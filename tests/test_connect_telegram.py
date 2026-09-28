import asyncio
import json

from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from conftest import GOOD_CODE
from telegram_mcp import config, server

API_ID = "1234567"
API_HASH = "0123456789abcdef0123456789abcdef"
PHONE = "+15550100"
PASSWORD = "correct horse"


def form_kind(params) -> str:
    fields = set(params.requestedSchema.get("properties", {}))
    for kind in ("api_hash", "phone", "code", "password"):
        if kind in fields:
            return kind
    raise AssertionError(f"unexpected form fields: {fields}")


def run_tool(answers: dict | None, asked: list[str] | None = None) -> dict:
    """Call connect_telegram over a real MCP session. `answers` maps a form
    kind to the content to submit, or to "cancel"; None means the client
    does not support forms at all."""

    async def on_form(context, params):
        kind = form_kind(params)
        asked.append(kind)
        answer = answers[kind]
        if answer == "cancel":
            return types.ElicitResult(action="cancel")
        return types.ElicitResult(action="accept", content=answer)

    async def main():
        callback = on_form if answers is not None else None
        async with create_connected_server_and_client_session(
            server.mcp, elicitation_callback=callback
        ) as client:
            result = await client.call_tool("connect_telegram", {})
        if result.structuredContent is not None:
            return result.structuredContent.get("result", result.structuredContent)
        return json.loads(result.content[0].text)

    return asyncio.run(main())


def new_user_answers():
    return {
        "api_hash": {"api_id": API_ID, "api_hash": API_HASH},
        "phone": {"phone": PHONE},
        "code": {"code": GOOD_CODE},
        "password": {"password": PASSWORD},
    }


def saved_credentials():
    return (config.home() / ".env").read_text() if (config.home() / ".env").exists() else ""


def test_new_user_logs_in_both_sessions_through_forms(telegram):
    asked = []
    result = run_tool(new_user_answers(), asked)

    assert result["ok"] is True
    assert telegram.authorized == {"mcp", "watcher"}
    assert asked == ["api_hash", "phone", "code", "code"]
    assert f"TELEGRAM_API_HASH={API_HASH}" in saved_credentials()


def test_saved_credentials_skip_the_credentials_form(telegram):
    from telegram_mcp import auth
    auth.write_api_credentials(API_ID, API_HASH)
    asked = []
    run_tool(new_user_answers(), asked)

    assert asked == ["phone", "code", "code"]


def test_two_factor_account_is_asked_for_its_password(telegram):
    telegram.password = PASSWORD
    asked = []
    result = run_tool(new_user_answers(), asked)

    assert result["ok"] is True
    assert telegram.authorized == {"mcp", "watcher"}
    assert asked == ["api_hash", "phone", "code", "password", "code", "password"]


def test_cancelling_saves_nothing(telegram):
    answers = new_user_answers() | {"api_hash": "cancel"}
    result = run_tool(answers, [])

    assert result["ok"] is False
    assert saved_credentials() == ""
    assert telegram.codes_sent == []


def test_wrong_code_reports_an_error_and_stays_logged_out(telegram):
    answers = new_user_answers() | {"code": {"code": "99999"}}
    result = run_tool(answers, [])

    assert result["ok"] is False
    assert "code" in result["error"].lower()
    assert telegram.authorized == set()


def test_malformed_api_hash_is_rejected_without_saving(telegram):
    answers = new_user_answers() | {"api_hash": {"api_id": API_ID, "api_hash": "short"}}
    result = run_tool(answers, [])

    assert result["ok"] is False
    assert saved_credentials() == ""


def test_already_logged_in_asks_nothing(telegram):
    from telegram_mcp import auth
    auth.write_api_credentials(API_ID, API_HASH)
    telegram.authorized = {"mcp", "watcher"}
    asked = []
    result = run_tool(new_user_answers(), asked)

    assert result["ok"] is True
    assert asked == []
    assert telegram.codes_sent == []


def test_result_never_repeats_secrets(telegram):
    telegram.password = PASSWORD
    result = json.dumps(run_tool(new_user_answers(), []))

    for secret in (API_HASH, GOOD_CODE, PASSWORD):
        assert secret not in result


def test_client_without_forms_is_told_to_use_the_chat_login(telegram, monkeypatch):
    from telegram_mcp import connect
    monkeypatch.setattr(connect, "native_dialogs_available", lambda: False)
    result = run_tool(None)

    assert result["ok"] is False
    assert "login_request_code" in result["fallback"]
    assert telegram.codes_sent == []
