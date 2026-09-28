---
name: watcher
description: Start, check, or troubleshoot the Telegram watcher daemon — the background process that records alerts. Use when the user asks whether monitoring is running, why they are getting no alerts, or how to start it.
---

# The watcher daemon

The watcher is a separate process from this MCP server. It holds its own Telegram
session and does all the live listening. **No watcher, no alerts** — the monitoring
tools will keep answering from the database without complaining, so always check
status before concluding anything about coverage.

## Check first

Call `monitor_status()`. The field that matters is `watcher_running`, which is
derived from a heartbeat written every 30 seconds and goes false after 90.

If it is false, nothing has been recorded since `last_heartbeat`. Say that
plainly rather than reporting on stale alert counts.

## Starting it

The user has to run this themselves in a terminal — the first run prompts for a
phone number and login code, which needs a real terminal:

```sh
export TELEGRAM_API_ID=...      # from https://my.telegram.org
export TELEGRAM_API_HASH=...
export ANTHROPIC_API_KEY=...    # only if judging is wanted
telegram-mcp-watcher
```

After the session file exists, later starts need no interaction and can be
backgrounded:

```sh
nohup telegram-mcp-watcher > ~/.telegram-mcp/watcher.log 2>&1 &
```

## Troubleshooting

Match the symptom:

- **`watcher_running: false`** — it is not running, or it crashed. Check
  `~/.telegram-mcp/watcher.log`.
- **Running but no alerts** — check `enabled_rules` in status. Zero rules means
  nothing is being matched. Remember rules are forward-looking; nothing that
  arrived before the watcher started was ever seen.
- **Alerts stuck at `awaiting_judgement`** — the judge queue is not draining.
  Usually a missing or invalid `ANTHROPIC_API_KEY`. Check `judge_errors` and the
  log; a repeated auth failure disables judging for that run by design.
- **Everything judged `irrelevant`** — the criteria are too strict. Show the user
  `list_alerts(include_irrelevant=True)` with the reasoning so they can see what
  is being rejected and why.
- **Too many notifications** — tighten criteria first, then scope rules with
  `exclude_chat_ids`. `TELEGRAM_MCP_NOTIFY=0` keeps recording but silences
  desktop popups.
