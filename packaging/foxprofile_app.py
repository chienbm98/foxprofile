"""Entry point of the packaged (PyInstaller) FoxProfile app.

Frozen, the app binary is also the interpreter for its helper processes, so
`process.helper_command` re-runs it as `<app> --fp-run <kind> <args...>`; that is
routed here before the UI starts. Also keeps user data out of the read-only bundle.
"""

import multiprocessing
import os
import runpy
import sys
from pathlib import Path

# kind -> module run as __main__ (see process.helper_command)
HELPERS = {
    "runner": "src.services.browser.runner",
    "cookie_tool": "src.services.browser.cookie_tool",
    "chrome_runner": "chrome_engine.runner",
    "mcp": None,  # MCP stdio server, special-cased below
    "camoufox_fetch": None,  # `camoufox fetch`, special-cased below
}


def data_dir() -> Path:
    if os.environ.get("FOXPROFILE_HOME"):
        return Path(os.environ["FOXPROFILE_HOME"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FoxProfile"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home()) / "FoxProfile"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "FoxProfile"


def prepare_environment() -> None:
    """chdir to the per-user data dir before src.core.config is imported: it
    resolves profiles.json, camoufox_data/, logs/ and .env against the CWD."""
    home = data_dir()
    home.mkdir(parents=True, exist_ok=True)
    os.chdir(home)
    os.environ.setdefault("FOXPROFILE_TOKEN_FILE", str(home / ".api_token"))
    for name in ("stdout", "stderr"):  # windowed builds have no console
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))  # noqa: SIM115


def run_helper(kind: str, args: list[str]) -> None:
    if kind not in HELPERS:
        sys.exit(f"unknown --fp-run target: {kind}")
    sys.argv = [kind, *args]
    if kind == "camoufox_fetch":
        from camoufox.__main__ import cli

        cli(["fetch"], standalone_mode=False)
        return
    if kind == "mcp":
        from src.mcp_server.server import main as mcp_main

        mcp_main()
        return
    runpy.run_module(HELPERS[kind], run_name="__main__", alter_sys=True)


def fetch_browser_if_missing() -> None:
    """Camoufox (~300 MB) is not bundled and nothing else fetches it: download it
    in the background on first start; progress goes to logs/camoufox_fetch.log."""
    import subprocess

    from camoufox.pkgman import installed_verstr

    try:
        installed_verstr()
        return
    except Exception:
        pass
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log = open(log_dir / "camoufox_fetch.log", "ab")  # noqa: SIM115
    subprocess.Popen(
        [sys.executable, "--fp-run", "camoufox_fetch"],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )


def main() -> None:
    multiprocessing.freeze_support()
    frozen = getattr(sys, "frozen", False)
    if frozen:
        prepare_environment()
    if len(sys.argv) > 2 and sys.argv[1] == "--fp-run":
        run_helper(sys.argv[2], sys.argv[3:])
        return
    if frozen:
        fetch_browser_if_missing()
    from src.main import main as run_app

    run_app()


if __name__ == "__main__":
    main()
