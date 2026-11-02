from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from backend.analyzer import RepositoryAnalyzer
from backend.architecture_reasoning import ArchitectureReasoningEngine
from backend.config import Settings
from backend.execution_flows import ExecutionFlowTracer
from backend.knowledge_gaps import KnowledgeGapDetector
from backend.learner_profile import LearnerProfileStore
from backend.learning import LearningStore
from backend.learning_projects import LearningProject, ProjectGenerator
from backend.main import app
from backend.storage import PkmStore
from backend.understanding import SemanticUnderstandingEngine

SAMPLE_FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_project"
AUTH_FIXTURE = Path(__file__).parents[1] / "fixtures" / "auth_platform"


def test_multi_repository_analysis_and_perspectives(tmp_path: Path):
    """Verify that both fixtures are parsed independently into complete 6-perspective architectures."""
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    store = PkmStore(settings.database_path)
    analyzer = RepositoryAnalyzer(settings, store)

    # 1. Analyze Sample Project
    sample_res = analyzer.analyse(SAMPLE_FIXTURE)
    sample_snapshot = sample_res.snapshot
    sample_files = {f.path: (SAMPLE_FIXTURE / f.path).read_text(encoding="utf-8") for f in sample_snapshot.files if (SAMPLE_FIXTURE / f.path).is_file()}
    sample_engine = SemanticUnderstandingEngine(sample_snapshot, sample_files)
    sample_engine.parse_all()
    sample_understandings = sample_engine.analyze_components()
    sample_tracer = ExecutionFlowTracer(sample_snapshot, sample_understandings, sample_snapshot.relationships)
    sample_paths = sample_tracer.trace_paths()

    sample_arch = ArchitectureReasoningEngine(sample_snapshot, sample_understandings, sample_snapshot.relationships, sample_paths)
    sample_views = sample_arch.generate_views()

    assert len(sample_views) >= 6
    sample_view_types = {v.view_type for v in sample_views}
    expected_perspectives = {
        "high_level_system", "module_dependency", "component_relationships",
        "api_communication", "data_flow", "execution_flow"
    }
    assert expected_perspectives.issubset(sample_view_types)

    # 2. Analyze Auth Platform
    auth_res = analyzer.analyse(AUTH_FIXTURE)
    auth_snapshot = auth_res.snapshot
    auth_files = {f.path: (AUTH_FIXTURE / f.path).read_text(encoding="utf-8") for f in auth_snapshot.files if (AUTH_FIXTURE / f.path).is_file()}
    auth_engine = SemanticUnderstandingEngine(auth_snapshot, auth_files)
    auth_engine.parse_all()
    auth_understandings = auth_engine.analyze_components()
    auth_tracer = ExecutionFlowTracer(auth_snapshot, auth_understandings, auth_snapshot.relationships)
    auth_paths = auth_tracer.trace_paths()

    auth_arch = ArchitectureReasoningEngine(auth_snapshot, auth_understandings, auth_snapshot.relationships, auth_paths)
    auth_views = auth_arch.generate_views()

    assert len(auth_views) >= 6
    auth_view_types = {v.view_type for v in auth_views}
    assert expected_perspectives.issubset(auth_view_types)

    # Verify node inspection attributes on auth_platform
    hl_view = next(v for v in auth_views if v.view_type == "high_level_system")
    assert hl_view.boundaries
    for node in hl_view.components:
        assert "what_it_does" in node
        assert "why_it_exists" in node
        assert "who_calls_it" in node
        assert "what_it_calls" in node
        assert "confidence" in node


