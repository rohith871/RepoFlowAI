import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.adaptive_model import TrainedTeachingPolicy
from backend.analyzer import RepositoryAnalyzer
from backend.app_store import AppStore
from backend.config import Settings
from backend.ids import stable_id
from backend.jobs import JobManager
from backend.learning import LearningStore, evaluate_baselines, rule_policy
from backend.lessons import plan_lesson
from backend.llm import LLMRouter
from backend.media import render_lesson
from backend.narration import PocketNarrator
from backend.retrieval import EvidenceRetriever, build_deterministic_explanation
from backend.storage import PkmStore
from backend.storyboard import build_storyboard, validate_storyboard

settings = Settings()
settings.ensure_directories()
app = FastAPI(title="RepoFlow AI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
pkm_store = PkmStore(settings.database_path)
learning_store = LearningStore(settings.database_path)
app_store = AppStore(settings.database_path)
analyzer = RepositoryAnalyzer(settings, pkm_store)
retriever = EvidenceRetriever()
llm = LLMRouter(settings)
trained_policy = TrainedTeachingPolicy(settings.policy_checkpoint)
narrator = PocketNarrator(settings.pocket_tts_voice)
jobs = JobManager(app_store)


class AnalyseRequest(BaseModel):
    path: str
    repository_id: str | None = None


class GithubImportRequest(BaseModel):
    url: str = Field(min_length=15, max_length=500)
    description: str = Field(default="", max_length=500)


class JobRequest(BaseModel):
    repository_id: str | None = None
    lesson_id: str | None = None


class LessonRequest(BaseModel):
    repository_id: str
    goal: str = Field(default="Understand the repository architecture", min_length=3, max_length=240)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class VideoRequest(BaseModel):
    scope: Literal["repository", "module", "feature", "question", "files"] = "repository"
    question: str = Field(default="", max_length=1000)
    detail: Literal["summary", "detailed"] = "summary"
    title: str | None = Field(default=None, max_length=180)


class EnrollmentRequest(BaseModel):
    learner_id: str = Field(default="local-learner", min_length=1, max_length=120)


class AttemptRequest(BaseModel):
    step_id: str
    score: float = Field(ge=0, le=1)
    evidence_refs: int = Field(ge=0, le=100)


class HintRequest(BaseModel):
    step_id: str


class CheckpointResponseRequest(BaseModel):
    checkpoint_id: str
    selected_option_id: str


@app.get("/health")
def health() -> dict[str, str]:
    import shutil
    torch_status = "available" if importlib.util.find_spec("torch") else "unavailable"
    llm_status = llm.status()
    return {"status": "ok", "service": "repoflow-api", "version": app.version,
            "torch": torch_status, "ffmpeg": "available" if shutil.which("ffmpeg") else "managed-or-unavailable",
            "ollama": "available" if llm_status["ollama_available"] else "unavailable", "ollama_model": settings.ollama_model,
            "pocket_tts": "available" if narrator.available() else "unavailable", "policy": trained_policy.version,
            "llm_provider": settings.llm_primary_provider, "llm_model_configured": settings.groq_model if settings.llm_primary_provider == "groq" else settings.ollama_model,
            "groq": "configured" if llm_status["groq_configured"] else "missing-key",
            "fallback_enabled": str(settings.llm_fallback_enabled).lower()}


@app.get("/api/repositories")
def list_repositories() -> list[dict[str, Any]]:
    stored = {item["repository_id"]: item for item in app_store.list_repositories()}
    output: list[dict[str, Any]] = []
    for repo in pkm_store.list_repositories():
        item = stored.get(repo.repository_id, repo.model_dump(mode="json"))
        snapshot = pkm_store.get_snapshot(repo.repository_id)
        if snapshot:
            item = {**item, "name": repo.name, "latest_published_revision_id": repo.latest_published_revision_id,
                    "summary": {"files": len(snapshot.files), "symbols": len(snapshot.symbols), "facts": len(snapshot.facts), "relationships": len(snapshot.relationships), "evidence": len(snapshot.evidence)}}
        output.append(item)
    return output


@app.post("/api/repositories/analyse")
def analyse_repository(request: AnalyseRequest) -> dict[str, Any]:
    try:
        result = analyzer.analyse(Path(request.path), request.repository_id)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail={"code": "PARSER_FAILED", "message": str(exc)}) from exc
    app_store.upsert_repository(result.snapshot.revision.repository_id, str(Path(request.path).resolve()), languages=sorted({item.language for item in result.snapshot.files if item.language != "unsupported"}), status="ready")
    return {"repository_id": result.snapshot.revision.repository_id, "revision_id": result.snapshot.revision.pkm_revision_id,
            "analysis_run_id": result.snapshot.revision.analysis_run_id, "summary": {"files": len(result.snapshot.files), "symbols": len(result.snapshot.symbols), "facts": len(result.snapshot.facts), "relationships": len(result.snapshot.relationships), "evidence": len(result.snapshot.evidence)}, "warnings": result.warnings}


