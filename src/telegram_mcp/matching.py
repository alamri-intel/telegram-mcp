"""Rule compilation and matching.

A rule is a pattern plus a scope. Compiling is cached by rule id + the
fields that affect the regex, so the watcher can re-read rules from the
DB cheaply without recompiling on every message.
"""

import re

MATCH_TYPES = ("substring", "word", "regex")
EXCERPT_PAD = 70

_cache: dict[tuple, re.Pattern] = {}


class RuleError(ValueError):
    """A rule's pattern or match_type is not usable."""


def compile_rule(rule: dict) -> re.Pattern:
    key = (rule["id"], rule["pattern"], rule["match_type"], rule["case_sensitive"])
    cached = _cache.get(key)
    if cached is not None:
        return cached

    match_type = rule["match_type"]
    if match_type not in MATCH_TYPES:
        raise RuleError(
            f"match_type must be one of {MATCH_TYPES}, got {match_type!r}"
        )

    flags = 0 if rule["case_sensitive"] else re.IGNORECASE
    if match_type == "regex":
        try:
            pattern = re.compile(rule["pattern"], flags)
        except re.error as exc:
            raise RuleError(f"invalid regex {rule['pattern']!r}: {exc}") from exc
    elif match_type == "word":
        pattern = re.compile(rf"\b{re.escape(rule['pattern'])}\b", flags)
    else:
        pattern = re.compile(re.escape(rule["pattern"]), flags)

    _cache[key] = pattern
    return pattern


def validate(pattern: str, match_type: str, case_sensitive: bool) -> None:
    """Raise RuleError if this pattern/type pair can't be compiled."""
    compile_rule(
        {
            "id": None,
            "pattern": pattern,
            "match_type": match_type,
            "case_sensitive": case_sensitive,
        }
    )


def in_scope(rule: dict, chat_id: int, outgoing: bool) -> bool:
    if outgoing and not rule["include_outgoing"]:
        return False
    if rule["exclude_chat_ids"] and chat_id in rule["exclude_chat_ids"]:
        return False
    if rule["chat_ids"] and chat_id not in rule["chat_ids"]:
        return False
    return True


def excerpt(text: str, match: re.Match) -> str:
    start = max(0, match.start() - EXCERPT_PAD)
    end = min(len(text), match.end() + EXCERPT_PAD)
    out = text[start:end]
    if start > 0:
        out = "…" + out
    if end < len(text):
        out = out + "…"
    return out


def check(rule: dict, text: str, chat_id: int, outgoing: bool) -> str | None:
    """Return a matched excerpt, or None if this message doesn't match."""
    if not text or not in_scope(rule, chat_id, outgoing):
        return None
    match = compile_rule(rule).search(text)
    return excerpt(text, match) if match else None
