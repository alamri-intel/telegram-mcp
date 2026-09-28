# Privacy policy — Telegram OSINT

Last updated: 2026-09-28

Telegram OSINT is an open-source plugin published by Abdul Alamri. It runs
entirely on your own computer. The publisher operates no server and receives
no data from you.

## What the plugin accesses

- **Your Telegram account.** With your login, the plugin reads your chat list
  and the messages in chats you can see, to answer your requests and to match
  your monitoring rules.
- **Your credentials.** Your Telegram app credentials (`API_ID`, `API_HASH`),
  your Telegram session, and, if you add one, your Anthropic API key.

## Where data is stored

Everything is stored locally in `~/.telegram-mcp/` on your computer: session
files, credentials (file mode `0600`), the alerts database (the text, sender
name, and sender ID of messages that matched one of your rules), and the
watcher log. Nothing is uploaded to the publisher.

## Who data is sent to

- **Telegram**, to operate your own account, under
  [Telegram's privacy policy](https://telegram.org/privacy).
- **Anthropic**, only if you turn on judging and provide an API key: the text
  of each rule-matched message and your criteria are sent to Anthropic's API
  for a verdict, under
  [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy).
  Messages that match no rule are never sent.

No analytics, telemetry, or tracking of any kind.

## Retention and deletion

Data stays on your computer until you delete it. Deleting a rule with the
plugin's tools also deletes its stored alerts; remove `~/.telegram-mcp/` to
erase everything, including your Telegram session.

## Children

The plugin is not intended for people under 18.

## Contact

Questions or concerns: open an issue at
<https://github.com/alamri-intel/telegram-mcp/issues>.
