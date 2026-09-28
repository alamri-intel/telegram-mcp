# Telegram OSINT

An MCP server for your own Telegram account. Read your chats through an AI
assistant, and run a background monitor that watches every incoming message
for things you care about.

The monitor works in two stages: cheap **rules** (substring / whole-word /
regex) decide what's worth looking at, then Claude judges each hit against
your plain-language **criteria** and decides whether it's worth surfacing.
On a firehose of busy channels, stage one keeps the cost down and stage two
keeps the noise down. The judge is optional — without it, every rule hit
becomes an alert.

Everything runs locally. Nothing leaves your machine except calls to
Telegram's API and, if you enable judging, Anthropic's.

## What it runs and sends

- **Local server.** The plugin starts a Python MCP server on your computer
  with `uv run --locked`. On first start, uv downloads Python and the exact
  package versions pinned in `uv.lock` from PyPI.
- **Telegram.** The server and the watcher log in to *your* Telegram
  account (a user session, not a bot) and talk to Telegram's servers to
  list chats, read and search messages, and receive new ones. Nothing is
  ever sent, deleted, or left on Telegram — there are no write tools.
- **Anthropic.** Only when judging is on and `ANTHROPIC_API_KEY` is set, the
  watcher sends the text of each rule-matched message, plus your criteria,
  to Anthropic's API for a verdict. Messages that match no rule are never
  sent anywhere.
- **Login happens in the chat.** You type your Telegram API ID and hash,
  phone number, login codes and (if you have one) two-step verification
  password into the conversation, and Claude passes them to the local
  server. They become part of that conversation's history in your Claude
  app. The password is passed to Telegram once to sign in and is never
  stored.
- **Local files.** Session files, your API credentials (`.env`, mode
  `0600`), the alerts database, and the watcher log live in
  `~/.telegram-mcp/`. Nothing is uploaded elsewhere.
- **Background watcher.** A separate process you start yourself; the plugin
  never starts it for you. On macOS it can show desktop notifications via
  `osascript`.

## Where it works

| Claude app | Works |
|---|---|
| Claude Code (terminal, IDE, desktop app Code tab) | Yes |
| Cowork in the desktop app | Yes, when the task runs **on your computer** — not in a cloud task |
| Chat on claude.ai web, desktop, or mobile | Skills only — chat can't start a local server, so the Telegram tools aren't available |

**Operating systems.** Developed and tested on macOS. On Windows and Linux the
tools, login and monitoring work, but desktop notifications are macOS-only:
elsewhere alerts are still recorded and listed, they just don't pop up.

## Install

