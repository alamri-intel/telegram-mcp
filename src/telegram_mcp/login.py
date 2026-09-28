"""One-time interactive Telegram login.

Telethon needs a phone number and the code Telegram sends, which only works
from a real terminal. This does that once and exits; afterwards every other
command reuses the saved session without prompting.

Run with `telegram-mcp-login`.
"""

import asyncio
import os
import sys

from telethon import TelegramClient

from . import config


def entity_name(me) -> str:
    return " ".join(filter(None, [me.first_name, me.last_name])) or (
        me.username or str(me.id)
    )


async def run(session: str) -> int:
    api_id, api_hash = config.api_credentials()
    if not api_id or not api_hash:
        print(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH first — either in your\n"
            f"shell, or in {config.home() / '.env'} as:\n\n"
            "    TELEGRAM_API_ID=...\n"
            "    TELEGRAM_API_HASH=...\n\n"
            "Get them from https://my.telegram.org (API development tools).",
            file=sys.stderr,
        )
        return 1

    path = config.session_path(session)
    client = TelegramClient(path, int(api_id), api_hash)

    print(f"Logging in — session will be saved to {path}.session")
    await client.start()
    me = await client.get_me()
    await client.disconnect()

    print(f"\nLogged in as {entity_name(me)}.")
    print("You can now run `telegram-mcp-watcher` without being prompted.")
    return 0


def main() -> None:
    # Default to the watcher's session, since that is the one that has to be
    # logged in for monitoring to work at all.
    session = os.environ.get("TELEGRAM_MCP_WATCHER_SESSION", "watcher")
    if len(sys.argv) > 1:
        session = sys.argv[1]
    try:
        sys.exit(asyncio.run(run(session)))
    except KeyboardInterrupt:
        print("\ncancelled.")
        sys.exit(130)


if __name__ == "__main__":
    main()
