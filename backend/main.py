import importlib.util
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.analyzer import RepositoryAnalyzer
from backend.config import Settings
from backend.ids import stable_id
from backend.learning import LearningStore, evaluate_baselines, rule_policy
from backend.lessons import plan_lesson
from backend.media import render_lesson
from backend.ollama import OllamaProvider
from backend.retrieval import EvidenceRetriever, build_deterministic_explanation
from backend.storage import PkmStore

settings = Settings()
settings.ensure_directories()
app = FastAPI(title="RepoFlow AI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
pkm_store = PkmStore(settings.database_path)
learning_store = LearningStore(settings.database_path)
analyzer = RepositoryAnalyzer(settings, pkm_store)
retriever = EvidenceRetriever()
ollama = OllamaProvider(settings.ollama_url, settings.ollama_model)


class AnalyseRequest(BaseModel):
    path: str
    repository_id: str | None = None


class LessonRequest(BaseModel):
    repository_id: str
    goal: str = Field(default="Understand the repository architecture", min_length=3, max_length=240)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class EnrollmentRequest(BaseModel):
    learner_id: str = Field(default="local-learner", min_length=1, max_length=120)


class AttemptRequest(BaseModel):
    step_id: str
    score: float = Field(ge=0, le=1)
    evidence_refs: int = Field(ge=0, le=100)


class HintRequest(BaseModel):
    step_id: str


@app.get("/health")
def health() -> dict[str, str]:
    import shutil
    torch_status = "available" if importlib.util.find_spec("torch") else "unavailable"
    return {"status": "ok", "service": "repoflow-api", "version": app.version,
            "torch": torch_status, "ffmpeg": "available" if shutil.which("ffmpeg") else "unavailable"}


@app.get("/api/repositories")
def list_repositories() -> list[dict[str, Any]]:
    return [repo.model_dump(mode="json") for repo in pkm_store.list_repositories()]


@app.post("/api/repositories/analyse")
def analyse_repository(request: AnalyseRequest) -> dict[str, Any]:
    try:
        result = analyzer.analyse(Path(request.path), request.repository_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail={"code": "PARSER_FAILED", "message": str(exc)}) from exc
    return {"repository_id": result.snapshot.revision.repository_id, "revision_id": result.snapshot.revision.pkm_revision_id,
            "analysis_run_id": result.snapshot.revision.analysis_run_id, "summary": {"files": len(result.snapshot.files), "symbols": len(result.snapshot.symbols), "facts": len(result.snapshot.facts), "relationships": len(result.snapshot.relationships), "evidence": len(result.snapshot.evidence)}, "warnings": result.warnings}


@app.get("/api/repositories/{repository_id}/pkm")
def get_pkm(repository_id: str, revision_id: str | None = None) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    return snapshot.model_dump(mode="json")


@app.get("/api/repositories/{repository_id}/source/{source_path:path}")
def get_source(repository_id: str, source_path: str, revision_id: str | None = None) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    if Path(source_path).is_absolute() or ".." in Path(source_path).parts:
        raise HTTPException(status_code=400, detail={"code": "INPUT_UNAUTHORIZED", "message": "Unsafe source path"})
    file_item = next((item for item in snapshot.files if item.path == source_path), None)
    if file_item is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source file not found in pinned revision"})
    source_file = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id / source_path
    if not source_file.is_file():
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND", "message": "Source snapshot is unavailable"})
    return {"repository_id": repository_id, "revision_id": snapshot.revision.pkm_revision_id, "path": file_item.path, "content": source_file.read_text(encoding="utf-8", errors="replace"), "content_hash": file_item.content_hash}


@app.get("/api/lessons/{lesson_id}/media")
def get_media(lesson_id: str) -> dict[str, Any]:
    manifest = settings.storage_dir / "media" / lesson_id / "manifest.json"
    if not manifest.is_file():
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "Render the lesson first"})
    import json
    return json.loads(manifest.read_text(encoding="utf-8"))