@app.post("/api/repositories/analyse-job", status_code=202)
def analyse_repository_job(request: AnalyseRequest) -> dict[str, Any]:
    def work(job_id: str) -> dict[str, Any]:
        app_store.update_job(job_id, progress=.1, stage="scanning", message="Scanning repository files")
        result = analyzer.analyse(Path(request.path), request.repository_id)
        app_store.upsert_repository(result.snapshot.revision.repository_id, str(Path(request.path).resolve()), languages=sorted({item.language for item in result.snapshot.files if item.language != "unsupported"}), status="ready")
        app_store.update_job(job_id, progress=.95, stage="persisting", message="Publishing immutable knowledge revision")
        return {"repository_id": result.snapshot.revision.repository_id, "revision_id": result.snapshot.revision.pkm_revision_id, "summary": {"files": len(result.snapshot.files), "symbols": len(result.snapshot.symbols), "facts": len(result.snapshot.facts), "relationships": len(result.snapshot.relationships), "evidence": len(result.snapshot.evidence)}, "warnings": result.warnings}
    return {"job_id": jobs.submit("analyse", request.model_dump(), work)}


@app.post("/api/repositories/{repository_id}/reindex-job", status_code=202)
def reindex_repository_job(repository_id: str) -> dict[str, str]:
    metadata = app_store.get_repository(repository_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail={"code": "REPOSITORY_NOT_FOUND", "message": "Repository not found"})
    source_path = Path(metadata["source_path"])
    if not source_path.is_dir():
        raise HTTPException(status_code=409, detail={"code": "SOURCE_UNAVAILABLE", "message": "Repository source folder is unavailable"})

    def work(job_id: str) -> dict[str, Any]:
        app_store.upsert_repository(repository_id, str(source_path), source_url=metadata.get("source_url"), description=metadata.get("description", ""), status="indexing")
        app_store.update_job(job_id, progress=.1, stage="scanning", message="Re-scanning repository files")
        result = analyzer.analyse(source_path, repository_id)
        app_store.update_job(job_id, progress=.95, stage="persisting", message="Publishing immutable knowledge revision")
        app_store.upsert_repository(repository_id, str(source_path), source_url=metadata.get("source_url"), description=metadata.get("description", ""), languages=sorted({item.language for item in result.snapshot.files if item.language != "unsupported"}), status="ready")
        return {"repository_id": repository_id, "revision_id": result.snapshot.revision.pkm_revision_id, "warnings": result.warnings}

    return {"job_id": jobs.submit("reindex", {"repository_id": repository_id}, work)}


