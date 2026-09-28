"""Stage 2 of the pipeline: Claude judges a prefiltered message against
the user's natural-language criteria.

Stage 1 (matching.py) is the cheap regex prefilter that decides what's even
worth an API call. Everything that survives lands here, where the question
stops being "does this string appear" and becomes "does this matter".

Env:
    ANTHROPIC_API_KEY        required (or an `ant auth login` profile)
    TELEGRAM_MCP_JUDGE_MODEL     default: claude-opus-5
    TELEGRAM_MCP_JUDGE_EFFORT    low | medium | high | xhigh | max (default: low)
"""

import json
import os
import pathlib

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

MODEL = os.environ.get("TELEGRAM_MCP_JUDGE_MODEL", "claude-opus-5")
# Triage is a classification route: it runs on every prefilter hit and rarely
# repays deep reasoning. Raise this if verdicts look shallow.
EFFORT = os.environ.get("TELEGRAM_MCP_JUDGE_EFFORT", "low")
MAX_TOKENS = 4000
MAX_POST_CHARS = 8000

SEVERITIES = ["none", "low", "medium", "high", "critical"]


def credentials_present() -> bool:
    """Whether judging can authenticate at all.

    ``TELEGRAM_MCP_JUDGE`` only records whether the operator *wants* judging.
    Without credentials the first verdict fails and every prefiltered message
    passes straight through to notification, so the two must be reported
    separately — a status of "judging on" with no key is how a person ends up
    trusting a filter that was never applied.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    for p in ("~/.anthropic", "~/.config/anthropic"):
        if (pathlib.Path(p).expanduser()).exists():
            return True
    return False

SYSTEM = """You are triaging messages from a person's monitored Telegram \
chats and channels. You see one message at a time, together with the criteria \
that person wrote describing what they want brought to their attention.

A message is relevant only if it substantively satisfies at least one \
criterion. Judge what the message actually says, not what subject it belongs \
to. Monitored feeds are mostly noise — reposts, chatter, promotion, and \
near-misses that mention a relevant term without containing anything of \
substance. A message that merely touches a criterion's topic without \
delivering on it is not relevant.

Severity is relative to this person's own criteria, not to the world: \
"critical" means they would want to know immediately, "low" means it belongs \
in a digest.

Set `relevant` to false and `severity` to "none" when nothing matches. List in \
`criteria` only the exact criterion names that matched. Keep `summary` to one \
sentence they can read at a glance, and put your justification — including why \
you rejected a near-miss — in `reasoning`."""

SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {
            "type": "boolean",
            "description": "True only if the post substantively satisfies a criterion.",
        },
        "criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exact names of the criteria that matched; empty if none.",
        },
        "severity": {
            "type": "string",
            "enum": SEVERITIES,
            "description": "How urgently a human should look. 'none' if not relevant.",
        },
        "summary": {
            "type": "string",
            "description": "One sentence: what this message says.",
        },
        "reasoning": {
            "type": "string",
            "description": "Why it matched or did not.",
        },
    },
    "required": ["relevant", "criteria", "severity", "summary", "reasoning"],
    "additionalProperties": False,
}


class Verdict(BaseModel):
    relevant: bool
    criteria: list[str]
    severity: str
    summary: str
    reasoning: str


class JudgeError(RuntimeError):
    """The judge could not produce a verdict for this post."""


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


def build_system(criteria: list[dict]) -> str:
    lines = [
        f"- {c['name']}: {c['description']}"
        for c in criteria
    ]
    return SYSTEM + "\n\nTheir criteria:\n\n" + "\n".join(lines)


def build_post(alert: dict) -> str:
    text = alert.get("text") or ""
    if len(text) > MAX_POST_CHARS:
        # Truncating changes the verdict, so say so rather than doing it silently.
        text = text[:MAX_POST_CHARS] + "\n[...post truncated for length...]"
    return (
        f"Channel: {alert.get('chat_name') or alert.get('chat_id')}\n"
        f"Sender: {alert.get('sender_name') or alert.get('sender_id') or 'unknown'}\n"
        f"Posted: {alert.get('message_date') or 'unknown'}\n"
        f"Matched prefilter rule: {alert.get('rule_name') or alert.get('rule_id')}\n\n"
        f"--- post ---\n{text}\n--- end post ---"
    )


async def judge(alert: dict, criteria: list[dict]) -> Verdict:
    """Ask Claude whether one post satisfies any criterion.

    Raises JudgeError if the model declines or returns something unusable;
    the caller decides whether that means retry, skip, or surface.
    """
    if not criteria:
        raise JudgeError("no enabled criteria to judge against")

    response = await get_client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": build_system(criteria),
                # Stable across every post; only shifts when criteria change.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": build_post(alert)}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
    )

    # These are hostile-content feeds; a decline is a normal outcome, not a bug.
    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "category", None)
        raise JudgeError(f"model declined to judge this post (category: {detail})")
    if response.stop_reason == "max_tokens":
        raise JudgeError("verdict truncated at max_tokens")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise JudgeError(f"no text block in response (stop_reason={response.stop_reason})")

    try:
        return Verdict(**json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise JudgeError(f"unparseable verdict: {exc}") from exc
