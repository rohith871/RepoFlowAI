import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response
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
from backend.learner_profile import LearnerProfileStore
profile_store = LearnerProfileStore(settings.database_path)
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


class CreateProjectRequest(BaseModel):
    learner_id: str = Field(default="default_learner", min_length=1, max_length=120)


class GenerateDomainProjectRequest(BaseModel):
    domain: str = "Machine Learning"
    learner_id: str = Field(default="default_learner", min_length=1, max_length=120)


class RecommendProjectRequest(BaseModel):
    learner_id: str = Field(default="default_learner", min_length=1, max_length=120)


class GenerateReferenceProjectRequest(BaseModel):
    repository_id: str
    learner_id: str = Field(default="default_learner", min_length=1, max_length=120)


class SubmitTaskRequest(BaseModel):
    learner_response: str = Field(default="", max_length=5000)
    solution_code: str = Field(default="", max_length=5000)
    learner_id: str | None = None


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
        repo_name = repo.name
        if repo_name in ("source", "", None):
            source_url = item.get("source_url")
            source_path = item.get("source_path")
            if source_url:
                parts = [p for p in urlparse(source_url).path.strip("/").split("/") if p]
                if len(parts) >= 2:
                    repo_name = f"{parts[0]}/{parts[1].removesuffix('.git')}"
                elif len(parts) == 1:
                    repo_name = parts[0].removesuffix('.git')
            elif source_path:
                sp = Path(source_path)
                if sp.name == "source" and sp.parent.name.startswith("repo_"):
                    repo_name = f"Repo {sp.parent.name[:12]}"
                else:
                    repo_name = sp.name
        if snapshot:
            item = {**item, "name": repo_name, "latest_published_revision_id": repo.latest_published_revision_id,
                    "summary": {"files": len(snapshot.files), "symbols": len(snapshot.symbols), "facts": len(snapshot.facts), "relationships": len(snapshot.relationships), "evidence": len(snapshot.evidence)}}
        else:
            item = {**item, "name": repo_name}
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


from backend.media_stream import stream_media_file, validate_mp4_file


def _resolve_media_dir(identifier: str) -> Path | None:
    """Intelligently resolve any media directory by lesson_id, stage_id, repository_id, or video_id."""
    media_base = settings.storage_dir / "media"
    if not media_base.is_dir():
        return None

    # 1. Direct path match
    candidates = [
        media_base / identifier,
        media_base / f"stage_{identifier}",
        media_base / f"stage_{identifier.removeprefix('stage_')}",
        media_base / f"stage_{identifier.removeprefix('lesson_stage_')}",
        media_base / f"repo_{identifier}_explainer",
        media_base / f"repo_{identifier.removeprefix('lesson_')}_explainer",
        media_base / f"repo_{identifier.removeprefix('repo_')}_explainer",
    ]
    for c in candidates:
        if (c / "manifest.json").is_file():
            return c

    # 2. Check AppStore video registration
    registered_video = app_store.get_video(identifier)
    if registered_video:
        manifest = registered_video.get("manifest", {})
        vpath = manifest.get("video_path")
        if vpath and Path(vpath).is_file():
            return Path(vpath).parent

    # 3. Scan manifest.json files in media_base
    for sub in media_base.iterdir():
        if sub.is_dir() and (sub / "manifest.json").is_file():
            try:
                import json
                m_data = json.loads((sub / "manifest.json").read_text(encoding="utf-8"))
                if (
                    m_data.get("lesson_id") == identifier
                    or sub.name == identifier
                    or sub.name == f"stage_{identifier}"
                    or sub.name == f"repo_{identifier}_explainer"
                ):
                    return sub
            except Exception:
                continue
    return None


@app.get("/api/lessons/{lesson_id}/media")
def get_media(lesson_id: str) -> dict[str, Any]:
    mdir = _resolve_media_dir(lesson_id)
    if not mdir or not (mdir / "manifest.json").is_file():
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": "Render the lesson first"})
    import json
    return json.loads((mdir / "manifest.json").read_text(encoding="utf-8"))


