---
name: setup
description: Set up Telegram OSINT monitoring — connect Telegram, interview the user in depth (even when they aren't sure what they need), engineer and test keyword rules against their real channels, calibrate the judge's criteria on real messages, then create everything. Use on first run, or when the user wants to rebuild or substantially change what the Telegram OSINT plugin monitors.
---

# Setting up Telegram OSINT monitoring

Your job is to turn "I want to monitor Telegram" into a professional setup that
needs almost no editing afterwards. That takes time and effort up front, and
that is the point: a rushed setup means weeks of noise or silent misses.

Work through the phases below in order. Tell the user roughly where they are
("Phase 3 of 8 — keywords"). Do not create any rule or criterion before
phase 7, when the user has approved the full setup sheet.

## Resources in this skill's folder

- `packs/` — starter packs for common goals: `security-incidents.md`,
  `brand-mentions.md`, `regional-news.md`, `crypto-markets.md`,
  `deals-marketplaces.md`, `jobs-opportunities.md`, `research-releases.md`.
  Each has extra interview options, seed vocabulary, typical noise, rule
  groups and an example criterion. Read the ones matching the user's goal in
  phase 2. They are starting points to adapt, never a script — the user's
  answers and real messages override them.
- `keyword-engineering.md` — the method for phase 5.
- `data/language-patterns.md` — tested regex building blocks for Arabic,
  Persian, Hebrew, Russian and more.
- `data/country-names/<lang>.tsv` — every country's name in 18 languages,
  from Unicode CLDR.

Many users don't know exactly what they want. That is normal, and it is your
job to find out — from their channels, from real messages, and from their
reactions to concrete examples — not to make them specify everything in the
abstract.

## How to ask

- If you have a tool for multiple-choice questions, use it for every question
  in this interview. It usually allows only a few questions per call and a few
  options each, so run **several short rounds** rather than one huge form.
  Otherwise ask in conversation, two or three questions at a time.
- Write options specific to what you already know about the user, never
  generic filler. Use multi-select wherever more than one answer can apply.
- The user can always choose one of three helpers, on any question:
  - **Suggest for me** — propose a concrete answer from what you know (their
    channels, earlier answers, the sample messages), say why in one line, and
    ask them to confirm. Record it as an assumption you made (phase 6 lists
    them all).
  - **Widen coverage** — go beyond what they listed: related topics, more
    names and aliases, other languages and spellings, adjacent channels in
    their list. Show what you would add as a multi-select so they keep
    control, and say what it costs in volume.
  - **Describe it in my own words** — let them explain freely, then restate it
    as concrete answers ("So: X, Y, not Z — right?") and confirm before moving
    on. Treat their words as the source of truth over any option you offered.
- Put these helpers as options on the questions where they matter most (goal,
  topics, names, sources, noise). Where option slots run out, end the round
  with one extra question — **How should I continue?** · Looks right, next ·
  Suggest for me · Widen coverage · Let me describe it — the free-text answer
  covers "describe". Offer it after every round, so help is always one click
  away.
- Skip anything they have already told you. Never ask the same thing twice.
- Keep each option short and plain. Avoid jargon like "regex" or "criteria" in
  options; say "keywords" and "what counts as important".

## Phase 1 — Connect

Call `auth_status`. If a session is not logged in, log it in through the chat,
asking for one thing at a time in plain text (not multiple-choice):

1. If no app credentials are saved, ask for the **API ID and API hash** from
   https://my.telegram.org (API development tools), and save them with
   `set_api_credentials`.
2. Ask for the **phone number** of the Telegram account, in international
   format.
3. For the `mcp` session (reading) and then the `watcher` session
   (monitoring): call `login_request_code`, ask for the code Telegram sends to
   their Telegram app, and call `login_submit_code`. Each session gets its own,
   different code — say so, so they use the newest one.
4. If Telegram asks for a password, the account has two-step verification:
   ask for it and call `login_submit_code` again with the code and password.

Before starting, tell the user once, briefly, that what they type here —
including the API hash and codes — becomes part of this conversation, and
suggest a dedicated account rather than their personal one if they monitor
sensitive channels. Codes expire within minutes; if one does, request a new
one.

Nothing else works until this does — phases 3 to 5 read real messages.

## Phase 2 — Goal and context

One or two rounds. Cover:

1. **Goal.** Offer starting points and let them pick one or more:
   mentions of an organization, person or brand · incidents in a field or
   region · a topic or research area · deals, listings or prices · jobs or
   opportunities · community moderation · "Not sure — look at my channels and
   suggest". Their answer is the backbone of the criteria. Read the matching
   starter packs now and use their extra interview options in the next
   rounds. If no pack fits, build the options yourself the same way.
2. **Role.** Who is reading the alerts — analyst, journalist, researcher,
   trader, recruiter, founder, moderator, other. It tells you what "useful"
   means to them.
3. **What happens with an alert.** Act on it immediately · review once or
   twice a day · collect for later research. This sets how strict to be.
4. **Volume.** Catch everything (more noise) · balanced · only what really
   matters. Translate it into a target number of alerts per day and say it
   back to them.
5. **Languages.** Which languages and scripts appear in their sources. Offer
   the likely ones based on anything they have said, plus "Not sure — check my
   channels".

If they chose "Not sure" for the goal, go to phase 3 first, then come back:
show them what their channels are about and ask which of those themes matter.

## Phase 3 — Sources

1. Call `list_dialogs` (a high `limit`, e.g. 300) to see every chat they are in.
2. Group them for the user: channels vs groups vs private chats, and by apparent
   theme from their names. Show the groups as multi-select options, e.g.
   "Security news channels (23)", "Job boards (8)", "Friends & family (41)".
3. Recommend excluding private and personal chats unless they say otherwise;
   rules without a scope match *every* chat, including personal ones.
4. Ask whether any specific channels must never be missed, and whether any
   are known to be noisy.
5. Resolve their choice into a concrete list of chat ids for `chat_ids`, and
   note any ids for `exclude_chat_ids`.

If their channels don't cover what they want to watch, say so plainly — the
plugin only sees chats their account has joined — and suggest the kinds of
channels they would need to join.

## Phase 4 — What matters, by example

This is the most important phase, and the one that works for users who can't
describe what they want.

1. **Sample real messages.** Use `read_messages` on a handful of the selected
   channels (and `search_messages` for their key names or topics) to collect
   15–30 varied messages: some clearly on-topic, some borderline, some noise.
2. **Ask them to react.** Present the messages in small batches (shortened to
   a line or two each) with options per message: **Alert me · Skip · Not sure**.
   For "Alert me", follow up in the same round: how urgent — drop everything ·
   important · nice to know.
3. **Ask why, briefly, on the disagreements.** When they skip something that
   looks on-topic, or keep something that looks like noise, ask what makes the
   difference. That sentence goes straight into a criterion.
4. **Name the noise.** Offer the noise types you saw in their channels as a
   multi-select, and for each ask: drop it · keep it but mark it low. Typical
   kinds: reposts and forwards, old news resurfacing, ads and promotions,
   opinion and commentary, recruitment posts, vague claims with no specifics,
   duplicates across channels. Use the kinds that actually appear.
5. **Names and entities.** Ask for (and propose, from the samples) the specific
   organizations, people, products, handles, places and hashtags to track,
   with any aliases, abbreviations or local-language forms they know.

Stop when their reactions are consistent and you can predict their answer on
a new message. If you can't yet, sample more.

## Phase 5 — Keyword engineering

Now build the rules. **Read `keyword-engineering.md` in this skill's folder
before starting this phase** and follow it: vocabulary discovery from their
real messages, expansion into variants and other languages, the
language-specific checks, and testing every rule with `preview_rule`.

Principles that matter most:

- **Rules are broad, criteria are strict.** A rule that misses a message means
  it is never judged. Precision belongs in the criteria.
- Group keywords into a few rules by concept (names, topic terms, event
  words), not one giant pattern, so each can be tested and tuned on its own.
- Every rule gets tested on real history before it is proposed. Report the
  match rate, the chats the matches come from, and a few sample matches.

Show the user a short summary at the end: each rule's purpose, rough volume,
and anything you deliberately left out and why. Ask only about the judgment
calls; don't make them review raw patterns unless they want to.

## Phase 6 — Criteria and calibration

Write the criteria from phases 2 and 4 (see *Writing a criterion* below), then
calibrate them on real messages:

1. Take the messages the rules matched in phase 5, plus the ones the user
   reacted to in phase 4.
2. For each, decide how the draft criteria would rule and at what severity.
3. Show the user the outcome in batches: "Of 20 matches, these 4 would alert
   you, these 16 would be filtered. Here are the 4, and 4 of the filtered
   ones." Ask: agree · this one should alert · this one shouldn't.
4. Every disagreement becomes a sentence in a criterion. Repeat until they
   agree with the calls. Two or three rounds is normal.

Then show the **setup sheet**, one screen:

- sources in scope (and excluded),
- each rule: purpose, expected volume,
- each criterion, including its severity levels,
- expected alerts per day, compared with their target from phase 2,
- **assumptions you made for them** ("Not sure" answers and your defaults),
  each one easy to change,
- whether judging is on (it needs `ANTHROPIC_API_KEY`), and notifications.

Ask for approval, and make any changes before going on.

## Phase 7 — Create

Create everything with `add_alert_rule` and `add_criterion`, then confirm
with `list_alert_rules` and `list_criteria`. Leave `notify` on only for rules
whose alerts they want as desktop notifications.

## Phase 8 — Hand-off

Tell them briefly:

- **Start the watcher**, or nothing is recorded — see the watcher skill. Rules
  only see messages that arrive while it runs; use `search_messages` for
  history.
- **Day one is for tuning.** Tomorrow, review `list_alerts(include_irrelevant=True)`
  together: what was kept, what was dropped and why. Missed things mean the
  rules or criteria need loosening; noise means tightening.
- If `monitor_status()` reports `watcher_running: false`, nothing is being
  recorded, whatever the other tools say.
- **Review any time** with the review skill (`/telegram-osint:review`): it
  checks coverage, finds gaps and noise, and adjusts the setup in the same
  question format.

## Writing a criterion

State what qualifies **and** what does not, and give severity levels when the
user distinguished urgency. Compare:

> Bad: `jobs` — posts about jobs.
>
> Good: `remote-backend-roles` — A specific open role for a backend engineer
> that is remote or remote-friendly in Europe, posted by someone hiring for
> it. Must name the company and the role. High: senior roles at companies on
> the user's list. Medium: other matching roles. Excludes: recruiter
> cold-calls with no named company, roles requiring relocation, "we're
> growing" posts with no listing, and anyone advertising their own
> availability.

The shape is what matters, whatever the subject: something concrete that must
be present, severity levels drawn from the user's own "drop everything /
important / nice to know" answers, and a list of near-misses to reject taken
from the messages they skipped in phase 4.
