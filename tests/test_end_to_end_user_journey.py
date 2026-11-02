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


def test_repository_to_video_complete_user_journey(monkeypatch):
    """Step 1 to Step 5: Add repo -> Ingest -> Explore 7 perspectives -> Render Explainer -> Watch with HTTP 206 Range seeking."""
    monkeypatch.setattr(media, "PocketNarrator", FastNarrator)

    # Step 1 & 2: Add and Analyze Repository
    sample_repo_path = str(Path(__file__).parent.parent / "fixtures" / "sample_project")
    ingest_res = client.post("/api/repositories/analyse", json={"path": sample_repo_path})
    assert ingest_res.status_code == 200, ingest_res.text
    repo_data = ingest_res.json()
    repo_id = repo_data["repository_id"]
    assert repo_data["summary"]["files"] > 0
    assert repo_data["summary"]["symbols"] > 0

    # Step 3: Explore 7 Architecture Views & Flows
    views_res = client.get(f"/api/repositories/{repo_id}/views")
    assert views_res.status_code == 200
    views_list = views_res.json()
    assert isinstance(views_list, list)
    assert len(views_list) >= 7

    flows_res = client.get(f"/api/repositories/{repo_id}/flows")
    assert flows_res.status_code == 200
    flows_list = flows_res.json()
    assert len(flows_list) > 0

    # Step 4: Generate Repository Explainer Video
    render_res = client.post(f"/api/repositories/{repo_id}/render-explainer")
    assert render_res.status_code == 200, render_res.text
    video_info = render_res.json()
    assert video_info["status"] == "rendered"
    assert "video_url" in video_info
    assert "captions_url" in video_info

    # Step 5: Watch Explainer Video via Direct HTTP & Range Streaming
    explainer_url = video_info["video_url"]
    captions_url = video_info["captions_url"]

    # HTTP 200 Full Stream
    full_stream = client.get(explainer_url)
    assert full_stream.status_code == 200
    assert full_stream.headers["content-type"] == "video/mp4"
    assert full_stream.headers["accept-ranges"] == "bytes"
    total_size = int(full_stream.headers["content-length"])
    assert total_size > 1000

    # HTTP 206 Byte-Range Seeking
    range_stream = client.get(explainer_url, headers={"Range": "bytes=0-1024"})
    assert range_stream.status_code == 206
    assert range_stream.headers["content-range"] == f"bytes 0-1024/{total_size}"
    assert len(range_stream.content) == 1025

    # Captions WebVTT
    cap_res = client.get(captions_url)
    assert cap_res.status_code == 200
    assert "text/vtt" in cap_res.headers["content-type"]
    assert "WEBVTT" in cap_res.text


def test_learning_stage_video_workflow_and_watch_current_step_video(monkeypatch):
    """Learning Workspace: Generate project -> Stage Video Render -> Watch Current Step Video -> Tasks & DQN."""
    monkeypatch.setattr(media, "PocketNarrator", FastNarrator)

    # 1. Generate Domain Project (Backend Development)
    proj_res = client.post("/api/projects/generate/domain", json={"domain": "Backend Development", "learner_id": "journey_learner"})
    assert proj_res.status_code == 200
    project = proj_res.json()
    project_id = project["project_id"]
    stage = project["stages"][0]
    stage_id = stage["stage_id"]

    # 2. Render Stage Video
    stage_render_res = client.post(f"/api/learning-projects/{project_id}/stages/{stage_id}/render-video")
    assert stage_render_res.status_code == 200, stage_render_res.text
    stage_video_info = stage_render_res.json()
    assert stage_video_info["status"] == "rendered"
    assert "video_url" in stage_video_info
    assert "captions_url" in stage_video_info

    # 3. Watch Current Step Video via Dedicated Endpoint
    stage_video_url = stage_video_info["video_url"]
    stage_captions_url = stage_video_info["captions_url"]

    v_res = client.get(stage_video_url)
    assert v_res.status_code == 200
    assert v_res.headers["content-type"] == "video/mp4"
    assert v_res.headers["accept-ranges"] == "bytes"
    stage_v_size = int(v_res.headers["content-length"])

    # HTTP 206 Partial Content Range Seeking
    seek_res = client.get(stage_video_url, headers={"Range": "bytes=0-512"})
    assert seek_res.status_code == 206
    assert seek_res.headers["content-range"] == f"bytes 0-512/{stage_v_size}"
    assert len(seek_res.content) == 513

    # Captions
    c_res = client.get(stage_captions_url)
    assert c_res.status_code == 200
    assert "text/vtt" in c_res.headers["content-type"]

    # 4. Verify Project State Persistence (video_generation_status == 'ready_to_watch')
    get_proj_res = client.get(f"/api/learning-projects/{project_id}")
    assert get_proj_res.status_code == 200
    updated_stage = get_proj_res.json()["stages"][0]
    assert updated_stage["video_generation_status"] == "ready_to_watch"
    assert updated_stage["video_path"] is not None

    # 5. Complete Task and verify Adaptive Tutor Feedback
    task_id = updated_stage["tasks"][0]["task_id"]
    submit_res = client.post(
        f"/api/learning-projects/{project_id}/tasks/{task_id}/submit",
        json={"solution_code": "def user_route(): return {'status': 'ok'}", "learner_id": "journey_learner"}
    )
    assert submit_res.status_code == 200
    sub_data = submit_res.json()
    assert "evaluation_feedback" in sub_data
