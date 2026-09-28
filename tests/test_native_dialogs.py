import asyncio

from conftest import GOOD_CODE
from telegram_mcp import connect
from test_connect_telegram import API_HASH, API_ID, PHONE, run_tool


class FakeDialogs:
    """Stands in for the macOS dialog boxes: records each prompt and
    answers from a script, or cancels on None."""

    def __init__(self, answers: list[str | None]):
        self.answers = list(answers)
        self.shown: list[tuple[str, bool]] = []

    async def __call__(self, prompt: str, hidden: bool) -> str | None:
        self.shown.append((prompt, hidden))
        return self.answers.pop(0)


def test_asks_each_field_in_turn_and_builds_the_answer(monkeypatch):
    dialogs = FakeDialogs([API_ID, API_HASH])
    monkeypatch.setattr(connect, "run_dialog", dialogs)

    creds = asyncio.run(connect.native_ask("Connect Telegram.", connect.Credentials))

    assert (creds.api_id, creds.api_hash) == (API_ID, API_HASH)
    assert len(dialogs.shown) == 2
    assert "api_id" in dialogs.shown[0][0] and "api_hash" in dialogs.shown[1][0]


def test_secret_fields_are_typed_hidden(monkeypatch):
    dialogs = FakeDialogs([API_ID, API_HASH])
    monkeypatch.setattr(connect, "run_dialog", dialogs)

    asyncio.run(connect.native_ask("Connect Telegram.", connect.Credentials))

    assert [hidden for _, hidden in dialogs.shown] == [False, True]


def test_cancelling_a_dialog_stops_asking(monkeypatch):
    dialogs = FakeDialogs([None, API_HASH])
    monkeypatch.setattr(connect, "run_dialog", dialogs)

    result = asyncio.run(connect.native_ask("Connect Telegram.", connect.Credentials))

    assert result is None
    assert len(dialogs.shown) == 1


def test_dialog_script_can_be_passed_as_process_arguments():
    # Process arguments can't carry NUL bytes; osascript would never start.
    assert all("\x00" not in line for line in connect._DIALOG_SCRIPT)


def test_app_without_forms_logs_in_through_native_dialogs(telegram, monkeypatch):
    dialogs = FakeDialogs([API_ID, API_HASH, PHONE, GOOD_CODE, GOOD_CODE])
    monkeypatch.setattr(connect, "native_dialogs_available", lambda: True)
    monkeypatch.setattr(connect, "run_dialog", dialogs)

    result = run_tool(None)

    assert result["ok"] is True
    assert telegram.authorized == {"mcp", "watcher"}
    assert len(dialogs.shown) == 5
