from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = Path(os.getenv("REPOFLOW_STORAGE_DIR", "storage"))
    max_file_bytes: int = int(os.getenv("REPOFLOW_MAX_FILE_BYTES", "1000000"))
    max_total_bytes: int = int(os.getenv("REPOFLOW_MAX_TOTAL_BYTES", "100000000"))
    ollama_url: str = os.getenv("REPOFLOW_OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("REPOFLOW_OLLAMA_MODEL", "qwen2.5-coder:7b")

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "repoflow.sqlite3"

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "repositories").mkdir(exist_ok=True)
        (self.storage_dir / "media").mkdir(exist_ok=True)
        (self.storage_dir / "exports").mkdir(exist_ok=True)
