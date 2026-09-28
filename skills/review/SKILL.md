---
name: review
description: Review and improve Telegram OSINT coverage at any time — show what is being monitored and how it is performing, find gaps and noise, then let the user widen coverage, cut noise, add names, topics or channels, or describe what they want, in the same popup question format as setup. Use when the user asks to review, audit, check, tune, expand or adjust their Telegram monitoring.
---

# Reviewing Telegram OSINT coverage

The user wants to see how well their monitoring covers what they care about,
and to improve it. Diagnose first, then ask what to change, then test changes
before applying them.

Ask questions the same way the setup skill does: use your multiple-choice
question tool if you have one, in short rounds; otherwise ask in conversation.
Every round offers the three helpers — **Suggest for me**, **Widen coverage**,
**Describe it in my own words** — and ends with **How should I continue?** if
option slots ran out.

## 1. Check health

Call `monitor_status` and `auth_status`. If the watcher is not running, or a
session is logged out, say so first — nothing below means much while nothing
is being recorded. Offer to fix it (the watcher skill, or `connect_telegram`).
Note whether judging is on.

## 2. Build the coverage report

Gather, without asking anything yet:

- `list_alert_rules` and `list_criteria` — hit counts, what's enabled.
- `list_alerts(since_hours=168, include_irrelevant=True, unacked_only=False,
  limit=200)` — the last week: volume per day, per rule, per chat, and the
  split between surfaced and filtered.
- `list_dialogs` (high `limit`) — compare against the rules' `chat_ids`:
  channels joined since setup, and relevant-looking chats that no rule covers.

Then look for problems:

- **Silent rules** — no hits in a week. Dead term, or a channel that went quiet.
- **Noisy rules** — many hits, almost all filtered by the judge. Costly and a
  sign the terms are too loose.
- **Criteria that never fire**, or that fire on nearly everything.
- **Possible misses** — scan 30–50 recent messages from the most relevant
  chats with `read_messages`, and use `search_messages` for the user's key
  names. Anything that looks relevant but produced no alert is a coverage gap;
  work out which term or variant was missing.
- **Questionable verdicts** — filtered alerts that look relevant, or surfaced
  ones that look like noise. Pick a few of each to show the user.
- **Volume against the target** — if setup recorded a target, compare.

Present one short report: a few headline numbers, then the problems found,
each in one line with its likely fix. Don't dump raw data.

## 3. Ask what to change

One popup round, multi-select, with options drawn from what you found, for
example:

- Fix the gaps you found (list them)
- Widen coverage — more names, variants, languages or related topics
- Reduce noise — tighten the noisy rules or criteria
- Add or remove channels
- Add new names or topics
- Review the filtered alerts with me
- Suggest for me
- Let me describe what I want

Then follow up on what they picked, in further short rounds. For verdict
reviews, show real alerts with **Should alert · Should not · Not sure**, and
turn each disagreement into a sentence in the relevant criterion. For new
names or topics, and for widening, follow `../setup/keyword-engineering.md`.

## 4. Test before applying

Test every rule change with `preview_rule` on real history, including the
recall check: messages the user wants must be matched. Re-run the relevant
alerts through the draft criteria in your head and show the user what would
change.

## 5. Apply, safely

Show a short before/after summary and get approval. Then apply:

- There is no edit tool. To change a rule, create the new version with
  `add_alert_rule`, then **disable** the old one with `set_alert_rule_enabled`
  rather than deleting it — `delete_alert_rule` also deletes every alert the
  rule produced. Delete only if the user asks.
- Criteria the same way: `add_criterion`, then `set_criterion_enabled` false
  on the old one.
- Confirm with `list_alert_rules` and `list_criteria`.

Finish by suggesting when to review again — after a few days for big changes,
otherwise every week or two.