**Requires [uv](https://docs.astral.sh/uv/).** It provisions the right Python
version itself, so you don't need to manage one. On macOS, `brew install uv`;
for other systems, see uv's
[installation guide](https://docs.astral.sh/uv/getting-started/installation/).

As a Claude Code plugin — this is the easy path, and gives you the setup skill:

```bash
claude plugin marketplace add alamri-intel/telegram-mcp
claude plugin install telegram-osint@telegram-osint
```

Or from inside Claude Code: `/plugin marketplace add alamri-intel/telegram-mcp`,
then `/plugin install telegram-osint@telegram-osint`.

Start a new session, then run `/telegram-osint:setup` and answer the
questions — it writes your rules and criteria for you.

Or as a plain Python package, if you'd rather not use the plugin:

```bash
uv tool install "telegram-monitor-mcp[judge] @ git+https://github.com/alamri-intel/telegram-mcp"
claude mcp add telegram -- telegram-mcp
```

The `judge` extra pulls in the Anthropic SDK. Omit it if you only want rule
matching.

You need a Telegram `API_ID` / `API_HASH` pair from
<https://my.telegram.org> (API development tools). These identify the *app*,
not your account.

```bash
export TELEGRAM_API_ID=...
export TELEGRAM_API_HASH=...
export ANTHROPIC_API_KEY=...   # only if you want judging
```

## Start the watcher

```bash
telegram-mcp-watcher
```

The first run prompts for your phone number and the login code Telegram
sends. After that the saved session is reused and startup is silent. Leave
it running — alerts are only recorded while it's up.

To run it in the background:

```bash
nohup telegram-mcp-watcher > ~/.telegram-mcp/watcher.log 2>&1 &
```

## Registering the server by hand

The plugin does this for you. If you installed the plain package instead:

```bash
claude mcp add telegram -- telegram-mcp
```

Claude Desktop — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "telegram": {
      "command": "telegram-mcp",
      "env": {
        "TELEGRAM_API_ID": "...",
        "TELEGRAM_API_HASH": "..."
      }
    }
  }
}
```

The server and the watcher use **separate** Telegram sessions on purpose:
one session file can only be used by one process at a time. A side effect
worth knowing is that the monitor tools work even if the server itself is
never logged in — they only read the local database.

## Tools

**Monitoring** — local database only, no Telegram login needed

| Tool | |
|---|---|
| `add_alert_rule(name, pattern, …)` | Create a prefilter rule. Live within ~5s. |
| `list_alert_rules(include_disabled)` | Rules with hit counts. |
| `set_alert_rule_enabled(rule_id, enabled)` | Pause or resume a rule. |
| `delete_alert_rule(rule_id)` | Delete a rule and its alerts. |
| `add_criterion(name, description)` | Add a plain-language judging criterion. |
| `list_criteria(include_disabled)` | Criteria with hit counts. |
| `set_criterion_enabled(id, enabled)` | Pause or resume a criterion. |
| `delete_criterion(id)` | Delete a criterion. |
| `list_alerts(limit, verdict, min_severity, …)` | What matched and what the judge decided. |
| `ack_alerts(alert_ids \| rule_id \| all_alerts)` | Clear alerts from the default view. |
| `monitor_status()` | Watcher liveness, counts, judge throughput. |

**Skills** (plugin install only)

`/telegram-osint:setup` walks you through a full setup: it connects Telegram,
interviews you in multiple-choice rounds (with "suggest for me", "widen
coverage" and "describe it in my own words" at every step), learns what you
want from real messages in your channels, engineers and tests the keywords
across languages, calibrates the judge on real examples, and only then creates
the rules and criteria. `/telegram-osint:review` reports how your coverage is
performing — gaps, noise, silent rules, questionable verdicts — and adjusts it
in the same format, any time. `/telegram-osint:watcher` covers starting the
daemon and working out why alerts aren't arriving.

**Reading** — talks to Telegram

`list_dialogs`, `read_messages`, `search_messages`, `unread_summary`,
`preview_rule`. `list_dialogs` is how you find the numeric chat ids for rule
scopes; `search_messages` searches history, which rules never see;
`preview_rule` tests a candidate rule against real message history before you
create it.

**Login** — sets up your Telegram session

| Tool | |
|---|---|
| `auth_status()` | Whether credentials are saved and each session is logged in. |
| `set_api_credentials(api_id, api_hash)` | Save your Telegram app credentials to `~/.telegram-mcp/.env` (mode `0600`). |
| `login_request_code(phone)` | Ask Telegram to send a login code. |
| `login_submit_code(code, password)` | Finish login; the session file is saved locally. |

## Rules and criteria

They answer different questions. A **rule** asks "does this string appear?"
A **criterion** asks "does this matter?"

Rules:

- `match_type` — `substring` (default), `word` (whole words only, so
  `deploy` won't fire on `redeployment`), or `regex`
- `case_sensitive` — off by default
- `chat_ids` / `exclude_chat_ids` — scope it; omit `chat_ids` to watch
  everything. Exclusions apply first.
- `include_outgoing` — off by default, so your own messages don't match
- `notify` — desktop notification on a surfaced alert (macOS)

Criteria are prose. Write them the way you'd brief a person doing the
triage for you — say what qualifies *and* what doesn't, because near-misses
are where a judge earns its keep:

> **remote-backend-roles** — A specific open role for a backend engineer
> that is remote or remote-friendly in Europe, posted by someone hiring for
> it. Must name the company and the role. Excludes: recruiter cold-calls
> with no named company, roles requiring relocation, and anyone advertising
> their own availability.

Nothing about the subject matter is built in — the criteria supply it. The
same machinery works for job leads, release announcements, a research
field, or a resale market.

Each alert keeps the judge's verdict, severity, one-line summary, and its
reasoning — including why it rejected something. `list_alerts` hides
rejected alerts by default; pass `include_irrelevant=True` to audit them.

## Gotchas

- **Rules are forward-looking.** The watcher only sees messages that arrive
  while it's running. Use `search_messages` for history.
- **Check `monitor_status()` first.** If the watcher died, the alert tools
  keep answering from a stale database. Status is what tells you. It reports
  the watcher down when its heartbeat is over 90 seconds old.
- **Judging is best-effort.** If the API call fails, the alert is marked
  `error` and surfaced anyway — dropping a possible hit is worse than a
  false positive. Repeated auth failures disable judging for that run rather
  than retrying on every message.
- **A broken rule is skipped, not fatal.** An invalid regex logs a warning;
  the other rules keep running.

## Configuration

| Variable | Default | |
|---|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | — | required |
| `ANTHROPIC_API_KEY` | — | required for judging |
| `TELEGRAM_MCP_HOME` | `~/.telegram-mcp` | database and session files |
| `TELEGRAM_MCP_DB` | `$TELEGRAM_MCP_HOME/monitor.db` | database path |
| `TELEGRAM_MCP_SESSION` | `mcp` | server's session name |
| `TELEGRAM_MCP_WATCHER_SESSION` | `watcher` | watcher's session name |
| `TELEGRAM_MCP_JUDGE` | `1` | `0` disables judging |
| `TELEGRAM_MCP_JUDGE_MODEL` | `claude-opus-5` | judging model |
| `TELEGRAM_MCP_JUDGE_EFFORT` | `low` | `low`…`max`; raise if verdicts look shallow |
| `TELEGRAM_MCP_NOTIFY` | `1` | `0` silences desktop notifications |
| `TELEGRAM_MCP_LOG` | `INFO` | watcher log level |

## Security

- Session files under `~/.telegram-mcp/` (mode `0700`) are equivalent to
  login credentials for your Telegram account. Never commit or share one.
- The database holds the full text of every message that matched a rule.
- These are **user** sessions, not bots — the watcher sees everything you
  see. Scope rules with `chat_ids` if you'd rather not store message text
  from every chat you're in.
- The server exposes **no** Telegram write operations: nothing here can
  send, delete, or leave anything. Add write tools deliberately and
  narrowly if you need them.

## License

MIT

Country names in `skills/setup/data/country-names/` come from the
[Unicode CLDR](https://cldr.unicode.org/) project, © Unicode, Inc., under the
Unicode License v3 (included alongside the data). Regenerate them with
`python3 scripts/build_country_names.py`.
