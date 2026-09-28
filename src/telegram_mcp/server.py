"""MCP server exposing your Telegram account and its alert monitor.

Two groups of tools:

  * Read tools (list_dialogs, read_messages, search_messages,
    unread_summary) talk to Telegram directly via Telethon.
  * Monitor tools (rules, criteria, alerts) only touch the local database.
    The watcher daemon does the live listening and holds a *separate*
    Telegram session, so the two processes never contend for one session
    lock — and monitoring keeps working even if this process never logs in.

Run with `telegram-mcp`. See the README for registration and setup.
"""

import contextlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from mcp.server.fastmcp import Context, FastMCP
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from . import auth, config, connect, db, matching

SESSION_NAME = os.environ.get("TELEGRAM_MCP_SESSION", "mcp")
WATCHER_SESSION_NAME = os.environ.get("TELEGRAM_MCP_WATCHER_SESSION", "watcher")
HEARTBEAT_STALE_SECONDS = 90
SEVERITY_ORDER = ["none", "low", "medium", "high", "critical"]

# This server speaks JSON-RPC over stdout. Anything else written there
# corrupts the stream, and Telethon logs at INFO by default — so send all
# logging to stderr and quiet the noisy loggers.
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
for _noisy in ("telethon", "asyncio", "httpx"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

mcp = FastMCP("telegram")
_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    """Build the Telethon client on first use, not at import time, so the
    monitor tools stay usable without Telegram credentials."""
    global _client
    if _client is None:
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not api_id or not api_hash:
            raise RuntimeError(
                "Set TELEGRAM_API_ID and TELEGRAM_API_HASH (from "
                "https://my.telegram.org) to use the Telegram read tools. "
                "The monitor tools work without them."
            )
        _client = TelegramClient(config.session_path(SESSION_NAME), int(api_id), api_hash)
    return _client


@contextlib.asynccontextmanager
async def connected():
    """Connect for one read tool call, without ever prompting.

    Telethon's own ``async with client`` calls ``start()``, which falls back
    to asking for a phone number and login code on stdin. In this process
    stdin is the JSON-RPC pipe, so that hangs the call forever instead of
    failing. Connect explicitly and check authorization ourselves, so an
    unauthorized session is a readable error and not a dead tool.
    """
    client = get_client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError(
                f"The '{SESSION_NAME}' Telegram session is not logged in, so "
                "the read tools cannot run. Call login_request_code with the "
                f"user's phone number and session='{SESSION_NAME}', then "
                "login_submit_code with the code Telegram sends. Check "
                "auth_status to see which sessions are authorized."
            )
        yield client
    finally:
        await client.disconnect()


def _entity_kind(entity) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return "unknown"


def _entity_name(entity) -> str:
    if isinstance(entity, User):
        return " ".join(filter(None, [entity.first_name, entity.last_name])) or (
            entity.username or str(entity.id)
        )
    return getattr(entity, "title", None) or str(getattr(entity, "id", "unknown"))


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


@mcp.tool()
async def auth_status() -> dict:
    """Check whether Telegram is logged in, and as whom.

    Reports both sessions: the watcher's (the one that must be logged in for
    monitoring to work) and this server's (needed only for the read tools).
    Call this before anything else if alerts or reads are failing.
    """
    return {
        "home": str(config.home()),
        "sessions": [
            await auth.status(WATCHER_SESSION_NAME),
            await auth.status(SESSION_NAME),
        ],
    }


@mcp.tool()
async def connect_telegram(ctx: Context) -> dict:
    """Log in to Telegram through popup forms. The easiest way to set up.

    Uses the app's own forms when it supports them, otherwise native dialog
    boxes on macOS, Windows or Linux. Asks the user for the app credentials (only
    if not saved yet), their phone number, each login code, and their 2FA
    password if they have one. None of these pass through the conversation,
    so do not ask the user for them in chat. Logs in both sessions: 'mcp'
    (read tools) and 'watcher' (monitoring). Safe to run again: sessions
    already logged in are skipped.

    If the result has a 'fallback' field, this app cannot show forms; follow
    those instructions instead.
    """
    params = ctx.session.client_params
    if params and params.capabilities.elicitation:
        async def ask(message, schema):
            result = await ctx.elicit(message, schema)
            return result.data if result.action == "accept" else None
    elif connect.native_dialogs_available():
        ask = connect.native_ask
    else:
        return {
            "ok": False,
            "fallback": "This app can't show login forms, so log in through the "
                        "chat: set_api_credentials, then login_request_code and "
                        "login_submit_code for session='mcp', and again for "
                        "session='watcher'.",
        }

    return await connect.run(ask, [SESSION_NAME, WATCHER_SESSION_NAME])


@mcp.tool()
def set_api_credentials(api_id: str, api_hash: str) -> dict:
    """Save the Telegram app credentials needed before any login.

    The user gets these from https://my.telegram.org under "API development
    tools" — they identify the application, not the account, and are not
    secret in the way a login code is. Stored owner-only in <home>/.env.

    Args:
        api_id: numeric App api_id from my.telegram.org.
        api_hash: 32-character App api_hash from my.telegram.org.
    """
    error = auth.validate_api_credentials(api_id, api_hash)
    if error:
        return {"ok": False, "error": error}
    path = auth.write_api_credentials(str(api_id).strip(), api_hash.strip())
    return {"ok": True, "written_to": path}


@mcp.tool()
async def login_request_code(phone: str, session: str = "watcher") -> dict:
    """Start logging in: ask Telegram to send a login code.

    Telegram delivers the code in the Telegram app itself if the user is
    signed in elsewhere, otherwise by SMS. Follow with login_submit_code.

    Ask the user for their phone number rather than guessing it.

    Args:
        phone: phone number in international format, e.g. +14155550123.
        session: which session to log in — 'watcher' (default, the one
            monitoring needs) or 'mcp' (for this server's read tools).
    """
    name = WATCHER_SESSION_NAME if session == "watcher" else SESSION_NAME
    try:
        result = await auth.request_code(phone, name)
    except auth.AuthError as exc:
        return {"ok": False, "error": str(exc)}
    if result.get("already_authorized"):
        return {"ok": True, "already_authorized": True,
                "note": f"the {session} session is already logged in"}
    return {"ok": True,
            "next": "Ask the user for the code Telegram just sent, then call "
                    "login_submit_code. Codes expire in a few minutes."}


@mcp.tool()
async def login_submit_code(
    code: str,
    password: str | None = None,
    session: str = "watcher",
) -> dict:
    """Finish logging in with the code Telegram sent.

    If the account has two-factor authentication, this returns an error
    asking for the password; call it again with both.

    Args:
        code: the login code the user received.
        password: two-factor password, only if the account has one.
        session: the session being logged in; must match login_request_code.
    """
    name = WATCHER_SESSION_NAME if session == "watcher" else SESSION_NAME
    try:
        return await auth.submit_code(code, password, name)
    except auth.AuthError as exc:
        return {"ok": False, "error": str(exc)}


# --------------------------------------------------------------------------
# Read tools (talk to Telegram)
# --------------------------------------------------------------------------


@mcp.tool()
async def list_dialogs(
    limit: int = 50,
    unread_only: bool = False,
    include_archived: bool = False,
) -> list[dict]:
    """List your Telegram chats/channels, most recently active first.

    Use this to find the numeric chat ids you need for alert rule scopes.

    Args:
        limit: max number of dialogs to return.
        unread_only: only return dialogs with unread messages.
        include_archived: include archived chats (excluded by default).
    """
    async with connected() as client:
        out = []
        async for dialog in client.iter_dialogs(limit=None, archived=None):
            if not include_archived and dialog.archived:
                continue
            if unread_only and dialog.unread_count == 0:
                continue
            out.append(
                {
                    "id": dialog.id,
                    "name": _entity_name(dialog.entity),
                    "kind": _entity_kind(dialog.entity),
                    "unread_count": dialog.unread_count,
                    "archived": dialog.archived,
                    "last_message_date": (
                        dialog.date.isoformat() if dialog.date else None
                    ),
                }
            )
            if len(out) >= limit:
                break
        return out


@mcp.tool()
async def read_messages(chat_id: int, limit: int = 20) -> list[dict]:
    """Read the most recent messages from a chat/channel.

    Args:
        chat_id: numeric dialog id, as returned by list_dialogs.
        limit: max number of messages to return (most recent first).
    """
    async with connected() as client:
        entity = await client.get_entity(chat_id)
        out = []
        async for msg in client.iter_messages(entity, limit=limit):
            out.append(
                {
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "sender_id": msg.sender_id,
                    "text": msg.message or "",
                    "has_media": msg.media is not None,
                }
            )
        return out


@mcp.tool()
async def search_messages(
    query: str,
    chat_id: int | None = None,
    limit: int = 30,
) -> list[dict]:
    """Search your Telegram messages for a keyword.

    Searches history, unlike alert rules which only see new messages.

    Args:
        query: text to search for.
        chat_id: restrict search to one chat; omit to search all chats.
        limit: max number of results.
    """
    async with connected() as client:
        entity = await client.get_entity(chat_id) if chat_id else None
        out = []
        async for msg in client.iter_messages(entity, search=query, limit=limit):
            out.append(
                {
                    "chat_id": msg.chat_id,
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "text": msg.message or "",
                }
            )
        return out


@mcp.tool()
async def unread_summary(limit_per_chat: int = 5, max_chats: int = 30) -> list[dict]:
    """Summarize unread chats: for each, the unread count and the last
    few unread message previews.

    Args:
        limit_per_chat: how many recent messages to preview per chat.
        max_chats: max number of unread chats to include.
    """
    async with connected() as client:
        out = []
        async for dialog in client.iter_dialogs(limit=None):
            if dialog.unread_count == 0 or dialog.archived:
                continue
            previews = []
            async for msg in client.iter_messages(dialog.entity, limit=limit_per_chat):
                previews.append(msg.message or "[media/non-text]")
            out.append(
                {
                    "chat_id": dialog.id,
                    "name": _entity_name(dialog.entity),
                    "unread_count": dialog.unread_count,
                    "recent_previews": previews,
                }
            )
            if len(out) >= max_chats:
                break
        return out


@mcp.tool()
async def preview_rule(
    pattern: str,
    match_type: str = "substring",
    case_sensitive: bool = False,
    chat_ids: list[int] | None = None,
    search_hint: str | None = None,
    limit: int = 15,
    scan: int = 300,
) -> dict:
    """Test a candidate rule against real message history before creating it.

    Shows what the rule *would* have matched, so the user can judge whether it
    is too broad or too narrow while they are still writing it. Creates
    nothing. Use this during setup, before add_alert_rule, and show the user
    the samples — a rule that looks sensible in the abstract often turns out
    to match mostly noise.

    The matched samples are also the right input for testing draft criteria:
    read them and decide which ones a criterion should keep, then tell the
    user which would have been surfaced and which filtered out.

    Args:
        pattern: the candidate pattern.
        match_type: 'substring', 'word', or 'regex'.
        case_sensitive: match case exactly.
        chat_ids: restrict to these chats; omit to search everywhere.
        search_hint: a plain word to search Telegram for when match_type is
            'regex' — Telegram cannot search by regex, so this narrows what
            gets scanned locally. Required for an unscoped regex preview.
        limit: max samples to return.
        scan: how many messages to pull and test.
    """
    try:
        matching.validate(pattern, match_type, case_sensitive)
    except matching.RuleError as exc:
        return {"ok": False, "error": str(exc)}

    if match_type == "regex":
        term = search_hint
        if not term and not chat_ids:
            return {
                "ok": False,
                "error": "Telegram can't search by regex. Pass search_hint with a "
                         "plain word the pattern implies, or scope with chat_ids.",
            }
    else:
        term = pattern

    candidate = {
        "id": None, "pattern": pattern, "match_type": match_type,
        "case_sensitive": case_sensitive, "chat_ids": chat_ids,
        "exclude_chat_ids": None, "include_outgoing": True,
    }

    samples, scanned, chats_hit = [], 0, {}
    async with connected() as client:
        targets = chat_ids if chat_ids else [None]
        for target in targets:
            entity = await client.get_entity(target) if target is not None else None
            async for msg in client.iter_messages(entity, search=term, limit=scan):
                scanned += 1
                text = msg.message or ""
                excerpt = matching.check(candidate, text, msg.chat_id, False)
                if not excerpt:
                    continue
                name = _entity_name(await msg.get_chat()) if msg.chat_id else "?"
                chats_hit[name] = chats_hit.get(name, 0) + 1
                if len(samples) < limit:
                    samples.append({
                        "chat": name,
                        "date": msg.date.isoformat() if msg.date else None,
                        "excerpt": excerpt,
                    })

    total = sum(chats_hit.values())
    return {
        "ok": True,
        "pattern": pattern,
        "match_type": match_type,
        "scanned": scanned,
        "matched": total,
        "match_rate": round(total / scanned, 3) if scanned else None,
        "top_chats": sorted(chats_hit.items(), key=lambda kv: -kv[1])[:10],
        "samples": samples,
        "note": "Nothing was created. Scanned messages Telegram returned for "
                f"the search term {term!r}, so this is a sample, not a full count.",
    }


# --------------------------------------------------------------------------
# Monitor tools (local DB only — no Telegram credentials needed)
# --------------------------------------------------------------------------


@mcp.tool()
def add_alert_rule(
    name: str,
    pattern: str,
    match_type: str = "substring",
    case_sensitive: bool = False,
    chat_ids: list[int] | None = None,
    exclude_chat_ids: list[int] | None = None,
    include_outgoing: bool = False,
    notify: bool = True,
) -> dict:
    """Create an alert rule. The watcher picks it up within a few seconds —
    no restart needed. Rules only match messages that arrive *after* they
    are created; use search_messages to look backwards.

    Args:
        name: unique label for the rule, used in alerts and notifications.
        pattern: what to look for.
        match_type: 'substring' (default), 'word' (whole-word only), or 'regex'.
        case_sensitive: match case exactly (default: case-insensitive).
        chat_ids: only watch these chats; omit to watch every chat.
        exclude_chat_ids: never match in these chats; applied before chat_ids.
        include_outgoing: also match messages you send (default: incoming only).
        notify: fire a macOS desktop notification on match.
    """
    try:
        matching.validate(pattern, match_type, case_sensitive)
    except matching.RuleError as exc:
        return {"ok": False, "error": str(exc)}

    db.init()
    with db.session() as conn:
        existing = conn.execute(
            "SELECT id FROM rules WHERE name=?", (name,)
        ).fetchone()
        if existing:
            return {
                "ok": False,
                "error": f"a rule named {name!r} already exists (id {existing['id']})",
            }
        cur = conn.execute(
            "INSERT INTO rules(name, pattern, match_type, case_sensitive, chat_ids,"
            " exclude_chat_ids, include_outgoing, notify, enabled, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,1,?)",
            (
                name,
                pattern,
                match_type,
                int(case_sensitive),
                json.dumps(chat_ids) if chat_ids else None,
                json.dumps(exclude_chat_ids) if exclude_chat_ids else None,
                int(include_outgoing),
                int(notify),
                db.now(),
            ),
        )
        rule_id = cur.lastrowid
    return {"ok": True, "rule_id": rule_id, "name": name}


@mcp.tool()
def list_alert_rules(include_disabled: bool = True) -> list[dict]:
    """List alert rules with their hit counts.

    Args:
        include_disabled: include rules that are currently turned off.
    """
    db.init()
    query = "SELECT * FROM rules"
    if not include_disabled:
        query += " WHERE enabled=1"
    query += " ORDER BY id"
    with db.session() as conn:
        return [db.rule_to_dict(row) for row in conn.execute(query).fetchall()]


@mcp.tool()
def set_alert_rule_enabled(rule_id: int, enabled: bool) -> dict:
    """Turn an alert rule on or off without deleting it or its alerts.

    Args:
        rule_id: id from list_alert_rules.
        enabled: True to resume matching, False to pause.
    """
    db.init()
    with db.session() as conn:
        cur = conn.execute(
            "UPDATE rules SET enabled=? WHERE id=?", (int(enabled), rule_id)
        )
    if cur.rowcount == 0:
        return {"ok": False, "error": f"no rule with id {rule_id}"}
    return {"ok": True, "rule_id": rule_id, "enabled": enabled}


@mcp.tool()
def delete_alert_rule(rule_id: int) -> dict:
    """Delete an alert rule and every alert it produced. Irreversible —
    prefer set_alert_rule_enabled(rule_id, False) to just pause it.

    Args:
        rule_id: id from list_alert_rules.
    """
    db.init()
    with db.session() as conn:
        alerts = conn.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE rule_id=?", (rule_id,)
        ).fetchone()["n"]
        cur = conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    if cur.rowcount == 0:
        return {"ok": False, "error": f"no rule with id {rule_id}"}
    return {"ok": True, "rule_id": rule_id, "deleted_alerts": alerts}


