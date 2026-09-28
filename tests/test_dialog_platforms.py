import asyncio

import pytest

from telegram_mcp import connect

TRICKY = "Enter code\"; Remove-Item C:\\ -Recurse; '$(whoami)'"


def on(monkeypatch, platform, tools=(), env=None):
    monkeypatch.setattr(connect.sys, "platform", platform)
    monkeypatch.setattr(connect.shutil, "which",
                        lambda name: f"/bin/{name}" if name in tools else None)
    for key in ("DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("platform, tools, env, expected", [
    ("darwin", ["osascript"], None, "osascript"),
    ("win32", ["powershell"], None, "powershell"),
    ("linux", ["zenity"], {"DISPLAY": ":0"}, "zenity"),
    ("linux", ["zenity"], None, None),
    ("linux", [], {"DISPLAY": ":0"}, None),
])
def test_picks_the_dialog_tool_for_the_system(monkeypatch, platform, tools, env, expected):
    on(monkeypatch, platform, tools, env)
    assert connect.dialog_backend() == expected


def test_windows_passes_the_prompt_outside_the_command(monkeypatch):
    argv, env = connect.dialog_command("powershell", TRICKY, hidden=False)

    assert all(TRICKY not in arg for arg in argv)
    assert env["TELEGRAM_OSINT_PROMPT"] == TRICKY


def test_windows_hides_secret_input(monkeypatch):
    _, shown = connect.dialog_command("powershell", "code", hidden=False)
    _, hidden = connect.dialog_command("powershell", "password", hidden=True)

    assert (shown["TELEGRAM_OSINT_HIDDEN"], hidden["TELEGRAM_OSINT_HIDDEN"]) == ("0", "1")


def test_linux_hides_secret_input():
    shown, _ = connect.dialog_command("zenity", "code", hidden=False)
    hidden, _ = connect.dialog_command("zenity", "password", hidden=True)

    assert "--hide-text" not in shown and "--hide-text" in hidden


@pytest.mark.parametrize("backend", ["osascript", "powershell", "zenity"])
def test_prompt_is_never_spliced_into_a_script(backend):
    argv, env = connect.dialog_command(backend, TRICKY, hidden=False)
    scripts = [arg for arg in argv if "\n" in arg or len(arg) > 200]
    assert all(TRICKY not in script for script in scripts)


@pytest.mark.parametrize("code, out, expected", [
    (0, "12345\n", "12345"),
    (0, "﻿12345\r\n", "12345"),  # Windows PowerShell may prefix a BOM
    (1, "", None),
    (5, "", None),
    (0, "", None),
])
def test_dialog_answer_or_none(monkeypatch, code, out, expected):
    async def fake_exec(argv, env):
        return code, out
    monkeypatch.setattr(connect, "dialog_backend", lambda: "zenity")
    monkeypatch.setattr(connect, "_exec", fake_exec)

    assert asyncio.run(connect.run_dialog("Code?", hidden=False)) == expected
