"""Paths and environment configuration.

Nothing is stored next to the installed package, so the server behaves the
same whether it was installed with uvx, pipx, pip -e, or run from a checkout.
Everything resolves under one home directory that the user can relocate.
"""

import os
from pathlib import Path

ENV_HOME = "TELEGRAM_MCP_HOME"
DEFAULT_HOME = Path.home() / ".telegram-mcp"


def home() -> Path:
    """Directory holding the database and session files."""
    return Path(os.environ.get(ENV_HOME) or DEFAULT_HOME).expanduser()


def ensure_home() -> Path:
    """Create the home directory if needed. It holds Telegram session files,
    which are login credentials, so it is owner-only."""
    path = home()
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass  # non-POSIX filesystem; not worth failing startup over
    return path


def db_path() -> Path:
    override = os.environ.get("TELEGRAM_MCP_DB")
    if override:
        return Path(override).expanduser()
    return ensure_home() / "monitor.db"


def session_path(name: str) -> str:
    """Absolute path for a Telethon session, minus the .session suffix that
    Telethon appends itself."""
    return str(ensure_home() / name)


_env_loaded = False


def load_env_file() -> None:
    """Read KEY=value lines from <home>/.env into the environment.

    The shell always wins: a variable already set is never overwritten, so
    `TELEGRAM_API_ID=... telegram-mcp-watcher` overrides the file. Saves every
    process from needing the same exports.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    path = home() / ".env"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def api_credentials() -> tuple[str | None, str | None]:
    load_env_file()
    return os.environ.get("TELEGRAM_API_ID"), os.environ.get("TELEGRAM_API_HASH")