@mcp.tool()
def list_alerts(
    limit: int = 30,
    unacked_only: bool = True,
    rule_id: int | None = None,
    chat_id: int | None = None,
    since_hours: float | None = None,
    verdict: str | None = None,
    min_severity: str | None = None,
    include_irrelevant: bool = False,
) -> list[dict]:
    """List recorded alerts, newest first.

    By default this hides alerts the judge ruled irrelevant — that filtering
    is the whole point of the judge. Pass include_irrelevant=True to audit
    what it rejected and why (each one keeps its reasoning).

    Args:
        limit: max number of alerts to return.
        unacked_only: only alerts you haven't acknowledged yet (default).
        rule_id: restrict to one prefilter rule.
        chat_id: restrict to one chat.
        since_hours: only alerts matched within this many hours.
        verdict: exact verdict — relevant, irrelevant, pending, skipped, error.
        min_severity: lowest severity to include (low, medium, high, critical).
        include_irrelevant: include alerts the judge rejected.
    """
    db.init()
    clauses, params = [], []
    if unacked_only:
        clauses.append("a.acked=0")
    if rule_id is not None:
        clauses.append("a.rule_id=?")
        params.append(rule_id)
    if chat_id is not None:
        clauses.append("a.chat_id=?")
        params.append(chat_id)
    if since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        clauses.append("a.matched_at >= ?")
        params.append(cutoff.isoformat())
    if verdict is not None:
        clauses.append("a.verdict=?")
        params.append(verdict)
    elif not include_irrelevant:
        clauses.append("a.verdict != 'irrelevant'")
    if min_severity is not None:
        if min_severity not in SEVERITY_ORDER:
            return [{"error": f"min_severity must be one of {SEVERITY_ORDER[1:]}"}]
        allowed = SEVERITY_ORDER[SEVERITY_ORDER.index(min_severity):]
        clauses.append(
            "a.severity IN (%s)" % ",".join("?" * len(allowed))
        )
        params.extend(allowed)

    query = (
        "SELECT a.*, r.name AS rule_name FROM alerts a"
        " JOIN rules r ON r.id = a.rule_id"
    )
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY a.id DESC LIMIT ?"
    params.append(limit)

    with db.session() as conn:
        rows = conn.execute(query, params).fetchall()
    return [db.alert_to_dict(row) for row in rows]


