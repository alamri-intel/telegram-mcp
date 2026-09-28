import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session

from conftest import GOOD_CODE
from telegram_mcp import config, server

API_ID = "1234567"
API_HASH = "0123456789abcdef0123456789abcdef"
PHONE = "+15550100"
PASSWORD = "correct horse"


def call(*steps: tuple[str, dict]) -> list[dict]:
    """Run tool calls in order over one real MCP session; return each result."""

    async def main():
        results = []
        async with create_connected_server_and_client_session(server.mcp) as client:
            for name, args in steps:
                result = await client.call_tool(name, args)
                data = result.structuredContent
                if data is None:
                    data = json.loads(result.content[0].text)
                results.append(data.get("result", data))
        return results

    return asyncio.run(main())


def saved_env() -> str:
    path = config.home() / ".env"
    return path.read_text() if path.exists() else ""


def test_credentials_are_saved_owner_only(telegram):
    [result] = call(("set_api_credentials", {"api_id": API_ID, "api_hash": API_HASH}))

    assert result["ok"] is True
    assert f"TELEGRAM_API_HASH={API_HASH}" in saved_env()
    assert (config.home() / ".env").stat().st_mode & 0o777 == 0o600


def test_malformed_credentials_are_rejected_without_saving(telegram):
    [result] = call(("set_api_credentials", {"api_id": API_ID, "api_hash": "short"}))

    assert result["ok"] is False
    assert saved_env() == ""


def test_each_session_logs_in_with_its_own_code(telegram):
    steps = [("set_api_credentials", {"api_id": API_ID, "api_hash": API_HASH})]
    for session in ("mcp", "watcher"):
        steps += [("login_request_code", {"phone": PHONE, "session": session}),
                  ("login_submit_code", {"code": GOOD_CODE, "session": session})]
    results = call(*steps)

    assert all(r["ok"] for r in results)
    assert telegram.authorized == {"mcp", "watcher"}
    assert [s for s, _ in telegram.codes_sent] == ["mcp", "watcher"]


def test_two_factor_login_asks_for_the_password_then_succeeds(telegram):
    telegram.password = PASSWORD
    results = call(
        ("set_api_credentials", {"api_id": API_ID, "api_hash": API_HASH}),
        ("login_request_code", {"phone": PHONE, "session": "watcher"}),
        ("login_submit_code", {"code": GOOD_CODE, "session": "watcher"}),
        ("login_submit_code", {"code": GOOD_CODE, "password": PASSWORD,
                               "session": "watcher"}),
    )

    assert results[2]["ok"] is False and "password" in results[2]["error"]
    assert results[3]["ok"] is True
    assert telegram.authorized == {"watcher"}


def test_wrong_code_is_reported_and_stays_logged_out(telegram):
    results = call(
        ("set_api_credentials", {"api_id": API_ID, "api_hash": API_HASH}),
        ("login_request_code", {"phone": PHONE, "session": "mcp"}),
        ("login_submit_code", {"code": "99999", "session": "mcp"}),
    )

    assert results[2]["ok"] is False and "code" in results[2]["error"].lower()
    assert telegram.authorized == set()