@app.post("/api/repositories/import/github", status_code=202)
def import_github(request: GithubImportRequest) -> dict[str, Any]:
    parsed = urlparse(request.url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise HTTPException(status_code=400, detail={"code": "INVALID_GITHUB_URL", "message": "Only https://github.com/<owner>/<repo> URLs are supported"})
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2 or any(part in {".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail={"code": "INVALID_GITHUB_URL", "message": "GitHub URL must include owner and repository"})
    owner, repo_name = parts[:2]
    repo_name = repo_name.removesuffix(".git")
    repo_id = stable_id("repo", request.url)
    destination = settings.storage_dir / "repositories" / repo_id / "source"
    app_store.upsert_repository(repo_id, str(destination), source_url=request.url, description=request.description, status="indexing")

    def work(job_id: str) -> dict[str, Any]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        app_store.update_job(job_id, progress=.1, stage="cloning", message=f"Cloning {owner}/{repo_name}")
        completed = subprocess.run(["git", "clone", "--depth", "1", request.url, str(destination)], check=False, capture_output=True, text=True, timeout=300)
        if completed.returncode != 0:
            app_store.upsert_repository(repo_id, str(destination), source_url=request.url, description=request.description, status="failed", last_error=completed.stderr[-1000:])
            raise RuntimeError(completed.stderr[-1000:] or "Git clone failed")
        app_store.update_job(job_id, progress=.35, stage="analysing", message="Building source-grounded knowledge model")
        result = analyzer.analyse(destination, repo_id)
        app_store.upsert_repository(repo_id, str(destination), source_url=request.url, description=request.description, languages=sorted({item.language for item in result.snapshot.files if item.language != "unsupported"}), status="ready")
        return {"repository_id": repo_id, "revision_id": result.snapshot.revision.pkm_revision_id, "summary": {"files": len(result.snapshot.files), "symbols": len(result.snapshot.symbols), "facts": len(result.snapshot.facts), "relationships": len(result.snapshot.relationships), "evidence": len(result.snapshot.evidence)}, "warnings": result.warnings}
    return {"job_id": jobs.submit("github_import", request.model_dump(), work), "repository_id": repo_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = app_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found"})
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    if app_store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found"})
    app_store.request_cancel(job_id)
    return {"job_id": job_id, "status": "cancellation_requested"}


@app.get("/api/repositories/{repository_id}/pkm")
def get_pkm(repository_id: str, revision_id: str | None = None) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    return snapshot.model_dump(mode="json")


@app.get("/api/repositories/{repository_id}/overview")
def repository_overview(repository_id: str, revision_id: str | None = None) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    languages: dict[str, int] = {}
    for item in snapshot.files:
        languages[item.language] = languages.get(item.language, 0) + 1
    return {"repository_id": repository_id, "revision_id": snapshot.revision.pkm_revision_id, "languages": languages,
            "summary": {"files": len(snapshot.files), "symbols": len(snapshot.symbols), "facts": len(snapshot.facts), "relationships": len(snapshot.relationships), "evidence": len(snapshot.evidence)},
            "unsupported": [item.model_dump(mode="json") for item in snapshot.files if item.unsupported_reason],
            "warnings": snapshot.revision.validation_summary}


@app.get("/api/repositories/{repository_id}/graph")
def repository_graph(repository_id: str, revision_id: str | None = None, limit: int = 250) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    symbols = {item.symbol_id: item for item in snapshot.symbols}
    nodes = [{"id": item.symbol_id, "label": item.name, "kind": item.kind, "file_id": item.file_id, "path": next((f.path for f in snapshot.files if f.file_id == item.file_id), ""), "line_start": item.line_start, "line_end": item.line_end} for item in snapshot.symbols[:limit]]
    node_ids = {node["id"] for node in nodes}
    edges = [{"id": item.relationship_id, "source": item.source_id, "target": item.target_id,
              "source_label": symbols[item.source_id].name, "target_label": symbols[item.target_id].name,
              "type": item.relationship_type, "status": item.status, "claim_level": item.claim_level.value,
              "evidence_ids": item.evidence_ids} for item in snapshot.relationships if item.source_id in node_ids and item.target_id in node_ids]
    return {"repository_id": repository_id, "revision_id": snapshot.revision.pkm_revision_id, "nodes": nodes, "edges": edges, "node_count": len(symbols)}


@app.get("/api/repositories/{repository_id}/views")
def repository_views(repository_id: str, question: str = "") -> list[dict[str, Any]]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.architecture_reasoning import ArchitectureReasoningEngine

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
    views = arch_engine.generate_views(question)
    return [v.model_dump(mode="json") for v in views]


@app.get("/api/repositories/{repository_id}/flows")
def repository_flows(repository_id: str) -> list[dict[str, Any]]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    return [p.model_dump(mode="json") for p in paths]


@app.get("/api/repositories/{repository_id}/gaps")
def repository_gaps(repository_id: str) -> list[dict[str, Any]]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.knowledge_gaps import KnowledgeGapDetector

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    detector = KnowledgeGapDetector(snapshot, understandings, paths, files_map)
    gaps = detector.detect_all()
    return [g.model_dump(mode="json") for g in gaps]


@app.get("/api/repositories/{repository_id}/benchmark")
def repository_benchmark(repository_id: str) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    from backend.evaluation import PipelineEvaluator

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    evaluator = PipelineEvaluator(snapshot, files_map)
    report = evaluator.run_benchmark()
    return report.model_dump(mode="json")


@app.get("/api/repositories/{repository_id}/verify")
def repository_verify(repository_id: str) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.architecture_reasoning import ArchitectureReasoningEngine
    from backend.consistency_verifier import EndToEndConsistencyVerifier

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
    views = arch_engine.generate_views()
    storyboard = build_storyboard(snapshot, scope="repository")
    verifier = EndToEndConsistencyVerifier(snapshot, understandings, paths, files_map)
    report = verifier.verify(storyboard, views)
    return report.model_dump(mode="json")


@app.get("/api/repositories/{repository_id}/files")
def repository_files(repository_id: str, revision_id: str | None = None) -> list[dict[str, Any]]:
    snapshot = pkm_store.get_snapshot(repository_id, revision_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "No published PKM revision found"})
    return [item.model_dump(mode="json") for item in snapshot.files]


@app.delete("/api/repositories/{repository_id}")
def delete_repository(repository_id: str) -> dict[str, str]:
    if not pkm_store.get_snapshot(repository_id) and app_store.get_repository(repository_id) is None:
        raise HTTPException(status_code=404, detail={"code": "REPOSITORY_NOT_FOUND", "message": "Repository not found"})
    root = settings.storage_dir / "repositories" / repository_id
    if root.exists():
        shutil.rmtree(root)
    learning_store.delete_repository(repository_id)
    pkm_store.delete_repository(repository_id)
    app_store.delete_repository_metadata(repository_id)
    return {"repository_id": repository_id, "status": "deleted"}


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
    source_root = (settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id).resolve()
    source_file = (source_root / source_path).resolve()
    try:
        source_file.relative_to(source_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INPUT_UNAUTHORIZED", "message": "Unsafe source path"}) from exc
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


@app.get("/api/lessons/{lesson_id}/media/video")
def media_video(lesson_id: str) -> FileResponse:
    manifest_path = settings.storage_dir / "media" / lesson_id / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "Render the lesson first"})
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    media_root = (settings.storage_dir / "media" / lesson_id).resolve()
    video = Path(manifest.get("video_path", ""))
    video = (video if video.is_absolute() else media_root / video).resolve()
    try:
        video.relative_to(media_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "MEDIA_PATH_UNSAFE", "message": "Video path is outside the lesson media directory"}) from exc
    if not video.is_file():
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "Playable video is not available"})
    return FileResponse(video, media_type="video/mp4", filename=f"{lesson_id}.mp4")


