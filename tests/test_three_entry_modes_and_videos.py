import pytest
import wave
from pathlib import Path
from fastapi.testclient import TestClient

from backend import media
from backend.main import app
from backend.learning_projects import DOMAINS_CATALOG

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


def test_domains_catalog_has_comprehensive_engineering_fields():
    assert len(DOMAINS_CATALOG) >= 11
    assert "Machine Learning" in DOMAINS_CATALOG
    assert "Backend Development" in DOMAINS_CATALOG
    assert "Full-Stack Development" in DOMAINS_CATALOG
    assert "Cybersecurity" in DOMAINS_CATALOG
    assert "Cloud Computing" in DOMAINS_CATALOG


def test_mode_a_domain_project_generation():
    payload = {
        "domain": "Machine Learning",
        "learner_id": "ml_learner_001"
    }
    response = client.post("/api/projects/generate/domain", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert data["project_id"].startswith("proj_")
    assert "Machine Learning" in data.get("domain", "") or "Churn" in data.get("title", "")
    assert len(data["stages"]) >= 8
    
    # Check stage 1 structure
    s1 = data["stages"][0]
    assert s1["order"] == 1
    assert "purpose" in s1
    assert "why_it_matters" in s1
    assert len(s1["learning_objectives"]) >= 2
    assert len(s1["tasks"]) >= 1
    
    # Check stage video specification
    assert "stage_video" in s1
    assert "scenes" in s1["stage_video"]
    assert len(s1["stage_video"]["scenes"]) >= 2
    assert s1["stage_video"]["scenes"][0]["duration_ms"] > 0
    assert len(s1["stage_video"]["scenes"][0]["source_refs"]) > 0


def test_mode_b_recommend_project_based_on_learner_profile():
    # Setup learner with some existing progress/gaps
    payload = {
        "learner_id": "test_learner_recs",
        "learner_profile": {
            "learner_id": "test_learner_recs",
            "skill_level": "intermediate",
            "completed_stages": ["proj_backend_stage_1", "proj_backend_stage_2"],
            "demonstrated_skills": ["python", "fastapi"],
            "interests": ["distributed systems", "cloud"],
            "difficulty_preference": "challenging"
        }
    }
    response = client.post("/api/projects/recommend", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    
    assert "project" in data
    assert "recommendation_rationale" in data
    assert len(data["recommendation_rationale"]) > 10
    
    proj = data["project"]
    assert len(proj["stages"]) >= 8
    assert proj["stages"][0]["stage_video"] is not None


def test_mode_c_reference_inspired_original_project_generation():
    # Ingest fixture repo first using /api/repositories/analyse
    sample_repo_path = str(Path(__file__).parent.parent / "fixtures" / "sample_project")
    ingest_res = client.post("/api/repositories/analyse", json={"path": sample_repo_path})
    assert ingest_res.status_code == 200, ingest_res.text
    repo_data = ingest_res.json()
    repo_id = repo_data["repository_id"]

    # Request Mode C project generation
    payload = {
        "repository_id": repo_id,
        "learner_id": "ref_learner_001"
    }
    response = client.post("/api/projects/generate/reference", json=payload)
    assert response.status_code == 200, response.text
    proj = response.json()
    
    assert proj["reference_repository_id"] == repo_id
    assert proj.get("entry_mode") == "reference_inspired"
    assert len(proj["stages"]) >= 8
    
    # Verify concepts are transferred rather than copying code verbatim
    assert "transferred_concepts" in proj
    assert len(proj["transferred_concepts"]) > 0
    first_transfer = proj["transferred_concepts"][0]
    assert "concept" in first_transfer
    assert "reference_usage" in first_transfer
    assert "inspired_usage" in first_transfer
    assert "architecture_differences" in proj
    assert len(proj["architecture_differences"]) > 10


def test_all_seven_architecture_perspectives():
    sample_repo_path = str(Path(__file__).parent.parent / "fixtures" / "sample_project")
    ingest_res = client.post("/api/repositories/analyse", json={"path": sample_repo_path})
    assert ingest_res.status_code == 200
    repo_id = ingest_res.json()["repository_id"]
    
    views_res = client.get(f"/api/repositories/{repo_id}/views")
    assert views_res.status_code == 200, views_res.text
    views_list = views_res.json()
    assert isinstance(views_list, list)
    views_by_type = {v["view_type"]: v for v in views_list}
    
    expected_perspectives = [
        "high_level_system",
        "module_dependency",
        "component_relationships",
        "api_communication",
        "database_interactions",
        "data_flow",
        "execution_flow"
    ]
    for p in expected_perspectives:
        assert p in views_by_type, f"Perspective {p} missing from views"
        assert len(views_by_type[p]["components"]) > 0, f"Components empty for perspective {p}"


def test_stage_video_and_repo_explainer_render_apis(monkeypatch):
    monkeypatch.setattr(media, "PocketNarrator", FastNarrator)

    # 1. Ingest repo
    sample_repo_path = str(Path(__file__).parent.parent / "fixtures" / "sample_project")
    ingest_res = client.post("/api/repositories/analyse", json={"path": sample_repo_path})
    assert ingest_res.status_code == 200
    repo_id = ingest_res.json()["repository_id"]

    # 2. Render Repo Explainer Video
    repo_video_res = client.post(f"/api/repositories/{repo_id}/render-explainer")
    assert repo_video_res.status_code == 200, repo_video_res.text
    repo_video_data = repo_video_res.json()
    assert "video_path" in repo_video_data
    assert "manifest" in repo_video_data
    assert repo_video_data["manifest"]["lesson_id"] is not None
    assert len(repo_video_data["manifest"]["frames"]) >= 3
    assert len(repo_video_data["manifest"]["narration"]["segments"]) >= 3
    assert repo_video_data["video_path"] is not None

    # 3. Generate a project with stages
    gen_res = client.post("/api/projects/generate/domain", json={"domain": "Backend Development", "learner_id": "test_render"})
    assert gen_res.status_code == 200
    proj_data = gen_res.json()
    proj_id = proj_data["project_id"]
    stage_id = proj_data["stages"][0]["stage_id"]

    # 4. Render Stage Video
    stage_video_res = client.post(f"/api/learning-projects/{proj_id}/stages/{stage_id}/render-video")
    assert stage_video_res.status_code == 200, stage_video_res.text
    stage_video_data = stage_video_res.json()
    assert "video_path" in stage_video_data
    assert stage_video_data["video_path"] is not None