@mcp.tool()
def ack_alerts(
    alert_ids: list[int] | None = None,
    rule_id: int | None = None,
    all_alerts: bool = False,
) -> dict:
    """Mark alerts as acknowledged so they drop out of the default
    list_alerts view. Pass exactly one of the three selectors.

    Args:
        alert_ids: specific alert ids to acknowledge.
        rule_id: acknowledge every unacked alert from this rule.
        all_alerts: acknowledge every unacked alert.
    """
    selectors = [alert_ids is not None, rule_id is not None, all_alerts]
    if sum(selectors) != 1:
        return {
            "ok": False,
            "error": "pass exactly one of alert_ids, rule_id, or all_alerts=True",
        }

    db.init()
    with db.session() as conn:
        if alert_ids is not None:
            if not alert_ids:
                return {"ok": True, "acked": 0}
            placeholders = ",".join("?" * len(alert_ids))
            cur = conn.execute(
                f"UPDATE alerts SET acked=1 WHERE acked=0 AND id IN ({placeholders})",
                alert_ids,
            )
        elif rule_id is not None:
            cur = conn.execute(
                "UPDATE alerts SET acked=1 WHERE acked=0 AND rule_id=?", (rule_id,)
            )
        else:
            cur = conn.execute("UPDATE alerts SET acked=1 WHERE acked=0")
    return {"ok": True, "acked": cur.rowcount}