@app.get("/api/lessons/{lesson_id}/media/video")
def media_video(lesson_id: str, request: Request) -> Response:
    mdir = _resolve_media_dir(lesson_id)
    if not mdir:
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": f"Media not found for {lesson_id}"})
    video_path = mdir / "lesson.mp4"
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "Playable video not available on disk"})
    return stream_media_file(video_path, request, media_type="video/mp4", allow_download_name=f"{lesson_id}.mp4")


@app.get("/api/lessons/{lesson_id}/media/captions")
def media_captions(lesson_id: str, request: Request) -> Response:
    mdir = _resolve_media_dir(lesson_id)
    if not mdir:
        raise HTTPException(status_code=404, detail={"code": "MEDIA_NOT_FOUND", "message": f"Media not found for {lesson_id}"})
    captions = mdir / "captions.vtt"
    if not captions.is_file():
        raise HTTPException(status_code=404, detail={"code": "CAPTIONS_NOT_FOUND", "message": "Captions not found"})
    return stream_media_file(captions, request, media_type="text/vtt", allow_download_name=f"{lesson_id}.vtt")


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


# -------------------------------------------------------------------------
# Independent Project-Based Learning & Adaptive Tutor Endpoints
# -------------------------------------------------------------------------

@app.post("/api/repositories/{repository_id}/learning-projects")
def create_learning_project(repository_id: str, request: CreateProjectRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse the repository first"})
    
    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.knowledge_gaps import KnowledgeGapDetector
    from backend.learning_projects import ProjectGenerator

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    profile = profile_store.get_profile(request.learner_id)
    generator = ProjectGenerator(snapshot, understandings, paths, gaps)
    project = generator.generate_project(request.learner_id, profile.concept_mastery)
    
    proj_dict = project.model_dump(mode="json")
    learning_store.save_project(proj_dict)
    
    if project.project_id not in profile.projects_enrolled:
        profile.projects_enrolled.append(project.project_id)
        profile_store.save_profile(profile)

    return proj_dict


@app.get("/api/learning-projects/{project_id}")
def get_learning_project(project_id: str) -> dict[str, Any]:
    project = learning_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Learning project not found"})
    return project


@app.get("/api/learners/{learner_id}/profile")
def get_learner_profile(learner_id: str) -> dict[str, Any]:
    profile = profile_store.get_profile(learner_id)
    payload = profile.model_dump(mode="json")

    # Calculate DQN policy state features
    attempt_count = float(profile.tutor_takeovers_count + len(profile.history_records))
    avg_correctness = float(sum(profile.concept_mastery.values()) / max(1, len(profile.concept_mastery)))
    hint_rate = float(profile.total_hints_used / max(1, attempt_count))
    independence = max(0.1, round(avg_correctness - min(0.3, profile.total_hints_used * 0.05), 3))

    state_features = {
        "attempt_count": attempt_count,
        "correctness_ema": avg_correctness,
        "hint_use_rate": hint_rate,
        "revisit_count": 0.0,
        "independence_score": independence,
    }

    from backend.learning import ACTION_IDS
    decision = trained_policy.select_action(state_features, ACTION_IDS)

    payload["dqn_features"] = state_features
    payload["dqn_decision"] = {
        "action_id": decision.action_id,
        "policy_version": decision.policy_version,
        "reason_code": decision.reason_code,
        "fallback_used": decision.fallback_used,
    }
    return payload


@app.get("/api/learners/{learner_id}/projects")
def list_learner_projects(learner_id: str) -> list[dict[str, Any]]:
    return learning_store.list_projects(learner_id=learner_id)


@app.post("/api/projects/generate/domain")
def api_generate_domain_project(request: GenerateDomainProjectRequest) -> dict[str, Any]:
    from backend.learning_projects import generate_domain_project
    profile = profile_store.get_profile(request.learner_id)
    project = generate_domain_project(request.domain, profile, request.learner_id)
    pdict = project.model_dump(mode="json")
    learning_store.save_project(pdict)
    if project.project_id not in profile.projects_enrolled:
        profile.projects_enrolled.append(project.project_id)
        profile_store.save_profile(profile)
    return pdict


@app.post("/api/projects/recommend")
def api_recommend_project(request: RecommendProjectRequest) -> dict[str, Any]:
    from backend.learning_projects import recommend_project
    profile = profile_store.get_profile(request.learner_id)
    result = recommend_project(profile)
    pdict = result["project"]
    learning_store.save_project(pdict)
    if pdict["project_id"] not in profile.projects_enrolled:
        profile.projects_enrolled.append(pdict["project_id"])
        profile_store.save_profile(profile)
    return result


@app.post("/api/projects/generate/reference")
def api_generate_reference_project(request: GenerateReferenceProjectRequest) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(request.repository_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse reference repository first"})

    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.learning_projects import generate_reference_inspired_project

    source_root = settings.storage_dir / "repositories" / request.repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()

    profile = profile_store.get_profile(request.learner_id)
    project = generate_reference_inspired_project(snapshot, understandings, paths, files_map, profile, request.learner_id)
    pdict = project.model_dump(mode="json")
    learning_store.save_project(pdict)
    if project.project_id not in profile.projects_enrolled:
        profile.projects_enrolled.append(project.project_id)
        profile_store.save_profile(profile)
    return pdict


@app.post("/api/learning-projects/{project_id}/stages/{stage_id}/render-video")
def render_stage_video(project_id: str, stage_id: str) -> dict[str, Any]:
    project = learning_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})
    target_stage = next((s for s in project.get("stages", []) if s.get("stage_id") == stage_id), None)
    if not target_stage:
        raise HTTPException(status_code=404, detail={"code": "STAGE_NOT_FOUND", "message": "Stage not found"})

    stage_video_spec = target_stage.get("stage_video", {})
    if not stage_video_spec or not stage_video_spec.get("scenes"):
        stage_video_spec = {
            "title": f"{target_stage.get('title', 'Learning Stage')} — Deep Dive",
            "scenes": [
                {
                    "scene_id": f"{stage_id}_orient",
                    "title": target_stage.get("title", "Stage Orientation"),
                    "kind": "orientation",
                    "visual_type": "summary",
                    "narration": f"In this stage we master {target_stage.get('primary_concept', 'core invariants')}. {target_stage.get('description', '')}",
                    "source_refs": target_stage.get("relevant_files_or_resources", []),
                    "duration_ms": 1500,
                },
                {
                    "scene_id": f"{stage_id}_code",
                    "title": f"Implementation: {target_stage.get('primary_concept', 'Concept')}",
                    "kind": "code_walkthrough",
                    "visual_type": "code",
                    "narration": f"Examine the architectural contract and invariants required for {target_stage.get('primary_concept', 'this milestone')}.",
                    "code_path": target_stage.get("relevant_files_or_resources", ["main.py"])[0],
                    "code_excerpt": "def execute_contract(payload: dict):\n    # Enforce contract validation\n    return {'status': 'verified'}",
                    "highlight_lines": [2, 3],
                    "key_takeaway": target_stage.get("purpose", "Decouples domain from presentation"),
                    "failure_mode": f"[HYPOTHETICAL] Skipping boundary validation in {target_stage.get('primary_concept')} introduces silent state errors.",
                    "source_refs": target_stage.get("relevant_files_or_resources", [])[:1],
                    "duration_ms": 2000,
                },
            ],
        }

    stage_media_dir = settings.storage_dir / "media" / f"stage_{stage_id}"
    lesson_dict = {
        "lesson_id": f"lesson_stage_{stage_id}",
        "repository_id": project.get("repository_id", "project_repo"),
        "title": stage_video_spec.get("title", "Stage Technical Explainer"),
        "scenes": stage_video_spec.get("scenes", []),
    }
    manifest = render_lesson(lesson_dict, stage_media_dir)
    video_playable = manifest.get("video_status") == "playable" and Path(manifest.get("video_path", "")).is_file()
    target_stage["video_path"] = manifest.get("video_path")
    target_stage["video_id"] = f"vid_{stage_id}"
    target_stage["video_generation_status"] = "ready_to_watch" if video_playable else "failed"
    target_stage["video_duration_seconds"] = manifest.get("duration_seconds", 0)
    target_stage["video_url"] = f"/api/learning-projects/{project_id}/stages/{stage_id}/video"
    target_stage["captions_url"] = f"/api/learning-projects/{project_id}/stages/{stage_id}/captions"
    learning_store.save_project(project)

    app_store.save_video({
        "video_id": f"vid_{stage_id}",
        "lesson_id": f"lesson_stage_{stage_id}",
        "repository_id": project.get("repository_id", "project_repo"),
        "title": f"{project.get('title', 'Project')} — {target_stage.get('title')}",
        "topic": target_stage.get("primary_concept", "Engineering Milestone"),
        "status": "playable" if video_playable else "failed",
        "manifest": manifest,
    })
    return {
        "status": "rendered" if video_playable else "render_failed",
        "video_path": manifest.get("video_path"),
        "video_id": f"vid_{stage_id}",
        "video_url": f"/api/learning-projects/{project_id}/stages/{stage_id}/video",
        "captions_url": f"/api/learning-projects/{project_id}/stages/{stage_id}/captions",
        "manifest": manifest,
    }


