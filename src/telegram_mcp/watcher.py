"""Telegram monitor daemon.

Listens to every incoming message on your account, tests each against the
enabled rules, and records an alert for each hit. When criteria are defined
and Anthropic credentials are available, each hit is then judged by Claude
for relevance before it notifies you — the rules are a cheap prefilter, the
judge decides whether it actually matters.

Owns its own Telethon session, separate from the MCP server's.

Run with `telegram-mcp-watcher`. First run prompts for phone + login code.
"""

import asyncio
import json
import logging
import os
import platform
import sys
import time

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User

from . import config, db, matching

RULE_REFRESH_SECONDS = 5
HEARTBEAT_SECONDS = 30
NOTIFY_MAX_CHARS = 180
JUDGE_CONCURRENCY = 3

log = logging.getLogger("telegram-mcp-watcher")

SESSION_NAME = os.environ.get("TELEGRAM_MCP_WATCHER_SESSION", "watcher")
NOTIFY_ENABLED = os.environ.get("TELEGRAM_MCP_NOTIFY", "1") != "0"
JUDGE_ENABLED = os.environ.get("TELEGRAM_MCP_JUDGE", "1") != "0"


def judge_credentials() -> bool:
    """Lazily ask judge.py whether it can authenticate.

    ``anthropic`` is an optional dependency and judge.py is imported late, so
    this must tolerate the module being absent entirely.
    """
    try:
        from . import judge
    except Exception:
        return False
    return judge.credentials_present()

_rules: list[dict] = []
_rules_loaded_at = 0.0
_chat_names: dict[int, str] = {}
_messages_seen = 0
_judged = 0
_judge_queue: asyncio.Queue[int] | None = None


# --------------------------------------------------------------------------
# Telegram helpers
# --------------------------------------------------------------------------


def entity_name(entity) -> str:
    if isinstance(entity, User):
        return " ".join(filter(None, [entity.first_name, entity.last_name])) or (
            entity.username or str(entity.id)
        )
    if isinstance(entity, (Chat, Channel)):
        return getattr(entity, "title", None) or str(entity.id)
    return "unknown"


async def chat_name_for(event) -> str:
    chat_id = event.chat_id
    if chat_id not in _chat_names:
        try:
            _chat_names[chat_id] = entity_name(await event.get_chat())
        except Exception:
            _chat_names[chat_id] = str(chat_id)
    return _chat_names[chat_id]


async def sender_info(event) -> tuple[int | None, str | None]:
    try:
        sender = await event.get_sender()
    except Exception:
        return event.sender_id, None
    if sender is None:
        return event.sender_id, None
    return sender.id, entity_name(sender)


# --------------------------------------------------------------------------
# Rules and alerts
# --------------------------------------------------------------------------


def load_rules(force: bool = False) -> list[dict]:
    """Return enabled rules, re-reading from the DB at most every few seconds."""
    global _rules, _rules_loaded_at
    if not force and time.monotonic() - _rules_loaded_at < RULE_REFRESH_SECONDS:
        return _rules
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM rules WHERE enabled=1 ORDER BY id").fetchall()
    usable = []
    for row in rows:
        rule = db.rule_to_dict(row)
        try:
            matching.compile_rule(rule)
        except matching.RuleError as exc:
            log.warning("skipping rule %s (%s): %s", rule["id"], rule["name"], exc)
            continue
        usable.append(rule)
    _rules = usable
    _rules_loaded_at = time.monotonic()
    return _rules


def load_criteria() -> list[dict]:
    with db.session() as conn:
        rows = conn.execute(
            "SELECT * FROM criteria WHERE enabled=1 ORDER BY id"
        ).fetchall()
    return [db.criterion_to_dict(row) for row in rows]


def record_alert(rule: dict, alert: dict) -> int | None:
    """Insert an alert, returning its id, or None if this message already
    matched this rule."""
    with db.session() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO alerts("
            " rule_id, chat_id, chat_name, message_id, sender_id, sender_name,"
            " text, matched_excerpt, message_date, matched_at, verdict)"
            " VALUES(:rule_id,:chat_id,:chat_name,:message_id,:sender_id,"
            ":sender_name,:text,:matched_excerpt,:message_date,:matched_at,:verdict)",
            alert,
        )
        if cur.rowcount == 0:
            return None
        conn.execute(
            "UPDATE rules SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
            (alert["matched_at"], rule["id"]),
        )
        return cur.lastrowid