@mcp.tool()
def add_criterion(name: str, description: str) -> dict:
    """Add a natural-language criterion the judge uses to decide whether a
    prefiltered post actually matters. The watcher picks it up on the next
    judged alert — no restart needed.

    Rules decide what gets looked at; criteria decide what gets surfaced.
    Write a criterion the way you'd brief someone doing the triage for you:
    say what qualifies and what doesn't. "A specific open remote backend role
    that names the company" beats "jobs".

    Args:
        name: short unique label, shown on matching alerts.
        description: what qualifies, in plain language.
    """
    db.init()
    with db.session() as conn:
        existing = conn.execute("SELECT id FROM criteria WHERE name=?", (name,)).fetchone()
        if existing:
            return {"ok": False,
                    "error": f"a criterion named {name!r} already exists (id {existing['id']})"}
        cur = conn.execute(
            "INSERT INTO criteria(name, description, enabled, created_at) VALUES(?,?,1,?)",
            (name, description, db.now()),
        )
    return {"ok": True, "criterion_id": cur.lastrowid, "name": name}


@mcp.tool()
def list_criteria(include_disabled: bool = True) -> list[dict]:
    """List the judging criteria and how often each has matched.

    Args:
        include_disabled: include criteria that are currently turned off.
    """
    db.init()
    query = "SELECT * FROM criteria"
    if not include_disabled:
        query += " WHERE enabled=1"
    query += " ORDER BY id"
    with db.session() as conn:
        return [db.criterion_to_dict(row) for row in conn.execute(query).fetchall()]


