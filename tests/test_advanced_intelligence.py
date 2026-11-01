from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from backend.analyzer import RepositoryAnalyzer
from backend.architecture_reasoning import ArchitectureReasoningEngine
from backend.cause_effect import CauseAndEffectEngine
from backend.config import Settings
from backend.consistency_verifier import EndToEndConsistencyVerifier
from backend.evaluation import PipelineEvaluator
from backend.execution_flows import ExecutionFlowTracer
from backend.explanation_planner import ExplanationPlanningEngine
from backend.knowledge_gaps import KnowledgeGapDetector
from backend.main import app
from backend.narration_checker import NarrationQualityChecker
from backend.semantic_storyboard import SemanticStoryboardBuilder
from backend.storage import PkmStore
from backend.understanding import SemanticUnderstandingEngine

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_project"


def _setup_analysis(tmp_path: Path):
    settings = Settings(storage_dir=tmp_path / "storage")
    settings.ensure_directories()
    store = PkmStore(settings.database_path)
    res = RepositoryAnalyzer(settings, store).analyse(FIXTURE)
    files_map = {
        f.path: (FIXTURE / f.path).read_text(encoding="utf-8")
        for f in res.snapshot.files
        if (FIXTURE / f.path).is_file()
    }
    return res.snapshot, files_map, settings, store