@app.get("/api/lessons/{lesson_id}/media/captions")
def media_captions(lesson_id: str) -> FileResponse:
    captions = settings.storage_dir / "media" / lesson_id / "captions.vtt"
    if not captions.is_file():
        raise HTTPException(status_code=404, detail={"code": "CAPTIONS_NOT_FOUND", "message": "Captions are not available"})
    return FileResponse(captions, media_type="text/vtt", filename=f"{lesson_id}.vtt")


@app.post("/api/lessons")
def create_lesson(request: LessonRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(request.repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    lesson = plan_lesson(snapshot, request.goal)
    payload: dict[str, Any] = {
        "lesson_id": lesson.lesson_id,
        "repository_id": lesson.repository_id,
        "pkm_revision_id": lesson.pkm_revision_id,
        "title": lesson.title,
        "chapters": lesson.chapters,
        "scenes": lesson.scenes,
        "steps": lesson.steps,
        "validation_status": lesson.validation_status,
        "checkpoints": getattr(lesson, "checkpoints", []),
    }
    generated = llm.generate_lesson_copy(request.goal, payload["scenes"])
    if generated:
        for scene in payload["scenes"]:
            copy = next((item for item in generated.payload.get("scene_copy", []) if item.get("scene_id") == scene["scene_id"]), None)
            if copy and set(copy.get("evidence_ids", [])).issubset(set(scene.get("evidence_ids", []))):
                scene["narration"] = copy["narration"]
                scene["generation_provider"] = f"{generated.provider}:{generated.model}"
        payload["introduction"] = generated.payload.get("introduction")
        payload["conclusion"] = generated.payload.get("conclusion")
        payload["generation_provider"] = f"{generated.provider}:{generated.model}"
    payload.setdefault("generation_provider", "deterministic-evidence-planner")
    learning_store.save_lesson(payload)
    return payload


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: str) -> dict[str, Any]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    return lesson


@app.get("/api/repositories/{repository_id}/lessons")
def list_lessons(repository_id: str) -> list[dict[str, Any]]:
    if pkm_store.get_snapshot(repository_id) is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    return learning_store.list_lessons(repository_id)


@app.post("/api/lessons/{lesson_id}/render")
def render_lesson_endpoint(lesson_id: str) -> dict[str, Any]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    manifest = render_lesson(lesson, settings.storage_dir / "media" / lesson_id, settings.pocket_tts_voice)
    video_id = stable_id("video", lesson_id)
    app_store.upsert_video(video_id, lesson_id, lesson["repository_id"], lesson["title"], lesson["title"], manifest.get("video_status", "failed"), manifest.get("video_path"), manifest)
    manifest["video_id"] = video_id
    return manifest


@app.post("/api/lessons/{lesson_id}/render-job", status_code=202)
def render_lesson_job(lesson_id: str) -> dict[str, str]:
    lesson = learning_store.get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})
    def work(job_id: str) -> dict[str, Any]:
        app_store.update_job(job_id, progress=.1, stage="narration", message="Generating Pocket TTS narration")
        manifest = render_lesson(lesson, settings.storage_dir / "media" / lesson_id, settings.pocket_tts_voice)
        app_store.update_job(job_id, progress=.95, stage="persisting", message="Persisting video manifest")
        video_id = stable_id("video", lesson_id)
        app_store.upsert_video(video_id, lesson_id, lesson["repository_id"], lesson["title"], lesson["title"], manifest.get("video_status", "failed"), manifest.get("video_path"), manifest)
        manifest["video_id"] = video_id
        return manifest
    return {"job_id": jobs.submit("render", {"lesson_id": lesson_id}, work)}


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
    valid_actions = ["replay_scene", "show_source_excerpt", "hint_concept", "ask_guided_question", "ask_transfer_question"]
    decision = trained_policy.select_action(features, valid_actions) if trained_policy.available else rule_policy(features, valid_actions)
    policy_event_id = stable_id("event", enrollment_id, "policy", str(len(state["attempts"])), str(state.get("checkpoint_progress", {}).get("total_answered", 0)))
    learning_store.record_event(policy_event_id, enrollment_id, "policy_decision", decision.__dict__)
    policy_status = "trained" if trained_policy.available else None
    return {**state, "learner_state": features, "policy_decision": decision.__dict__, "policy_evaluation": evaluate_baselines(policy_status)}


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