@app.post("/api/repositories/{repository_id}/render-explainer")
def render_repository_explainer(repository_id: str) -> dict[str, Any]:
    snapshot = pkm_store.get_snapshot(repository_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail={"code": "PKM_NOT_FOUND", "message": "Analyse repository first"})

    from backend.understanding import SemanticUnderstandingEngine
    from backend.execution_flows import ExecutionFlowTracer
    from backend.architecture_reasoning import ArchitectureReasoningEngine
    from backend.knowledge_gaps import KnowledgeGapDetector
    from backend.semantic_storyboard import SemanticStoryboardBuilder

    source_root = settings.storage_dir / "repositories" / repository_id / "snapshots" / snapshot.revision.pkm_revision_id
    files_map = {f.path: (source_root / f.path).read_text(encoding="utf-8", errors="replace") for f in snapshot.files if (source_root / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()
    arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
    views = arch_engine.generate_views()

    builder = SemanticStoryboardBuilder(snapshot, understandings, paths, gaps, views, files_map)
    storyboard = builder.build(scope="repository")
    storyboard.setdefault("lesson_id", f"lesson_{repository_id}")

    explainer_dir = settings.storage_dir / "media" / f"repo_{repository_id}_explainer"
    manifest = render_lesson(storyboard, explainer_dir)
    vid_id = stable_id("vid_repo", repository_id)
    video_playable = manifest.get("video_status") == "playable" and Path(manifest.get("video_path", "")).is_file()
    app_store.save_video({
        "video_id": vid_id,
        "lesson_id": storyboard.get("lesson_id", f"lesson_{repository_id}"),
        "repository_id": repository_id,
        "title": f"{snapshot.repositories[0].name if snapshot.repositories else repository_id} — Architectural Explainer",
        "topic": "System Architecture & Execution Flow",
        "status": "playable" if video_playable else "failed",
        "manifest": manifest,
    })
    return {
        "status": "rendered" if video_playable else "render_failed",
        "video_id": vid_id,
        "video_path": manifest.get("video_path"),
        "video_url": f"/api/repositories/{repository_id}/explainer/video",
        "captions_url": f"/api/repositories/{repository_id}/explainer/captions",
        "manifest": manifest,
    }


@app.get("/api/learning-projects/{project_id}/stages/{stage_id}/video")
def stage_media_video(project_id: str, stage_id: str, request: Request) -> Response:
    stage_dir = settings.storage_dir / "media" / f"stage_{stage_id}"
    if not stage_dir.is_dir() or not (stage_dir / "lesson.mp4").is_file():
        stage_dir = _resolve_media_dir(f"stage_{stage_id}")
    if not stage_dir or not (stage_dir / "lesson.mp4").is_file():
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": f"Stage video not found for stage {stage_id}"})
    return stream_media_file(stage_dir / "lesson.mp4", request, media_type="video/mp4", allow_download_name=f"stage_{stage_id}.mp4")


@app.get("/api/learning-projects/{project_id}/stages/{stage_id}/captions")
def stage_media_captions(project_id: str, stage_id: str, request: Request) -> Response:
    stage_dir = settings.storage_dir / "media" / f"stage_{stage_id}"
    if not stage_dir.is_dir() or not (stage_dir / "captions.vtt").is_file():
        stage_dir = _resolve_media_dir(f"stage_{stage_id}")
    if not stage_dir or not (stage_dir / "captions.vtt").is_file():
        raise HTTPException(status_code=404, detail={"code": "CAPTIONS_NOT_FOUND", "message": f"Captions not found for stage {stage_id}"})
    return stream_media_file(stage_dir / "captions.vtt", request, media_type="text/vtt", allow_download_name=f"stage_{stage_id}.vtt")


@app.get("/api/repositories/{repository_id}/explainer/video")
def repo_explainer_video(repository_id: str, request: Request) -> Response:
    repo_dir = settings.storage_dir / "media" / f"repo_{repository_id}_explainer"
    if not repo_dir.is_dir() or not (repo_dir / "lesson.mp4").is_file():
        repo_dir = _resolve_media_dir(f"repo_{repository_id}")
    if not repo_dir or not (repo_dir / "lesson.mp4").is_file():
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": f"Explainer video not found for repo {repository_id}"})
    return stream_media_file(repo_dir / "lesson.mp4", request, media_type="video/mp4", allow_download_name=f"repo_{repository_id}.mp4")


@app.get("/api/repositories/{repository_id}/explainer/captions")
def repo_explainer_captions(repository_id: str, request: Request) -> Response:
    repo_dir = settings.storage_dir / "media" / f"repo_{repository_id}_explainer"
    if not repo_dir.is_dir() or not (repo_dir / "captions.vtt").is_file():
        repo_dir = _resolve_media_dir(f"repo_{repository_id}")
    if not repo_dir or not (repo_dir / "captions.vtt").is_file():
        raise HTTPException(status_code=404, detail={"code": "CAPTIONS_NOT_FOUND", "message": f"Captions not found for repo {repository_id}"})
    return stream_media_file(repo_dir / "captions.vtt", request, media_type="text/vtt", allow_download_name=f"repo_{repository_id}.vtt")


@app.get("/api/videos/{video_id}/stream")
def video_stream_by_id(video_id: str, request: Request) -> Response:
    video_rec = app_store.get_video(video_id)
    if not video_rec:
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": f"Video not registered: {video_id}"})
    vpath = video_rec.get("path") or video_rec.get("manifest", {}).get("video_path")
    if not vpath or not Path(vpath).is_file():
        mdir = _resolve_media_dir(video_rec.get("lesson_id", video_id))
        if mdir and (mdir / "lesson.mp4").is_file():
            vpath = str(mdir / "lesson.mp4")
    if not vpath or not Path(vpath).is_file():
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "Playable video file missing from disk"})
    return stream_media_file(Path(vpath), request, media_type="video/mp4", allow_download_name=f"{video_id}.mp4")


