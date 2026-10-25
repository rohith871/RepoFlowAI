from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


class PocketNarrator:
    """Lazy Pocket TTS narrator using the built-in alba voice."""

    _lock = threading.Lock()
    _model: Any = None
    _voice: Any = None

    def __init__(self, voice: str = "alba"):
        self.voice = voice

    def available(self) -> bool:
        try:
            import pocket_tts  # noqa: F401
            import scipy  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self) -> tuple[Any, Any]:
        if self._model is not None and self._voice is not None:
            return self._model, self._voice
        with self._lock:
            if self._model is None:
                from pocket_tts import TTSModel
                self._model = TTSModel.load_model()
                self._voice = self._model.get_state_for_audio_prompt(self.voice)
        return self._model, self._voice

    def generate(self, text: str, output_path: Path) -> dict[str, Any]:
        if not self.available():
            return {"status": "unavailable", "reason": "Pocket TTS and scipy are not installed"}
        import numpy as np
        from scipy.io.wavfile import write

        model, voice = self._load()
        audio = model.generate_audio(voice, text, max_tokens=max(80, min(800, len(text) * 3)))
        values = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        values = np.asarray(values).reshape(-1)
        peak = float(np.max(np.abs(values))) if values.size else 0.0
        if peak > 1.0:
            values = values / peak
        pcm = np.clip(values * 32767, -32768, 32767).astype(np.int16)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write(output_path, int(model.sample_rate), pcm)
        return {"status": "generated", "path": str(output_path), "sample_rate": int(model.sample_rate), "duration_ms": int(len(pcm) * 1000 / model.sample_rate)}