def fetch_alert(alert_id: int) -> dict | None:
    with db.session() as conn:
        row = conn.execute(
            "SELECT a.*, r.name AS rule_name, r.notify AS rule_notify"
            " FROM alerts a JOIN rules r ON r.id = a.rule_id WHERE a.id = ?",
            (alert_id,),
        ).fetchone()
    return db.alert_to_dict(row) if row else None


def store_verdict(alert_id: int, **fields) -> None:
    columns = ", ".join(f"{k} = :{k}" for k in fields)
    with db.session() as conn:
        conn.execute(
            f"UPDATE alerts SET {columns} WHERE id = :id", {**fields, "id": alert_id}
        )


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------


async def notify(title: str, body: str) -> None:
    if not NOTIFY_ENABLED or platform.system() != "Darwin":
        return

    def esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    body = body[:NOTIFY_MAX_CHARS].replace("\n", " ")
    script = (
        f'display notification "{esc(body)}" '
        f'with title "Telegram" subtitle "{esc(title)}"'
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception as exc:  # a failed notification must never kill the watcher
        log.warning("notification failed: %s", exc)


# --------------------------------------------------------------------------
# Judging
# --------------------------------------------------------------------------


async def judge_alert(alert_id: int, semaphore: asyncio.Semaphore) -> None:
    """Judge one alert and notify if it is worth surfacing.

    Judging is best-effort: if it fails, the alert is marked and still
    notified. Silently dropping a possible hit is worse than a false positive.
    """
    global _judged, JUDGE_ENABLED

    alert = fetch_alert(alert_id)
    if alert is None:
        return

    criteria = load_criteria() if JUDGE_ENABLED else []
    if not criteria:
        store_verdict(alert_id, verdict="skipped",
                      verdict_reason="no criteria defined; not judged")
        if alert["rule_notify"]:
            await notify(f"{alert['rule_name']} · {alert['chat_name']}",
                         alert["matched_excerpt"] or "")
        return

    from . import judge  # imported late: anthropic is an optional dependency

    async with semaphore:
        try:
            verdict = await judge.judge(alert, criteria)
        except judge.JudgeError as exc:
            log.warning("judge failed for alert %s: %s", alert_id, exc)
            store_verdict(alert_id, verdict="error", verdict_reason=str(exc),
                          judged_at=db.now(), judge_model=judge.MODEL)
            if alert["rule_notify"]:
                await notify(f"{alert['rule_name']} · {alert['chat_name']} (unjudged)",
                             alert["matched_excerpt"] or "")
            return
        except Exception as exc:
            # Auth/config problems would otherwise repeat on every single post.
            log.error("judging disabled after error: %s", exc)
            JUDGE_ENABLED = False
            store_verdict(alert_id, verdict="error", verdict_reason=str(exc))
            return

    _judged += 1
    store_verdict(
        alert_id,
        verdict="relevant" if verdict.relevant else "irrelevant",
        verdict_summary=verdict.summary,
        verdict_reason=verdict.reasoning,
        verdict_criteria=json.dumps(verdict.criteria),
        severity=verdict.severity,
        judged_at=db.now(),
        judge_model=judge.MODEL,
    )

    if not verdict.relevant:
        log.info("[%s] filtered out — %s", alert["chat_name"], verdict.summary)
        return

    for criterion in verdict.criteria:
        with db.session() as conn:
            conn.execute(
                "UPDATE criteria SET hit_count = hit_count + 1 WHERE name = ?",
                (criterion,),
            )

    log.info("[%s] %s · %s — %s", verdict.severity.upper(), alert["rule_name"],
             alert["chat_name"], verdict.summary)
    if alert["rule_notify"]:
        await notify(
            f"{verdict.severity.upper()} · {alert['chat_name']}", verdict.summary
        )


async def judge_worker() -> None:
    semaphore = asyncio.Semaphore(JUDGE_CONCURRENCY)
    assert _judge_queue is not None
    while True:
        alert_id = await _judge_queue.get()
        try:
            await judge_alert(alert_id, semaphore)
        except Exception as exc:
            log.exception("unhandled error judging alert %s: %s", alert_id, exc)
        finally:
            _judge_queue.task_done()


def requeue_pending() -> int:
    """Re-enqueue alerts left unjudged by a previous run."""
    with db.session() as conn:
        rows = conn.execute(
            "SELECT id FROM alerts WHERE verdict='pending' ORDER BY id"
        ).fetchall()
    assert _judge_queue is not None
    for row in rows:
        _judge_queue.put_nowait(row["id"])
    return len(rows)


# --------------------------------------------------------------------------
# Message handling
# --------------------------------------------------------------------------


async def handle(event) -> None:
    global _messages_seen
    _messages_seen += 1
    text = event.raw_text or ""
    if not text:
        return

    rules = load_rules()
    if not rules:
        return

    chat_id = event.chat_id
    outgoing = bool(event.out)
    hits = [(rule, ex) for rule in rules
            if (ex := matching.check(rule, text, chat_id, outgoing))]
    if not hits:
        return

    chat_name = await chat_name_for(event)
    sender_id, sender_name = await sender_info(event)
    message_date = event.message.date.isoformat() if event.message.date else None

    for rule, excerpt in hits:
        alert_id = record_alert(rule, {
            "rule_id": rule["id"],
            "chat_id": chat_id,
            "chat_name": chat_name,
            "message_id": event.message.id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "text": text,
            "matched_excerpt": excerpt,
            "message_date": message_date,
            "matched_at": db.now(),
            "verdict": "pending",
        })
        if alert_id is not None and _judge_queue is not None:
            _judge_queue.put_nowait(alert_id)


async def heartbeat() -> None:
    while True:
        try:
            with db.session() as conn:
                db.set_state(conn, "watcher", {
                    "pid": os.getpid(),
                    "session": SESSION_NAME,
                    "messages_seen": _messages_seen,
                    "active_rules": len(_rules),
                    "judged": _judged,
                    "judge_queue": _judge_queue.qsize() if _judge_queue else 0,
                    "judging": JUDGE_ENABLED and judge_credentials(),
                    "judge_requested": JUDGE_ENABLED,
                    "judge_credentials": judge_credentials(),
                    "notifications": NOTIFY_ENABLED,
                })
        except Exception as exc:
            log.warning("heartbeat write failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_SECONDS)


async def run() -> None:
    global _judge_queue

    api_id, api_hash = config.api_credentials()
    if not api_id or not api_hash:
        raise SystemExit(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH "
            "(get them from https://my.telegram.org)."
        )

    db.init()
    _judge_queue = asyncio.Queue()
    load_rules(force=True)
    criteria = load_criteria()

    log.info("db: %s", config.db_path())
    log.info("rules: %d enabled", len(_rules))
    have_creds = judge_credentials()
    log.info("criteria: %d enabled%s", len(criteria),
             "" if criteria and JUDGE_ENABLED and have_creds
             else " (judging off — alerts pass through)")
    if criteria and JUDGE_ENABLED and not have_creds:
        log.warning(
            "%d criteria are enabled but no Anthropic credentials were found, so "
            "NOTHING will be filtered — every rule match becomes an alert. Set "
            "ANTHROPIC_API_KEY (or run `ant auth login`) and restart.", len(criteria))

    pending = requeue_pending()
    if pending:
        log.info("requeued %d unjudged alerts from a previous run", pending)

    client = TelegramClient(config.session_path(SESSION_NAME), int(api_id), api_hash)
    client.add_event_handler(handle, events.NewMessage)

    await client.start()
    log.info("watching as %s — Ctrl+C to stop", entity_name(await client.get_me()))

    tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(judge_worker())]
    try:
        await client.run_until_disconnected()
    finally:
        for task in tasks:
            task.cancel()
        with db.session() as conn:
            db.set_state(conn, "watcher_stopped_at", db.now())


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("TELEGRAM_MCP_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