@app.get("/api/videos/{video_id}/captions")
def video_captions_by_id(video_id: str, request: Request) -> Response:
    video_rec = app_store.get_video(video_id)
    if not video_rec:
        raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": f"Video not registered: {video_id}"})
    vpath = video_rec.get("path") or video_rec.get("manifest", {}).get("video_path")
    cpath = Path(vpath).parent / "captions.vtt" if vpath else None
    if not cpath or not cpath.is_file():
        mdir = _resolve_media_dir(video_rec.get("lesson_id", video_id))
        if mdir and (mdir / "captions.vtt").is_file():
            cpath = mdir / "captions.vtt"
    if not cpath or not cpath.is_file():
        raise HTTPException(status_code=404, detail={"code": "CAPTIONS_NOT_FOUND", "message": "Captions file missing from disk"})
    return stream_media_file(cpath, request, media_type="text/vtt", allow_download_name=f"{video_id}.vtt")


@app.post("/api/learning-projects/{project_id}/tasks/{task_id}/submit")
def submit_project_task(project_id: str, task_id: str, request: SubmitTaskRequest) -> dict[str, Any]:
    project = learning_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})
    
    target_stage = None
    target_task = None
    for stage in project.get("stages", []):
        for task in stage.get("tasks", []):
            if task.get("task_id") == task_id:
                target_stage = stage
                target_task = task
                break
        if target_task:
            break

    if not target_task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task not found in project"})

    submitted_text = request.learner_response or request.solution_code
    learner_id = request.learner_id or project.get("learner_id", "default_learner")
    profile = profile_store.get_profile(learner_id)
    concept = target_task.get("required_concepts", ["general"])[0]

    target_task["attempts_count"] = target_task.get("attempts_count", 0) + 1
    target_task["learner_response"] = submitted_text

    # Evaluate criteria
    criteria = target_task.get("completion_criteria", {})
    req_keywords = criteria.get("required_keywords", [])
    response_lower = submitted_text.lower()
    
    is_successful = (
        len(submitted_text.strip()) >= 5
        and (not req_keywords or any(kw.lower() in response_lower for kw in req_keywords))
    )

    if is_successful:
        target_task["status"] = "completed"
        target_task["evaluation_feedback"] = "Task passed! Evidence matches repository architecture."
        import datetime
        target_task["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Unlock next stage if this stage's tasks are complete
        if all(t.get("status") in {"completed", "tutor_demonstrated"} for t in target_stage.get("tasks", [])):
            target_stage["status"] = "completed"
            stage_idx = project["stages"].index(target_stage)
            if stage_idx + 1 < len(project["stages"]):
                project["stages"][stage_idx + 1]["status"] = "in_progress"

        project["completed_tasks"] = sum(
            1 for s in project.get("stages", []) for t in s.get("tasks", []) if t.get("status") in {"completed", "tutor_demonstrated"}
        )
        if project["completed_tasks"] == project.get("total_tasks", 0):
            project["status"] = "completed"
            if project["project_id"] not in profile.completed_projects:
                profile.completed_projects.append(project["project_id"])

        profile.record_attempt(
            repository_id=project["repository_id"],
            project_id=project_id,
            task_id=task_id,
            concept=concept,
            is_successful=True,
            hints_used=target_task.get("hints_used", 0),
            attempts_count=target_task["attempts_count"],
        )
    else:
        target_task["status"] = "needs_revision"
        target_task["evaluation_feedback"] = (
            f"Response could not be fully verified. Required architectural components or keywords ({', '.join(req_keywords)}) were missing."
        )
        profile.record_attempt(
            repository_id=project["repository_id"],
            project_id=project_id,
            task_id=task_id,
            concept=concept,
            is_successful=False,
            hints_used=target_task.get("hints_used", 0),
            attempts_count=target_task["attempts_count"],
        )

    learning_store.save_project(project)
    profile_store.save_profile(profile)

    return {
        "task_id": task_id,
        "status": target_task["status"],
        "is_successful": is_successful,
        "passed": is_successful,
        "evaluation_feedback": target_task["evaluation_feedback"],
        "updated_concept_mastery": profile.concept_mastery.get(concept, 0.5),
        "project_completed_tasks": project["completed_tasks"],
        "project_status": project["status"],
    }


@app.post("/api/learning-projects/{project_id}/tasks/{task_id}/hint")
def request_project_task_hint(project_id: str, task_id: str) -> dict[str, Any]:
    project = learning_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})

    target_task = None
    for stage in project.get("stages", []):
        for task in stage.get("tasks", []):
            if task.get("task_id") == task_id:
                target_task = task
                break
        if target_task:
            break

    if not target_task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task not found"})

    hints = target_task.get("hints", [])
    hints_used = target_task.get("hints_used", 0)
    if hints_used < len(hints):
        current_hint = hints[hints_used]
        target_task["hints_used"] = hints_used + 1
        learning_store.save_project(project)
        h_lvl = int(current_hint.get("level", hints_used + 1))
        h_text = current_hint.get("hint", "")
        return {
            "hint_level": str(h_lvl),
            "hint_text": h_text,
            "remaining_hints": len(hints) - target_task["hints_used"],
            "hint": {"level": h_lvl, "text": h_text},
        }
    return {
        "hint_level": "exhausted",
        "hint_text": "All hints for this task have been revealed. Consider using 'Tutor Takeover' for a full demonstration.",
        "remaining_hints": 0,
        "hint": {"level": 0, "text": "All hints revealed."},
    }


