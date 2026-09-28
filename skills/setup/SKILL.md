---
name: setup
description: Set up Telegram monitoring — interview the user about what they watch for, then create the rules and criteria. Use on first run, or when the user wants to change what they are monitoring.
---

# Setting up Telegram monitoring

Your job is to turn "I want to monitor Telegram" into a working set of rules and
criteria. Interview first, then write. Do not create anything until the user has
seen it and agreed.

## Connect first

Testing rules needs a logged-in session, so start here. Call `auth_status`; if
either session is not authorized, call `connect_telegram`. It shows the user
popup forms for their app credentials, phone number, login codes and 2FA
password, so **never ask for any of these in chat** — the forms keep them out
of the conversation. If they don't have app credentials yet, tell them to get
an API ID and hash from https://my.telegram.org (API development tools) first.

If `connect_telegram` returns a `fallback`, this app can't show forms: follow
its instructions and use the step-by-step login tools instead.

## How the two stages differ

Get this distinction right, because the whole setup depends on it:

- **Rules** are cheap string matching (`substring`, `word`, `regex`). They run on
  every incoming message and decide what is worth an API call. They should be
  **broad** — a rule that misses something means it is never judged at all.
- **Criteria** are plain language. Claude judges every rule hit against them and
  decides what actually reaches the user. They should be **strict**.

Broad rules, strict criteria. Users get this backwards and write narrow rules
with vague criteria, which is the worst combination: they miss things *and* get
noise. If the user proposes that, say so.

## The interview

If you have a tool for asking the user multiple-choice questions, use it:
offer a few concrete suggested answers for each question, and let them write
their own. Otherwise ask in conversation, two or three at a time. Either way,
adapt — skip what they have already told you.

1. **What are you watching, and why?** Their domain, in their words — a job
   market, a research field, a product ecosystem, a region, a community. This
   becomes the substance of the criteria.
2. **What would make you drop everything?** The alert they never want to miss.
   This is the highest-severity criterion.
3. **What are you sick of seeing?** The most important question, and the one
   users never answer unprompted. Criteria that say what does *not* qualify are
   what make the judge worth running. Push for specifics — "reposts", "job ads
   for other cities", "price speculation", "announcements with no release date",
   "people asking the same beginner question".
4. **Any specific names?** Companies, people, products, handles, places. These
   often become their own rule plus a criterion.
5. **Everything, or specific chats?** If they only care about some channels, call
   `list_dialogs` to get the ids and scope the rules with `chat_ids`. If they are
   not sure, leave it unscoped — the judge handles the volume.

## Draft, test, then create

Do not create anything until it has been tested against their real messages.
A rule that reads sensibly in the abstract routinely turns out to match
almost entirely noise, and the user cannot know that from the wording alone.

**1. Draft the rules.** Broad, as above.

**2. Test each one with `preview_rule`** before `add_alert_rule`. It creates
nothing — it reports how many of their recent messages the pattern would have
caught, which chats those came from, and a sample of the actual text.

Read the result honestly and tell the user what you see:

- **`match_rate` above roughly 0.2** — the rule is very broad. Fine if the
  criteria will do the filtering, expensive if judging is enabled. Say so.
- **Zero matches** — usually a typo, or a term nobody actually writes. Try the
  word they would really use, not the formal one.
- **`top_chats` dominated by one channel** — that channel is about to become
  most of their alerts. Ask whether it belongs in `exclude_chat_ids`.

**3. Test the criteria against those same samples.** This is the step that
makes criteria good. Take the messages `preview_rule` returned, and for each
one decide how the draft criteria would rule on it. Then show the user:

> Of the 12 messages this rule caught, the criteria would surface 2 and filter
> 10. Here are the two it keeps, and here are three it drops — does that match
> what you'd want?

Their answer is the actual requirement. When they say "no, I'd want that one",
ask what makes it different from the ones they were happy to drop — that
difference is the sentence the criterion is missing.

**4. Iterate** until they agree with the calls on the samples. Two or three
rounds is normal and worth the time.

**5. Only now create them** with `add_alert_rule` and `add_criterion`, and
confirm with `list_alert_rules` and `list_criteria`.

## Writing a criterion

State what qualifies **and** what does not. Compare:

> Bad: `jobs` — posts about jobs.
>
> Good: `remote-backend-roles` — A specific open role for a backend engineer
> that is remote or remote-friendly in Europe, posted by someone hiring for
> it. Must name the company and the role. Excludes: recruiter cold-calls with
> no named company, roles requiring relocation, "we're growing" posts with no
> listing, and anyone advertising their own availability.

The shape is what matters, whatever the subject: something concrete that must
be present, and a short list of the near-misses to reject. The exclusions
usually come straight out of step 3 — they are the messages the user just told
you they did not want.

## Finish by telling them what happens next

Three things, briefly:

- Rules only see messages that arrive **while the watcher is running**. For
  history, use `search_messages`.
- The first day is for tuning. Have them run
  `list_alerts(include_irrelevant=True)` to see what the judge rejected and why —
  if it is dropping things it should not, the criteria need loosening; if noise
  gets through, they need tightening.
- If `monitor_status()` reports `watcher_running: false`, nothing is being
  recorded, regardless of what the other tools say.
