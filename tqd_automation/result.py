from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PostResult:
    status: Literal["published", "blocked", "needs_agent", "awaiting_approval", "failed", "dry_run"]
    url: str = ""
    evidence: str = ""
    detail: str = ""
    snapshot: str = ""
