import wave
from pathlib import Path
from fastapi.testclient import TestClient
from backend import media
from backend.main import app

client = TestClient(app)

class FastNarrator:
    def __init__(self, voice: str = "alba") -> None:
        self.voice = voice

    def generate(self, _text: str, output_path: Path) -> dict[str, object]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(b"\x00\x00" * 8_000)
        return {"status": "generated", "path": str(output_path), "duration_ms": 500, "sample_rate": 16_000}


def test_video_media_streaming_and_http_range_support(monkeypatch):
    monkeypatch.setattr(media, "PocketNarrator", FastNarrator)
    # 1. Ingest sample repository
    sample_repo_path = str(Path(__file__).parent.parent / "fixtures" / "sample_project")
    ingest_res = client.post("/api/repositories/analyse", json={"path": sample_repo_path})
    assert ingest_res.status_code == 200
    repo_id = ingest_res.json()["repository_id"]

    # 2. Render explainer video
    render_res = client.post(f"/api/repositories/{repo_id}/render-explainer")
    assert render_res.status_code == 200
    data = render_res.json()
    assert data["status"] == "rendered"
    video_url = data["video_url"]
    captions_url = data["captions_url"]

    # 3. Test Full Download (HTTP 200)
    full_res = client.get(video_url)
    assert full_res.status_code == 200
    assert full_res.headers["content-type"] == "video/mp4"
    assert full_res.headers["accept-ranges"] == "bytes"
    total_len = int(full_res.headers["content-length"])
    assert total_len > 1000

    # 4. Test Byte-Range Seeking (HTTP 206 Partial Content)
    range_res = client.get(video_url, headers={"Range": "bytes=0-499"})
    assert range_res.status_code == 206
    assert range_res.headers["content-type"] == "video/mp4"
    assert range_res.headers["content-range"] == f"bytes 0-499/{total_len}"
    assert len(range_res.content) == 500

    # 5. Test Open-Ended Range (bytes=500-)
    range2_res = client.get(video_url, headers={"Range": "bytes=500-"})
    assert range2_res.status_code == 206
    assert range2_res.headers["content-range"] == f"bytes 500-{total_len - 1}/{total_len}"
    assert len(range2_res.content) == total_len - 500

    # 6. Test Suffix Range (bytes=-300)
    range3_res = client.get(video_url, headers={"Range": "bytes=-300"})
    assert range3_res.status_code == 206
    assert range3_res.headers["content-range"] == f"bytes {total_len - 300}-{total_len - 1}/{total_len}"
    assert len(range3_res.content) == 300

    # 7. Test Captions Endpoint
    cap_res = client.get(captions_url)
    assert cap_res.status_code == 200
    assert "text/vtt" in cap_res.headers["content-type"]
    assert "WEBVTT" in cap_res.text

    # 8. Test Lesson media video fallback route
    lesson_id = data["manifest"]["lesson_id"]
    lesson_video_res = client.get(f"/api/lessons/{lesson_id}/media/video")
    assert lesson_video_res.status_code == 200
    assert lesson_video_res.headers["content-type"] == "video/mp4"

    # 9. Test Invalid/Nonexistent media returns 404
    missing_res = client.get("/api/lessons/nonexistent_video_id_9999/media/video")
    assert missing_res.status_code == 404
