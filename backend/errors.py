from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RepoFlowError(Exception):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message