def test_cross_file_relationships_and_multi_level_understanding(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()

    # Must resolve cross-file call: api.py:user_route -> app.py:get_user in snapshot
    sym_map = {s.symbol_id: s.qualified_name for s in snapshot.symbols}
    resolved_pairs = [(sym_map.get(r.source_id), r.relationship_type, sym_map.get(r.target_id)) for r in snapshot.relationships]
    assert any(
        src == "api.py:user_route" and rtype == "calls" and tgt == "app.py:get_user"
        for src, rtype, tgt in resolved_pairs
    )

    # Must derive multi-level understandings
    understandings = engine.analyze_components()
    assert "api.py:user_route" in [s.qualified_name for s in snapshot.symbols if s.symbol_id in understandings]
    user_route_comp = next(u for u in understandings.values() if u.name == "user_route")
    assert user_route_comp.execution_role == "request_handler"
    assert any(inp["name"] == "name" for inp in user_route_comp.inputs)
    assert user_route_comp.transformations

    user_model_comp = next(u for u in understandings.values() if u.name == "User")
    assert user_model_comp.execution_role == "entity_model"
    assert any(inp["name"] == "name" for inp in user_model_comp.inputs)


def test_execution_flow_and_data_lineage_reasoning(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()

    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()

    assert len(paths) >= 1
    primary_path = paths[0]
    assert "user_route" in primary_path.name
    assert len(primary_path.steps) >= 4

    # Verify step sequence
    step_ops = [s.operation_type for s in primary_path.steps]
    assert "entry_call" in step_ops
    assert "call" in step_ops
    assert "return" in step_ops

    # Verify data lineage traces parameter 'name'
    assert primary_path.data_lineage
    lineage = primary_path.data_lineage[0]
    assert lineage["variable"] == "name"
    assert lineage["transmitted_in_response"] is True


def test_knowledge_gap_and_contradiction_detection(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()

    detector = KnowledgeGapDetector(snapshot, understandings, paths, files_map)
    gaps = detector.detect_all()

    assert len(gaps) >= 1
    # Check that schema.sql runtime uncertainty is detected and disclosed
    sql_gap = next((g for g in gaps if "schema.sql" in g.subject_name), None)
    assert sql_gap is not None
    assert sql_gap.category == "runtime_uncertainty"
    assert sql_gap.resolution_status == "disclosed_limitation"
    assert "database" in sql_gap.limitation_note.lower() and "runtime" in sql_gap.limitation_note.lower()


def test_architecture_views_and_layout_separation(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()

    arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
    views = arch_engine.generate_views()

    assert len(views) >= 3
    view_types = {v.view_type for v in views}
    assert "module_organization" in view_types
    assert "request_flow" in view_types
    assert "data_lifecycle" in view_types

    org_view = next(v for v in views if v.view_type == "module_organization")
    assert org_view.boundaries
    assert all("x" in c and "y" in c for c in org_view.components)


def test_explanation_planning_and_concept_dependencies(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    planner = ExplanationPlanningEngine(snapshot, understandings, paths, gaps, files_map)
    plan = planner.build_plan(goal="Understand request flow")

    assert plan.teaching_units
    assert plan.topological_concept_order

    # Model concept must precede Request Handler concept
    unit_titles = [u.title for u in plan.teaching_units]
    model_idx = next(i for i, t in enumerate(unit_titles) if "User" in t)
    handler_idx = next(i for i, t in enumerate(unit_titles) if "user_route" in t)
    assert model_idx < handler_idx


def test_cause_and_effect_and_counterfactuals(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    cause_engine = CauseAndEffectEngine(understandings, paths, gaps)
    route_comp = next(u for u in understandings.values() if u.name == "user_route")
    causal = cause_engine.explain_component(route_comp)

    assert causal.problem_addressed
    assert causal.why_involved
    assert causal.responsibility_boundary
    assert "[HYPOTHETICAL]" in causal.counterfactual_analysis


def test_end_to_end_consistency_verifier(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
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

    verifier = EndToEndConsistencyVerifier(snapshot, understandings, paths, files_map)
    report = verifier.verify(storyboard, views)

    assert report.is_valid is True
    assert report.overall_integrity_score >= 80.0
    assert "architecture_view_components_and_edges_grounded" in report.verified_checks
    assert "storyboard_entities_and_source_references_verified" in report.verified_checks
    assert len(report.critical_mismatches) == 0


def test_pipeline_benchmark_comparison(tmp_path: Path) -> None:
    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    evaluator = PipelineEvaluator(snapshot, files_map)
    report = evaluator.run_benchmark()

    assert report.repository_name
    assert len(report.metrics) == 10
    # Advanced overall score must exceed 90/100
    assert report.advanced_summary["overall_score"] >= 90.0
    # Boilerplate in advanced storyboard must be 0
    assert report.advanced_summary["boilerplate_count"] == 0


def test_semantic_api_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPOFLOW_STORAGE_DIR", str(tmp_path / "storage"))
    from backend import main

    client = TestClient(main.app)
    # 1. Analyse fixture
    analyse_resp = client.post("/api/repositories/analyse", json={"path": str(FIXTURE)})
    assert analyse_resp.status_code == 200
    repo_id = analyse_resp.json()["repository_id"]

    # 2. Test /views endpoint
    views_resp = client.get(f"/api/repositories/{repo_id}/views")
    assert views_resp.status_code == 200
    assert len(views_resp.json()) >= 3

    # 3. Test /flows endpoint
    flows_resp = client.get(f"/api/repositories/{repo_id}/flows")
    assert flows_resp.status_code == 200
    assert len(flows_resp.json()) >= 1
    assert "user_route" in flows_resp.json()[0]["name"]

    # 4. Test /gaps endpoint
    gaps_resp = client.get(f"/api/repositories/{repo_id}/gaps")
    assert gaps_resp.status_code == 200
    assert len(gaps_resp.json()) >= 1

    # 5. Test /benchmark endpoint
    bench_resp = client.get(f"/api/repositories/{repo_id}/benchmark")
    assert bench_resp.status_code == 200
    assert bench_resp.json()["metrics"]

    # 6. Test /verify endpoint
    verify_resp = client.get(f"/api/repositories/{repo_id}/verify")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_valid"] is True

    # 7. Test lesson creation with checkpoints and interactive response
    lesson_resp = client.post("/api/lessons", json={"repository_id": repo_id, "goal": "Understand architecture"})
    assert lesson_resp.status_code == 200
    lesson_data = lesson_resp.json()
    assert "checkpoints" in lesson_data
    if lesson_data["checkpoints"]:
        chk = lesson_data["checkpoints"][0]
        enrol_resp = client.post(f"/api/lessons/{lesson_data['lesson_id']}/enrol", json={"learner_id": "test-learner"})
        assert enrol_resp.status_code == 200
        enrol_id = enrol_resp.json()["enrollment_id"]
        chk_resp = client.post(f"/api/enrollments/{enrol_id}/checkpoint-response", json={
            "checkpoint_id": chk["checkpoint_id"],
            "selected_option_id": chk["options"][0]["id"],
        })
        assert chk_resp.status_code == 200
        assert "is_correct" in chk_resp.json()
        assert "recommended_action" in chk_resp.json()


def test_transcript_validator_and_segmentation() -> None:
    from backend.transcript import TranscriptSegment, TranscriptValidator, build_transcript_from_lesson

    lesson = {
        "scenes": [
            {
                "scene_id": "sc1",
                "title": "Introduction",
                "narration": "In this video we will explore the architecture of the system.",
                "source_refs": ["api.py:1-10"],
            },
            {
                "scene_id": "sc2",
                "title": "Duplicate Scene",
                "narration": "In this video we will explore the architecture of the system.",
                "source_refs": ["api.py:1-10"],
            },
            {
                "scene_id": "sc3",
                "title": "Clean Scene",
                "narration": "The user_route function parses incoming request parameters and forwards them to the domain model.",
                "source_refs": ["unknown_ghost_file.py"],
            },
        ]
    }

    segments = build_transcript_from_lesson(lesson)
    assert len(segments) == 3
    assert segments[0].spoken_text.startswith("In this video")

    validator = TranscriptValidator(known_files={"api.py", "app.py"})
    report = validator.validate(segments)

    # Must flag boilerplate in scene 1
    assert any(i.issue_type == "boilerplate_narration" for i in report.issues)
    # Must flag duplicate narration in scene 2
    assert any(i.issue_type == "duplicate_narration" for i in report.issues)
    # Must flag unsupported source file in scene 3
    assert any(i.issue_type == "unsupported_source_file" for i in report.issues)
    assert report.quality_score < 100.0


def test_active_learning_checkpoints_and_evaluation(tmp_path: Path) -> None:
    from backend.checkpoints import CheckpointGenerator, evaluate_checkpoint_response
    from backend.lessons import plan_lesson

    snapshot, files_map, _, _ = _setup_analysis(tmp_path)
    engine = SemanticUnderstandingEngine(snapshot, files_map)
    engine.parse_all()
    understandings = engine.analyze_components()
    tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
    paths = tracer.trace_paths()
    gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()

    lesson_plan = plan_lesson(snapshot, goal="Explore API handler and data flow")
    assert lesson_plan.checkpoints
    assert len(lesson_plan.checkpoints) >= 1

    first_chk = lesson_plan.checkpoints[0]
    assert "question_text" in first_chk
    assert len(first_chk["options"]) >= 2
    
    # Check evaluation
    from backend.checkpoints import ActiveLearningCheckpoint
    chk_obj = ActiveLearningCheckpoint(**first_chk)
    correct_opt = next(o for o in chk_obj.options if o.is_correct)
    incorrect_opt = next(o for o in chk_obj.options if not o.is_correct)

    eval_correct = evaluate_checkpoint_response(chk_obj, correct_opt.id)
    assert eval_correct.is_correct is True
    assert eval_correct.recommended_action == "continue"

    eval_incorrect = evaluate_checkpoint_response(chk_obj, incorrect_opt.id)
    assert eval_incorrect.is_correct is False
    assert eval_incorrect.recommended_action in {"hint_concept", "show_source_excerpt", "replay_scene"}


def test_remotion_renderer_integration(tmp_path: Path) -> None:
    from backend.remotion_renderer import RemotionRenderer
    from backend import media

    renderer = RemotionRenderer()
    # It checks availability cleanly without throwing
    available = renderer.available()
    assert isinstance(available, bool)

    lesson = {
        "lesson_id": "lesson_remotion_test",
        "scenes": [
            {
                "scene_id": "scene_rem_1",
                "title": "Remotion Test Scene",
                "kind": "orientation",
                "visual_type": "summary",
                "narration": "A test scene for remotion integration.",
                "source_refs": ["app.py"],
                "duration_ms": 500,
            }
        ],
    }

    manifest = media.render_lesson(lesson, tmp_path / "remotion_media")
    assert (tmp_path / "remotion_media" / "remotion_props.json").is_file()
    assert manifest["renderer"] in {"remotion", "pillow_ffmpeg"}
    assert "transcript_validation" in manifest
