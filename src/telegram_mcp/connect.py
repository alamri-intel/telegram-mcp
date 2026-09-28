"""Telegram login through form popups the Claude app shows the user.

Credentials, codes and the 2FA password go from the form straight to this
server, so they never appear in the conversation.
"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, Field

from . import auth, config

T = TypeVar("T", bound=BaseModel)
Ask = Callable[[str, type[T]], Awaitable[T | None]]

SESSION_PURPOSE = {
    "mcp": "reading and searching your chats",
    "watcher": "background monitoring",
}


class Credentials(BaseModel):
    api_id: str = Field(description="App api_id (a number) from my.telegram.org → API development tools")
    api_hash: str = Field(description="App api_hash (32 characters) from the same page")


class Phone(BaseModel):
    phone: str = Field(description="Phone number of your Telegram account, international format, e.g. +14155550123")


class Code(BaseModel):
    code: str = Field(description="The login code Telegram just sent you")


class Password(BaseModel):
    password: str = Field(description="Your Telegram two-step verification password")


def _cancelled() -> dict:
    return {"ok": False, "cancelled": True, "note": "Stopped at the user's request; nothing more was changed."}


async def run(ask: Ask, sessions: list[str]) -> dict:
    api_id, api_hash = config.api_credentials()
    if not (api_id and api_hash):
        creds = await ask(
            "Connect Telegram. Enter your app credentials from my.telegram.org "
            "(API development tools). They identify the app, not your account.",
            Credentials,
        )
        if creds is None:
            return _cancelled()
        error = auth.validate_api_credentials(creds.api_id, creds.api_hash)
        if error:
            return {"ok": False, "error": error, "next": "Run connect_telegram again."}
        auth.write_api_credentials(creds.api_id.strip(), creds.api_hash.strip())

    todo = [s for s in sessions if not (await auth.status(s))["authorized"]]
    if not todo:
        return {"ok": True, "already_logged_in": sessions}

    phone = await ask("Which Telegram account should this log in to?", Phone)
    if phone is None:
        return _cancelled()

    logged_in, account = [], None
    for session in todo:
        purpose = SESSION_PURPOSE.get(session, session)
        try:
            sent = await auth.request_code(phone.phone.strip(), session)
            if sent.get("already_authorized"):
                logged_in.append(session)
                continue
            code = await ask(
                f"Telegram sent a login code to your Telegram app. Enter it to "
                f"connect the '{session}' session ({purpose}).",
                Code,
            )
            if code is None:
                return _cancelled()
            try:
                me = await auth.submit_code(code.code, None, session)
            except auth.PasswordNeeded:
                password = await ask(
                    f"This account has two-step verification. Enter your Telegram "
                    f"password for the '{session}' session.",
                    Password,
                )
                if password is None:
                    return _cancelled()
                me = await auth.submit_password(password.password, session)
        except auth.AuthError as exc:
            return {"ok": False, "error": str(exc), "logged_in": logged_in,
                    "next": "Run connect_telegram again; sessions already connected are skipped."}
        logged_in.append(session)
        account = me.get("username") or me.get("name")

    return {"ok": True, "logged_in": logged_in, "account": account}
