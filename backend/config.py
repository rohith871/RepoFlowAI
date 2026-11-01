from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_load_dotenv: Callable[..., object] | None = None
try:
    from dotenv import load_dotenv as _imported_load_dotenv
    _load_dotenv = _imported_load_dotenv
except ImportError:  # pragma: no cover - optional local-development helper
    pass

if _load_dotenv is not None:
    _load_dotenv()


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = Path(os.getenv("REPOFLOW_STORAGE_DIR", "storage"))
    max_file_bytes: int = int(os.getenv("REPOFLOW_MAX_FILE_BYTES", "1000000"))
    max_total_bytes: int = int(os.getenv("REPOFLOW_MAX_TOTAL_BYTES", "100000000"))
    groq_api_key: str | None = os.environ.get("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", os.getenv("REPOFLOW_OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = os.getenv("OLLAMA_MODEL", os.getenv("REPOFLOW_OLLAMA_MODEL", "qwen2.5-coder:7b"))
    llm_primary_provider: str = os.getenv("LLM_PRIMARY_PROVIDER", "groq").lower()
    llm_fallback_enabled: bool = os.getenv("LLM_FALLBACK_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    groq_timeout_seconds: float = float(os.getenv("GROQ_TIMEOUT_SECONDS", "45"))
    pocket_tts_voice: str = os.getenv("REPOFLOW_POCKET_TTS_VOICE", "alba")

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "repoflow.sqlite3"

    @property
    def policy_checkpoint(self) -> Path:
        return self.storage_dir / "models" / "teaching_policy.pt"

    def ensure_directories(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "repositories").mkdir(exist_ok=True)
        (self.storage_dir / "media").mkdir(exist_ok=True)
        (self.storage_dir / "exports").mkdir(exist_ok=True)