@app.post("/api/enrollments/{enrollment_id}/checkpoint-response")
def submit_checkpoint_response(enrollment_id: str, request: CheckpointResponseRequest) -> dict[str, Any]:
    import sqlite3
    from backend.checkpoints import ActiveLearningCheckpoint, evaluate_checkpoint_response

    with sqlite3.connect(learning_store.path) as db:
        row = db.execute("SELECT lesson_id FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ENROLLMENT_NOT_FOUND", "message": "Enrollment not found"})
    lesson = learning_store.get_lesson(row[0])
    if lesson is None:
        raise HTTPException(status_code=404, detail={"code": "LESSON_NOT_FOUND", "message": "Lesson not found"})

    # Find checkpoint in lesson
    checkpoints = lesson.get("checkpoints", [])
    matching_chk = next((c for c in checkpoints if c.get("checkpoint_id") == request.checkpoint_id), None)
    if not matching_chk:
        for s in lesson.get("scenes", []):
            if s.get("checkpoint", {}).get("checkpoint_id") == request.checkpoint_id:
                matching_chk = s["checkpoint"]
                break

    if not matching_chk:
        raise HTTPException(status_code=404, detail={"code": "CHECKPOINT_NOT_FOUND", "message": "Checkpoint not found in lesson"})

    chk_model = ActiveLearningCheckpoint(**matching_chk)
    eval_result = evaluate_checkpoint_response(chk_model, request.selected_option_id)

    event_id = stable_id("event", enrollment_id, "checkpoint", request.checkpoint_id)
    learning_store.record_event(event_id, enrollment_id, "checkpoint_answered", {
        "checkpoint_id": request.checkpoint_id,
        "is_correct": eval_result.is_correct,
        "selected_option_id": request.selected_option_id,
        "recommended_action": eval_result.recommended_action,
    })

    return eval_result.model_dump(mode="json")