@app.post("/api/lessons")
def create_lesson(request: LessonRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(request.repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    lesson = plan_lesson(snapshot, request.goal)
    payload = {"lesson_id": lesson.lesson_id, "repository_id": lesson.repository_id, "pkm_revision_id": lesson.pkm_revision_id, "title": lesson.title, "chapters": lesson.chapters, "scenes": lesson.scenes, "steps": lesson.steps, "validation_status": lesson.validation_status}
    learning_store.save_lesson(payload)
    return payload


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str) -> dict[str, Any]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    return lesson


@app.post("/api/lessons/{lesson_id}/render")
def render_lesson_endpoint(lesson_id: str) -> dict[str, Any]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    return render_lesson(lesson, settings.storage_dir / "media" / lesson_id)


@app.post("/api/lessons/{lesson_id}/enrol")
def enrol(lesson_id: str, request: EnrollmentRequest) -> dict[str, str]:
    if learning_store.get_lesson(lesson_id) is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    enrollment_id = stable_id("enrol", lesson_id, request.learner_id)
    learning_store.create_enrollment(enrollment_id, lesson_id, request.learner_id)
    return {"enrollment_id": enrollment_id, "lesson_id": lesson_id, "learner_id": request.learner_id}


@app.get("/api/enrollments/{enrollment_id}/progress")
def progress(enrollment_id: str) -> dict[str, Any]:
    import sqlite3
    with sqlite3.connect(learning_store.path) as db:
        row = db.execute("SELECT lesson_id FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ENROLLMENT_NOT_FOUND", "message": "Enrollment not found"})
    lesson = learning_store.get_lesson(row[0])
    assert lesson is not None
    state = learning_store.get_progress(enrollment_id, lesson)
    features = learning_store.state_features(enrollment_id, lesson)
    decision = rule_policy(features, ["replay_scene", "show_source_excerpt", "hint_concept", "ask_guided_question"])
    return {**state, "learner_state": features, "policy_decision": decision.__dict__, "policy_evaluation": evaluate_baselines()}


@app.post("/api/enrollments/{enrollment_id}/attempts")
def submit_attempt(enrollment_id: str, request: AttemptRequest) -> dict[str, Any]:
    import sqlite3
    with sqlite3.connect(learning_store.path) as db:
        row = db.execute("SELECT lesson_id FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ENROLLMENT_NOT_FOUND", "message": "Enrollment not found"})
    lesson = learning_store.get_lesson(row[0])
    assert lesson is not None
    try:
        return learning_store.submit_attempt(enrollment_id, stable_id("attempt", enrollment_id, request.step_id, str(request.score), str(request.evidence_refs)), request.step_id, request.score, request.evidence_refs, lesson)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc), "message": "Step is locked or prerequisites are unmet"}) from exc


@app.post("/api/enrollments/{enrollment_id}/hints")
def hint(enrollment_id: str, request: HintRequest) -> dict[str, Any]:
    import sqlite3
    with sqlite3.connect(learning_store.path) as db:
        row = db.execute("SELECT lesson_id FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ENROLLMENT_NOT_FOUND", "message": "Enrollment not found"})
    lesson = learning_store.get_lesson(row[0])
    assert lesson is not None
    step = next((item for item in lesson["steps"] if item["step_id"] == request.step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail={"code": "STEP_NOT_FOUND", "message": "Step not found"})
    event_id = stable_id("event", enrollment_id, "hint", request.step_id)
    learning_store.record_event(event_id, enrollment_id, "hint_requested", {"step_id": request.step_id})
    return {"action": "hint_concept", "message": "Start by naming one source-backed component and cite its file path. A hint supports the task but does not complete it.", "step_id": request.step_id}


@app.post("/api/lessons/{lesson_id}/questions")
def ask_question(lesson_id: str, request: QuestionRequest) -> dict[str, Any]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    snapshot = pkm_store.get_snapshot(lesson["repository_id"], lesson["pkm_revision_id"])
    if snapshot is None:
        raise HTTPException(status_code=409, detail={"code": "PKM_NOT_FOUND", "message": "Pinned PKM revision is unavailable"})
    result = retriever.retrieve(snapshot, request.question)
    explanation = build_deterministic_explanation(snapshot, request.question, result)
    model_explanation = ollama.explain(request.question, [item.__dict__ for item in result.items]) if ollama.available() else None
    return {"question": request.question, "provider": "ollama" if model_explanation else "deterministic-fallback", "evidence_items": [item.__dict__ for item in result.items], **(model_explanation or explanation)}


@app.get("/api/learning/evaluation")
def learning_evaluation() -> dict[str, Any]:
    return evaluate_baselines()