@mcp.tool()
def set_criterion_enabled(criterion_id: int, enabled: bool) -> dict:
    """Turn a criterion on or off without deleting it.

    Args:
        criterion_id: id from list_criteria.
        enabled: True to resume judging against it, False to pause.
    """
    db.init()
    with db.session() as conn:
        cur = conn.execute(
            "UPDATE criteria SET enabled=? WHERE id=?", (int(enabled), criterion_id)
        )
    if cur.rowcount == 0:
        return {"ok": False, "error": f"no criterion with id {criterion_id}"}
    return {"ok": True, "criterion_id": criterion_id, "enabled": enabled}


@mcp.tool()
def delete_criterion(criterion_id: int) -> dict:
    """Delete a criterion. Alerts already judged against it keep their
    verdicts. Prefer set_criterion_enabled to pause one.

    Args:
        criterion_id: id from list_criteria.
    """
    db.init()
    with db.session() as conn:
        cur = conn.execute("DELETE FROM criteria WHERE id=?", (criterion_id,))
    if cur.rowcount == 0:
        return {"ok": False, "error": f"no criterion with id {criterion_id}"}
    return {"ok": True, "criterion_id": criterion_id}


@mcp.tool()
def monitor_status() -> dict:
    """Check whether the watcher daemon is running and what it has seen.

    Reports liveness from the daemon's heartbeat, so a 'stale' result means
    watcher.py has stopped and no new alerts are being recorded.
    """
    db.init()
    with db.session() as conn:
        heartbeat = db.get_state(conn, "watcher")
        beat_at = db.state_updated_at(conn, "watcher")
        counts = conn.execute(
            "SELECT"
            " (SELECT COUNT(*) FROM rules)                          AS rules,"
            " (SELECT COUNT(*) FROM rules WHERE enabled=1)          AS enabled_rules,"
            " (SELECT COUNT(*) FROM criteria)                       AS criteria,"
            " (SELECT COUNT(*) FROM criteria WHERE enabled=1)       AS enabled_criteria,"
            " (SELECT COUNT(*) FROM alerts)                         AS alerts,"
            " (SELECT COUNT(*) FROM alerts WHERE acked=0)           AS unacked_alerts,"
            " (SELECT COUNT(*) FROM alerts WHERE verdict='relevant')   AS relevant,"
            " (SELECT COUNT(*) FROM alerts WHERE verdict='irrelevant') AS filtered_out,"
            " (SELECT COUNT(*) FROM alerts WHERE verdict='pending')    AS awaiting_judgement,"
            " (SELECT COUNT(*) FROM alerts WHERE verdict='error')      AS judge_errors"
        ).fetchone()
        latest = conn.execute(
            "SELECT matched_at FROM alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()

    age = None
    if beat_at:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(beat_at)).total_seconds()

    return {
        "db_path": str(config.db_path()),
        "watcher_running": age is not None and age < HEARTBEAT_STALE_SECONDS,
        "last_heartbeat": beat_at,
        "heartbeat_age_seconds": round(age, 1) if age is not None else None,
        "watcher": heartbeat,
        "rules": counts["rules"],
        "enabled_rules": counts["enabled_rules"],
        "criteria": counts["criteria"],
        "enabled_criteria": counts["enabled_criteria"],
        "alerts": counts["alerts"],
        "unacked_alerts": counts["unacked_alerts"],
        "relevant": counts["relevant"],
        "filtered_out": counts["filtered_out"],
        "awaiting_judgement": counts["awaiting_judgement"],
        "judge_errors": counts["judge_errors"],
        "latest_alert_at": latest["matched_at"] if latest else None,
        "hint": (
            None
            if age is not None and age < HEARTBEAT_STALE_SECONDS
            else "watcher.py is not running — start it to record new alerts"
        ),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