def _retrieval_context(snapshot: Any, items: list[Any]) -> list[dict[str, Any]]:
    evidence_by_id = {item.evidence_id: item for item in snapshot.evidence}
    symbols_by_id = {item.symbol_id: item for item in snapshot.symbols}
    relationships_by_id = {item.relationship_id: item for item in snapshot.relationships}
    context: list[dict[str, Any]] = []
    for item in items:
        evidence = [evidence_by_id[eid].model_dump(mode="json") for eid in item.evidence_ids if eid in evidence_by_id]
        related_symbols = [symbol.model_dump(mode="json") for symbol in symbols_by_id.values() if symbol.symbol_id == item.item_id]
        related_relationships = [rel.model_dump(mode="json") for rel in relationships_by_id.values() if rel.relationship_id == item.item_id]
        context.append({**item.__dict__, "evidence": evidence, "symbols": related_symbols, "relationships": related_relationships})
    return context


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
    model_result = llm.explain(request.question, _retrieval_context(snapshot, result.items))
    model_explanation = model_result.payload if model_result else None
    response = {"question": request.question, "provider": f"{model_result.provider}:{model_result.model}" if model_result else "deterministic-fallback", "evidence_items": _retrieval_context(snapshot, result.items), **(model_explanation or explanation)}
    app_store.add_message(stable_id("message", lesson_id, request.question), lesson["repository_id"], "user", request.question, [item.__dict__ for item in result.items], lesson_id)
    app_store.add_message(stable_id("message", lesson_id, request.question, "answer"), lesson["repository_id"], "assistant", str(response.get("answer", "")), [item.__dict__ for item in result.items], lesson_id)
    return response


