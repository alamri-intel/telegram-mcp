"""Telegram login through form popups the Claude app shows the user.

Credentials, codes and the 2FA password go from the form straight to this
server, so they never appear in the conversation.
"""

import asyncio
import shutil
import sys
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


SECRET_FIELDS = {"api_hash", "password"}
DIALOG_TIMEOUT_SECONDS = 300
_GAVE_UP = "__telegram_osint_dialog_gave_up__"

# The prompt arrives as an argument, never spliced into the script, so no
# message text can inject AppleScript.
_DIALOG_SCRIPT = [
    "on run argv",
    "activate",
    'set reply to display dialog (item 1 of argv) default answer "" '
    'with title "Telegram OSINT" buttons {"Cancel", "OK"} default button "OK" '
    'hidden answer ((item 2 of argv) is "true") '
    "giving up after ((item 3 of argv) as integer)",
    'if gave up of reply then return "' + _GAVE_UP + '"',
    "return text returned of reply",
    "end run",
]


def native_dialogs_available() -> bool:
    """Whether this machine can show macOS dialog boxes for the login."""
    return sys.platform == "darwin" and shutil.which("osascript") is not None


async def run_dialog(prompt: str, hidden: bool) -> str | None:
    """Show one macOS dialog box; None if cancelled, timed out or empty."""
    args = [arg for line in _DIALOG_SCRIPT for arg in ("-e", line)]
    proc = await asyncio.create_subprocess_exec(
        "osascript", *args, prompt, "true" if hidden else "false",
        str(DIALOG_TIMEOUT_SECONDS),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    answer = out.decode().rstrip("\n")
    return None if answer in ("", _GAVE_UP) else answer


async def native_ask(message: str, schema: type[T]) -> T | None:
    """Ask for each field of `schema` in its own dialog box, secrets hidden."""
    values = {}
    for name, field in schema.model_fields.items():
        answer = await run_dialog(f"{message}\n\n{name}: {field.description}",
                                  name in SECRET_FIELDS)
        if answer is None:
            return None
        values[name] = answer.strip()
    return schema(**values)


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
