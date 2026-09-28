"""Telegram login, driven through MCP tools instead of a terminal prompt.

Telethon's own login is an interactive prompt, which an MCP server can't use.
This splits it into two steps that survive between tool calls: request a code,
then submit it. The pending phone number and Telegram's `phone_code_hash` are
parked in the database between the two, so the flow still completes if the
server restarts in between.
"""

import os

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from . import config, db

PENDING_KEY = "login_pending"


class AuthError(RuntimeError):
    """Login could not proceed; the message is meant for the user."""


def write_api_credentials(api_id: str, api_hash: str) -> str:
    """Persist app credentials to <home>/.env, preserving any other keys."""
    home = config.ensure_home()
    path = home / ".env"

    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()
    existing["TELEGRAM_API_ID"] = str(api_id)
    existing["TELEGRAM_API_HASH"] = str(api_hash)

    body = "# Telegram app credentials from https://my.telegram.org\n"
    body += "".join(f"{k}={v}\n" for k, v in existing.items())
    path.write_text(body)
    path.chmod(0o600)

    # Make them visible to this process without a restart. Set them directly
    # rather than re-reading the file: load_env_file() deliberately never
    # overwrites an existing variable, so a second call correcting a typo
    # would otherwise keep using the old value until the server restarted.
    os.environ["TELEGRAM_API_ID"] = str(api_id)
    os.environ["TELEGRAM_API_HASH"] = api_hash
    config._env_loaded = True
    return str(path)


def build_client(session: str) -> TelegramClient:
    api_id, api_hash = config.api_credentials()
    if not api_id or not api_hash:
        raise AuthError(
            "No Telegram app credentials yet. Get an API ID and API hash from "
            "https://my.telegram.org (API development tools) and pass them to "
            "set_api_credentials first."
        )
    return TelegramClient(config.session_path(session), int(api_id), api_hash)


async def status(session: str) -> dict:
    """Whether this session exists and is signed in, and as whom."""
    path = config.session_path(session) + ".session"
    try:
        client = build_client(session)
    except AuthError as exc:
        return {"session": session, "file": path, "authorized": False,
                "error": str(exc)}

    try:
        await client.connect()
    except Exception as exc:
        return {"session": session, "file": path, "authorized": False,
                "error": f"could not connect: {exc}"}

    try:
        if not await client.is_user_authorized():
            return {"session": session, "file": path, "authorized": False}
        me = await client.get_me()
        return {
            "session": session,
            "file": path,
            "authorized": True,
            "user_id": me.id,
            "username": me.username,
            "name": " ".join(filter(None, [me.first_name, me.last_name])) or None,
            "phone": me.phone,
        }
    finally:
        await client.disconnect()


async def request_code(phone: str, session: str) -> dict:
    client = build_client(session)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            return {"ok": True, "already_authorized": True, "user_id": me.id}
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError:
            raise AuthError(
                f"Telegram rejected {phone!r}. Use international format, e.g. +14155550123."
            ) from None
        except FloodWaitError as exc:
            raise AuthError(
                f"Too many login attempts. Telegram wants you to wait {exc.seconds}s."
            ) from None
    finally:
        await client.disconnect()

    with db.session() as conn:
        db.set_state(conn, PENDING_KEY, {
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
            "session": session,
        })
    return {"ok": True, "already_authorized": False, "phone": phone}


async def submit_code(code: str, password: str | None, session: str) -> dict:
    with db.session() as conn:
        pending = db.get_state(conn, PENDING_KEY)
    if not pending or pending.get("session") != session:
        raise AuthError(
            "No login in progress for this session — call login_request_code first."
        )

    client = build_client(session)
    await client.connect()
    try:
        try:
            # Telegram sends codes as digits; users paste them with spaces or dashes.
            await client.sign_in(
                phone=pending["phone"],
                code=code.strip().replace(" ", "").replace("-", ""),
                phone_code_hash=pending["phone_code_hash"],
            )
        except SessionPasswordNeededError:
            if not password:
                raise AuthError(
                    "This account has two-factor authentication enabled. "
                    "Call login_submit_code again with the password as well as the code."
                ) from None
            await client.sign_in(password=password)
        except PhoneCodeInvalidError:
            raise AuthError("That code was not accepted. Check it and try again.") from None
        except PhoneCodeExpiredError:
            raise AuthError(
                "That code has expired. Call login_request_code again for a new one."
            ) from None

        me = await client.get_me()
        name = " ".join(filter(None, [me.first_name, me.last_name])) or me.username
    finally:
        await client.disconnect()

    with db.session() as conn:
        conn.execute("DELETE FROM state WHERE key=?", (PENDING_KEY,))

    return {
        "ok": True,
        "user_id": me.id,
        "username": me.username,
        "name": name,
        "session_file": config.session_path(session) + ".session",
    }
