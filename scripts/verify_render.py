from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import json
from backend.config import Settings
from backend.storage import PkmStore
from backend.analyzer import RepositoryAnalyzer
from backend.main import _build_video_explanation, VideoRequest
from backend.media import render_lesson

storage_dir = Path("storage_demo")
settings = Settings(storage_dir=storage_dir)
settings.ensure_directories()
store = PkmStore(settings.database_path)
fixture = Path("fixtures/sample_project")

res = RepositoryAnalyzer(settings, store).analyse(fixture)
repo_id = res.snapshot.revision.repository_id
print(f"Analysed repo: {repo_id}")

explanation = _build_video_explanation(repo_id, VideoRequest(scope="repository", detail="detailed"))
lesson_id = explanation["lesson_id"]
media_out = storage_dir / "media" / lesson_id

manifest = render_lesson(explanation, media_out, voice=settings.pocket_tts_voice)
print("Manifest video status:", manifest.get("video_status"))
print("Renderer used:", manifest.get("renderer"))
print("Captions count:", len(manifest.get("captions", [])))
print("Transcript validation score:", manifest.get("transcript_validation", {}).get("quality_score"))
video_file = media_out / "lesson.mp4"
print("MP4 exists:", video_file.is_file(), "Size:", video_file.stat().st_size if video_file.is_file() else 0)
