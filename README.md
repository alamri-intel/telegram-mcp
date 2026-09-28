# telegram-monitor-mcp

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

## Install

**Requires [uv](https://docs.astral.sh/uv/).** It provisions the right Python
version itself, so you don't need to manage one:
`curl -LsSf https://astral.sh/uv/install.sh | sh`

As a Claude Code plugin — this is the easy path, and gives you the setup skill:

```bash
claude plugin marketplace add alamri-intel/telegram-mcp
claude plugin install telegram-monitor@telegram-monitor
```

Or from inside Claude Code: `/plugin marketplace add alamri-intel/telegram-mcp`,
then `/plugin install telegram-monitor@telegram-monitor`.

Start a new session, then run `/telegram-monitor:setup` and answer the
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

`/telegram-monitor:setup` interviews you about what you watch for and writes the
rules and criteria. `/telegram-monitor:watcher` covers starting the daemon and
working out why alerts aren't arriving.

**Reading** — talks to Telegram

`list_dialogs`, `read_messages`, `search_messages`, `unread_summary`.
`list_dialogs` is how you find the numeric chat ids for rule scopes;
`search_messages` searches history, which rules never see.

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