@app.post("/api/repositories/{repository_id}/questions")
def ask_repository_question(repository_id: str, request: QuestionRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    result = retriever.retrieve(snapshot, request.question)
    explanation = build_deterministic_explanation(snapshot, request.question, result)
    context = _retrieval_context(snapshot, result.items)
    model_result = llm.explain(request.question, context)
    model_explanation = model_result.payload if model_result else None
    response = {"question": request.question, "provider": f"{model_result.provider}:{model_result.model}" if model_result else "deterministic-fallback", "evidence_items": context, **(model_explanation or explanation)}
    app_store.add_message(stable_id("message", repository_id, request.question), repository_id, "user", request.question, [item.__dict__ for item in result.items])
    app_store.add_message(stable_id("message", repository_id, request.question, "answer"), repository_id, "assistant", str(response.get("answer", "")), [item.__dict__ for item in result.items])
    return response


def _build_video_explanation(repository_id: str, request: VideoRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    storyboard = build_storyboard(snapshot, scope=request.scope, question=request.question, detail=request.detail, title=request.title)
    model_used = "deterministic-evidence-storyboard"
    model_result = llm.generate_storyboard(request.model_dump(), storyboard, [item.model_dump(mode="json") for item in snapshot.evidence])
    if model_result:
        overlay = model_result.payload
        if overlay:
            by_id = {scene["scene_id"]: scene for scene in storyboard["scenes"]}
            for scene in overlay.get("scenes", []):
                base = by_id.get(scene.get("scene_id"))
                if base is None or not isinstance(scene.get("narration"), str):
                    continue
                base["narration"] = scene["narration"]
                base["objective"] = scene.get("objective", base["objective"])
                base["visual_type"] = scene.get("visual_type", base["visual_type"])
                base["highlight_lines"] = scene.get("highlight_lines", base.get("highlight_lines", []))
            storyboard["generation_provider"] = f"{model_result.provider}:{model_result.model}"
            model_used = f"{model_result.provider}:{model_result.model}"
    validate_storyboard(storyboard, snapshot)
    storyboard["estimated_duration_ms"] = int(sum(len(str(scene["narration"]).split()) for scene in storyboard["scenes"]) / 2.3 * 1000)

    # Run End-to-End Consistency Verifier
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.architecture_reasoning import ArchitectureReasoningEngine
    from backend.consistency_verifier import EndToEndConsistencyVerifier

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
    views = arch_engine.generate_views(request.question)
    verifier = EndToEndConsistencyVerifier(snapshot, understandings, paths, files_map)
    consistency_rep = verifier.verify(storyboard, views)
    validation_status = "validated" if consistency_rep.is_valid else "warning"

    payload = {
        "lesson_id": stable_id("explanation", repository_id, request.scope, request.question, request.detail),
        "repository_id": repository_id,
        "pkm_revision_id": snapshot.revision.pkm_revision_id,
        "title": storyboard["title"],
        "chapters": storyboard["chapters"],
        "scenes": storyboard["scenes"],
        "steps": [],
        "validation_status": validation_status,
        "consistency_report": consistency_rep.model_dump(mode="json"),
        "generation_provider": model_used,
        "storyboard": storyboard,
        "scope": request.scope,
        "question": request.question,
        "detail": request.detail,
        "content_kind": "video_explanation",
        "estimated_duration_ms": storyboard["estimated_duration_ms"],
    }
    learning_store.save_lesson(payload)
    return payload


@app.post("/api/repositories/{repository_id}/video-job", status_code=202)
def create_repository_video_job(repository_id: str, request: VideoRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    estimate = build_storyboard(snapshot, scope=request.scope, question=request.question, detail=request.detail, title=request.title)["estimated_duration_ms"]

    def work(job_id: str) -> dict[str, Any]:
        app_store.update_job(job_id, progress=.08, stage="evidence", message="Retrieving repository evidence for the requested scope")
        payload = _build_video_explanation(repository_id, request)
        app_store.update_job(job_id, progress=.28, stage="storyboard", message=f"Building storyboard with {payload['generation_provider']}")
        app_store.update_job(job_id, progress=.4, stage="narration", message="Generating Pocket TTS narration segments")
        manifest = render_lesson(payload, settings.storage_dir / "media" / payload["lesson_id"], settings.pocket_tts_voice)
        app_store.update_job(job_id, progress=.92, stage="validation", message="Validating MP4, audio, captions, and chapter timing")
        video_id = stable_id("video", payload["lesson_id"])
        app_store.upsert_video(video_id, payload["lesson_id"], repository_id, payload["title"], request.scope, manifest.get("video_status", "failed"), manifest.get("video_path"), manifest)
        manifest["video_id"] = video_id
        manifest["model_used"] = payload["generation_provider"]
        return manifest

    return {
        "job_id": jobs.submit("repository_video", request.model_dump() | {"repository_id": repository_id}, work),
        "repository_id": repository_id,
        "scope": request.scope,
        "estimated_duration_ms": estimate,
        "model": settings.groq_model if settings.llm_primary_provider == "groq" else settings.ollama_model,
        "model_available": bool(llm.status()["groq_configured"] or llm.status()["ollama_available"]),
    }


@app.get("/api/repositories/{repository_id}/conversations")
def conversations(repository_id: str, lesson_id: str | None = None) -> list[dict[str, Any]]:
    return app_store.list_messages(repository_id, lesson_id)


@app.get("/api/videos")
def list_videos(repository_id: str | None = None) -> list[dict[str, Any]]:
    return app_store.list_videos(repository_id)


@app.get("/api/videos/{video_id}")
def get_video(video_id: str) -> dict[str, Any]:
    video = app_store.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "Video not found"})
    return video


@app.post("/api/adaptive/train", status_code=202)
def train_adaptive_policy() -> dict[str, str]:
    def work(job_id: str) -> dict[str, Any]:
        from backend.adaptive_model import train_policy, write_training_report
        app_store.update_job(job_id, progress=.1, stage="training", message="Training simulated learner policy")
        result = train_policy(settings.policy_checkpoint)
        report = settings.storage_dir / "models" / "teaching_policy-evaluation.json"
        write_training_report(result, report)
        trained_policy._load()
        return {"checkpoint": str(settings.policy_checkpoint), "evaluation": result.evaluation}
    return {"job_id": jobs.submit("adaptive_training", {}, work)}


@app.get("/api/learning/evaluation")
def learning_evaluation() -> dict[str, Any]:
    return evaluate_baselines("trained" if trained_policy.available else None)