@app.post("/api/learning-projects/{project_id}/tasks/{task_id}/tutor-takeover")
def trigger_tutor_takeover(project_id: str, task_id: str) -> dict[str, Any]:
    project = learning_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"})

    target_stage = None
    target_task = None
    for stage in project.get("stages", []):
        for task in stage.get("tasks", []):
            if task.get("task_id") == task_id:
                target_stage = stage
                target_task = task
                break
        if target_task:
            break

    if not target_task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task not found"})

    learner_id = project.get("learner_id", "default_learner")
    profile = profile_store.get_profile(learner_id)
    concept = target_task.get("required_concepts", ["general"])[0]

    target_task["status"] = "tutor_demonstrated"
    import datetime
    target_task["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    target_task["evaluation_feedback"] = "Task demonstrated by RepoFlow AI Tutor with source citations."

    if all(t.get("status") in {"completed", "tutor_demonstrated"} for t in target_stage.get("tasks", [])):
        target_stage["status"] = "completed"
        stage_idx = project["stages"].index(target_stage)
        if stage_idx + 1 < len(project["stages"]):
            project["stages"][stage_idx + 1]["status"] = "in_progress"

    project["completed_tasks"] = sum(
        1 for s in project.get("stages", []) for t in s.get("tasks", []) if t.get("status") in {"completed", "tutor_demonstrated"}
    )

    profile.record_attempt(
        repository_id=project["repository_id"],
        project_id=project_id,
        task_id=task_id,
        concept=concept,
        is_successful=True,
        hints_used=target_task.get("hints_used", 0),
        attempts_count=target_task.get("attempts_count", 1),
        tutor_assisted=True,
    )

    learning_store.save_project(project)
    profile_store.save_profile(profile)

    td = target_task.get("tutor_demonstration", {})
    fc = target_task.get("follow_up_challenge", {})
    return {
        "task_id": task_id,
        "status": "tutor_demonstrated",
        "task": target_task,
        "tutor_takeover": {
            "task_id": task_id,
            "demonstration_steps": td.get("demonstration_walkthrough", [
                f"1. Inspected {td.get('evidence_path', '')}.",
                f"2. Verified code lines {td.get('line_range', '')}.",
                "3. Verified architectural boundaries."
            ]),
            "demonstrated_code": td.get("evidence_path", ""),
            "verified_facts": td.get("verified_vs_inferred", "VERIFIED: static source confirmed."),
            "follow_up_challenge": fc.get("challenge", ""),
            "explanation_rationale": td.get("task_summary", "Architecture explanation"),
        },
        "tutor_demonstration": td,
        "follow_up_challenge": fc,
        "message": "Tutor has demonstrated this task with verified source evidence. Complete the follow-up challenge to verify your understanding.",
    }


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