def test_independent_project_curriculum_and_adaptive_presentation(tmp_path: Path):
    """Verify that ProjectGenerator builds authentic 5-stage curriculum adapting to learner profiles."""
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    pkm_store = PkmStore(settings.database_path)
    res = RepositoryAnalyzer(settings, pkm_store).analyse(SAMPLE_FIXTURE)
    snapshot = res.snapshot
    files_map = {f.path: (SAMPLE_FIXTURE / f.path).read_text(encoding="utf-8") for f in snapshot.files if (SAMPLE_FIXTURE / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    profile_store = LearnerProfileStore(settings.database_path)
    learner_id = "learner_adaptive_test"

    # Beginner learner (0 mastery)
    profile_beginner = profile_store.get_or_create_profile(learner_id)
    generator = ProjectGenerator(snapshot, understandings, paths, gaps, files_map)
    project_beg = generator.generate_project(snapshot.repository_id, profile_beginner)

    assert len(project_beg.stages) == 5
    assert project_beg.stages[0].unlocked is True
    assert project_beg.stages[1].unlocked is False
    # Stage 1 tasks should have substantial_support for beginner
    task1 = project_beg.stages[0].tasks[0]
    assert task1.presentation_level in {"moderate", "substantial_support"}
    assert len(task1.hints) == 3
    assert task1.rubric.verification_criteria

    # Now simulate veteran learner with high mastery in request_routing
    learner_vet_id = "learner_veteran"
    profile_vet = profile_store.get_or_create_profile(learner_vet_id)
    profile_vet.concept_mastery["request_routing"] = 0.95
    profile_store.save_profile(profile_vet)

    project_vet = generator.generate_project(snapshot.repository_id, profile_vet)
    vet_task1 = project_vet.stages[0].tasks[0]
    assert vet_task1.presentation_level == "advanced"


def test_tutor_takeover_and_progressive_hints(tmp_path: Path):
    """Verify tutor takeover generates grounded demonstration and progressive hints reveal cleanly."""
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    pkm_store = PkmStore(settings.database_path)
    res = RepositoryAnalyzer(settings, pkm_store).analyse(SAMPLE_FIXTURE)
    snapshot = res.snapshot
    files_map = {f.path: (SAMPLE_FIXTURE / f.path).read_text(encoding="utf-8") for f in snapshot.files if (SAMPLE_FIXTURE / f.path).is_file()}
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    profile_store = LearnerProfileStore(settings.database_path)
    generator = ProjectGenerator(snapshot, understandings, paths, gaps, files_map)
    project = generator.generate_project(snapshot.repository_id)

    # 1. Test progressive hint reveal
    task = project.stages[0].tasks[0]
    assert project.revealed_hints_per_task.get(task.task_id, 0) == 0

    h1 = project.reveal_next_hint(task.task_id)
    assert h1 is not None
    assert h1.level == 1
    assert project.revealed_hints_per_task.get(task.task_id) == 1

    h2 = project.reveal_next_hint(task.task_id)
    assert h2 is not None
    assert h2.level == 2

    # 2. Test Tutor Takeover
    takeover = generator.generate_tutor_takeover(task)
    assert takeover.task_id == task.task_id
    assert len(takeover.demonstration_steps) >= 3
    assert takeover.demonstrated_code
    assert takeover.verified_facts
    assert takeover.follow_up_challenge
    assert "user_route" in takeover.explanation_rationale or "api.py" in takeover.explanation_rationale


def test_cross_project_learner_continuity_and_transfer(tmp_path: Path):
    """Verify learner concept mastery carries over across projects and certifies demonstrated transfer."""
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    pkm_store = PkmStore(settings.database_path)
    analyzer = RepositoryAnalyzer(settings, pkm_store)
    profile_store = LearnerProfileStore(settings.database_path)
    learner_id = "cross_learner_001"

    # Ingest repo 1 (sample)
    snap1 = analyzer.analyse(SAMPLE_FIXTURE).snapshot
    files1 = {f.path: (SAMPLE_FIXTURE / f.path).read_text(encoding="utf-8") for f in snap1.files if (SAMPLE_FIXTURE / f.path).is_file()}
    engine1 = SemanticUnderstandingEngine(snap1, files1)
    engine1.parse_all()
    und1 = engine1.analyze_components()
    tracer1 = ExecutionFlowTracer(snap1, und1, snap1.relationships)
    paths1 = tracer1.trace_paths()
    gaps1 = KnowledgeGapDetector(snap1, und1, paths1, files1).detect_all()

    # Generate Project 1
    gen1 = ProjectGenerator(snap1, und1, paths1, gaps1, files1)
    p1 = gen1.generate_project(snap1.repository_id)

    # Learner solves task in project 1
    task1 = p1.stages[0].tasks[0]
    solution1 = "def user_route(name):\n    return get_user(name)\n# api.py verified"
    result1 = p1.submit_task(task1.task_id, solution1, profile_store, learner_id)

    assert result1["passed"] is True
    prof = profile_store.get_or_create_profile(learner_id)
    assert prof.concept_mastery.get(task1.target_concept, 0.0) > 0.5
    assert snap1.repository_id in prof.project_history

    # Now ingest repo 2 (auth_platform)
    snap2 = analyzer.analyse(AUTH_FIXTURE).snapshot
    files2 = {f.path: (AUTH_FIXTURE / f.path).read_text(encoding="utf-8") for f in snap2.files if (AUTH_FIXTURE / f.path).is_file()}
    engine2 = SemanticUnderstandingEngine(snap2, files2)
    engine2.parse_all()
    und2 = engine2.analyze_components()
    tracer2 = ExecutionFlowTracer(snap2, und2, snap2.relationships)
    paths2 = tracer2.trace_paths()
    gaps2 = KnowledgeGapDetector(snap2, und2, paths2, files2).detect_all()

    gen2 = ProjectGenerator(snap2, und2, paths2, gaps2, files2)
    # Generate project with existing learner profile
    p2 = gen2.generate_project(snap2.repository_id, prof)

    # Notice learner profile concept mastery is preserved!
    assert prof.concept_mastery.get(task1.target_concept) > 0.5

    # Learner solves task in repo 2 on the same or related concept
    task2 = p2.stages[0].tasks[0]
    solution2 = "def login_endpoint(email, password):\n    return verify_credentials(email, password)\n# gateway.py"
    result2 = p2.submit_task(task2.task_id, solution2, profile_store, learner_id)
    assert result2["passed"] is True

    # Check that demonstrated transfer was recorded!
    prof_updated = profile_store.get_or_create_profile(learner_id)
    assert snap2.repository_id in prof_updated.project_history
    assert len(prof_updated.demonstrated_transfers) >= 1
    transfer = prof_updated.demonstrated_transfers[0]
    assert transfer["concept"] == task1.target_concept
    assert transfer["source_repo"] == snap1.repository_id
    assert transfer["target_repo"] == snap2.repository_id


def test_learning_project_rest_api(tmp_path: Path, monkeypatch):
    """Verify all REST API endpoints for independent project-based learning and tutor takeover."""
    monkeypatch.setenv("REPOFLOW_STORAGE_DIR", str(tmp_path / "storage"))
    client = TestClient(app)

    # 1. Analyse sample repo
    an_resp = client.post("/api/repositories/analyse", json={"path": str(SAMPLE_FIXTURE)})
    assert an_resp.status_code == 200
    repo_id = an_resp.json()["repository_id"]

    # 2. Create learning project curriculum
    proj_resp = client.post(f"/api/repositories/{repo_id}/learning-projects", json={"learner_id": "api_learner_1"})
    assert proj_resp.status_code == 200
    pdata = proj_resp.json()
    assert "project_id" in pdata
    project_id = pdata["project_id"]
    assert len(pdata["stages"]) == 5
    task_id = pdata["stages"][0]["tasks"][0]["task_id"]

    # 3. Fetch project
    get_proj = client.get(f"/api/learning-projects/{project_id}")
    assert get_proj.status_code == 200
    assert get_proj.json()["project_id"] == project_id

    # 4. Request Progressive Hint
    hint_resp = client.post(f"/api/learning-projects/{project_id}/tasks/{task_id}/hint")
    assert hint_resp.status_code == 200
    hdata = hint_resp.json()
    assert hdata["hint"]["level"] == 1

    # 5. Submit solution
    sub_resp = client.post(
        f"/api/learning-projects/{project_id}/tasks/{task_id}/submit",
        json={"solution_code": "def user_route(name):\n    return get_user(name)\n# api.py", "learner_id": "api_learner_1"}
    )
    assert sub_resp.status_code == 200
    assert sub_resp.json()["passed"] is True

    # 6. Request Tutor Takeover on a subsequent task
    task2_id = pdata["stages"][1]["tasks"][0]["task_id"]
    takeover_resp = client.post(f"/api/learning-projects/{project_id}/tasks/{task2_id}/tutor-takeover", json={"learner_id": "api_learner_1"})
    assert takeover_resp.status_code == 200
    tdata = takeover_resp.json()
    assert "tutor_takeover" in tdata
    assert len(tdata["tutor_takeover"]["demonstration_steps"]) >= 2
    assert tdata["task"]["status"] == "tutor_demonstrated"

    # 7. Check learner profile endpoint
    prof_resp = client.get("/api/learners/api_learner_1/profile")
    assert prof_resp.status_code == 200
    prof_json = prof_resp.json()
    assert prof_json["learner_id"] == "api_learner_1"
    assert prof_json["tutor_takeovers_used"] >= 1
    assert repo_id in prof_json["project_history"]

    # 8. List learner projects
    projs_resp = client.get("/api/learners/api_learner_1/projects")
    assert projs_resp.status_code == 200
    assert len(projs_resp.json()) >= 1
