from __future__ import annotations

import wave
from pathlib import Path

from backend import media
from backend.analyzer import RepositoryAnalyzer
from backend.config import Settings
from backend.storage import PkmStore
from backend.storyboard import build_storyboard

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_project"


class FakeNarrator:
    def __init__(self, voice: str) -> None:
        self.voice = voice

    def generate(self, _text: str, output_path: Path) -> dict[str, object]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(b"\x00\x00" * 8_000)
        return {"status": "generated", "path": str(output_path), "duration_ms": 500, "sample_rate": 16_000}


def test_relative_render_produces_playable_video_with_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(media, "PocketNarrator", FakeNarrator)
    monkeypatch.chdir(tmp_path)
    lesson = {
        "lesson_id": "lesson_test",
        "scenes": [
            {
                "scene_id": "scene_test",
                "title": "Test scene",
                "kind": "orientation",
                "narration": "A source-grounded test scene.",
                "source_refs": ["app.py"],
                "duration_ms": 500,
            }
        ],
    }

    manifest = media.render_lesson(lesson, Path("media") / "lesson_test")

    assert manifest["video_status"] == "playable"
    assert manifest["narration"]["status"] == "generated"
    video_path = Path(manifest["video_path"])
    assert video_path.is_absolute()
    assert video_path.is_file()
    assert (video_path.parent / "captions.vtt").is_file()


def test_storyboard_is_repository_grounded_and_scoped(tmp_path) -> None:
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    snapshot = RepositoryAnalyzer(settings, PkmStore(settings.database_path)).analyse(FIXTURE).snapshot

    storyboard = build_storyboard(snapshot, scope="feature", question="get_user", detail="detailed")

    assert storyboard["scenes"]
    assert storyboard["estimated_duration_ms"] > 0
    assert all(set(scene.get("node_ids", [])).issubset({symbol.symbol_id for symbol in snapshot.symbols}) for scene in storyboard["scenes"])
    assert any("get_user" in scene["title"] for scene in storyboard["scenes"])
