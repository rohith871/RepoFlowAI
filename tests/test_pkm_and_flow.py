from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_project"


def test_analyse_retrieval_lesson_and_locked_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REPOFLOW_STORAGE_DIR", str(tmp_path / "storage"))
    # The app's stores are created at import time; use a fresh direct analyzer/store for the PKM contract.
    from backend.analyzer import RepositoryAnalyzer
    from backend.config import Settings
    from backend.retrieval import EvidenceRetriever
    from backend.storage import PkmStore

    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    store = PkmStore(settings.database_path)
    result = RepositoryAnalyzer(settings, store).analyse(FIXTURE)
    assert len(result.snapshot.files) >= 3
    assert any(f.fact_type == "api_route" for f in result.snapshot.facts) is False
    assert any(s.name == "get_user" for s in result.snapshot.symbols)
    assert result.snapshot.evidence
    retrieval = EvidenceRetriever().retrieve(result.snapshot, "get_user load_user")
    assert retrieval.items
    assert all(item.evidence_ids for item in retrieval.items)


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
