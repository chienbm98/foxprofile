"""Agent-driven posting on top of the FoxProfile REST API: judge, safety gates and macros."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Where the ledger, lockouts, kill switch and logs live.

    Anchored to the repo root rather than the working directory: a scheduler that starts in another
    folder would otherwise read an empty ledger and let every guard pass.
    """
    return Path(os.getenv("TQD_AUTOMATION_DIR") or REPO_ROOT / "automation_data")
