import os
from types import SimpleNamespace

import pytest
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from telegram_mcp import auth, config, db

GOOD_CODE = "12345"


class FakeTelegram:
    """Telegram's side of a login: which sessions are signed in, and the
    account's code and 2FA password. Stands in for the network only."""

    def __init__(self):
        self.authorized: set[str] = set()
        self.awaiting_password: set[str] = set()
        self.password: str | None = None
        self.codes_sent: list[tuple[str, str]] = []

    def client_class(self):
        telegram = self

        class FakeClient:
            def __init__(self, session_path, api_id, api_hash):
                self.session = os.path.basename(session_path)

            async def connect(self):
                pass

            async def disconnect(self):
                pass

            async def is_user_authorized(self):
                return self.session in telegram.authorized

            async def get_me(self):
                return SimpleNamespace(id=42, username="tester", first_name="Test",
                                       last_name=None, phone="15550100")

            async def send_code_request(self, phone):
                telegram.codes_sent.append((self.session, phone))
                return SimpleNamespace(phone_code_hash="hash")

            async def sign_in(self, phone=None, code=None, phone_code_hash=None,
                              password=None):
                if password is not None:
                    if self.session not in telegram.awaiting_password:
                        raise AssertionError("password sent before the code")
                    if password != telegram.password:
                        raise PasswordHashInvalidError(request=None)
                    telegram.awaiting_password.discard(self.session)
                    telegram.authorized.add(self.session)
                    return
                if code != GOOD_CODE:
                    raise PhoneCodeInvalidError(request=None)
                if telegram.password:
                    telegram.awaiting_password.add(self.session)
                    raise SessionPasswordNeededError(request=None)
                telegram.authorized.add(self.session)

        return FakeClient


@pytest.fixture
def telegram(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_HOME, str(tmp_path))
    monkeypatch.delenv("TELEGRAM_MCP_DB", raising=False)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    monkeypatch.setattr(config, "_env_loaded", False)
    db.init()
    fake = FakeTelegram()
    monkeypatch.setattr(auth, "TelegramClient", fake.client_class())
    return fake
