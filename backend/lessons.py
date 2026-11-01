from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.ids import stable_id
from backend.models import PkmSnapshot
from backend.semantic_layer import ComponentUnderstanding, ExecutionPath, KnowledgeGap
from backend.explanation_planner import ExplanationPlanningEngine
from backend.checkpoints import CheckpointGenerator
from backend.cause_effect import CauseAndEffectEngine


@dataclass(frozen=True)
class LessonPlan:
    lesson_id: str
    repository_id: str
    pkm_revision_id: str
    title: str
    chapters: list[dict[str, Any]]
    scenes: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    validation_status: str
    checkpoints: list[dict[str, Any]] = ()


def plan_lesson(snapshot: PkmSnapshot, goal: str = "Understand the repository architecture") -> LessonPlan:
    lesson_id = stable_id("lesson", snapshot.revision.repository_id, snapshot.revision.pkm_revision_id, goal)
    repo_id = snapshot.revision.repository_id

    # Reconstruct semantic components and paths
    comp_facts = [f for f in snapshot.facts if f.fact_type == "component_understanding"]
    understandings: dict[str, ComponentUnderstanding] = {}
    for f in comp_facts:
        try:
            comp = ComponentUnderstanding(**f.attributes)
            understandings[comp.component_id] = comp
        except Exception:
            continue

    paths: list[ExecutionPath] = []
    for f in snapshot.facts:
        if f.fact_type == "execution_path":
            try:
                paths.append(ExecutionPath(**f.attributes))
            except Exception:
                continue

    gaps: list[KnowledgeGap] = []
    for f in snapshot.facts:
        if f.fact_type == "knowledge_gap":
            try:
                gaps.append(KnowledgeGap(**f.attributes))
            except Exception:
                continue

    source_files_map: dict[str, str] = {}
    for ev in snapshot.evidence:
        if ev.source_path and ev.excerpt and ev.source_path not in source_files_map:
            source_files_map[ev.source_path] = ev.excerpt

    planner = ExplanationPlanningEngine(snapshot, understandings, paths, gaps, source_files_map)
    plan = planner.build_plan(goal=goal, depth="intermediate")
    cause_engine = CauseAndEffectEngine(understandings, paths, gaps)

    scenes: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    step_ids: list[str] = []

    # Chapter 1: Foundations
    ch_foundations_id = stable_id("chapter", lesson_id, "foundations")
    ch_flow_id = stable_id("chapter", lesson_id, "execution_flow")
    ch_recap_id = stable_id("chapter", lesson_id, "recap")

    # Orientation Scene
    intro_scene_id = stable_id("scene", lesson_id, "intro")
    scenes.append({
        "scene_id": intro_scene_id,
        "chapter_id": ch_foundations_id,
        "order": 1,
        "kind": "orientation",
        "visual_type": "summary",
        "title": "Learning Objective & System Scope",
        "narration": f"In this guided technical lesson, we will explore: {goal}. The analysis is strictly grounded in the verified static revision of {snapshot.repositories[0].name if snapshot.repositories else 'the repository'}.",
        "evidence_ids": [e.evidence_id for e in snapshot.evidence[:3]],
        "source_refs": list(dict.fromkeys(e.source_path for e in snapshot.evidence[:3])),
        "duration_ms": 7000,
        "invariants": [
            "Evidence is derived from static syntax and call graph analysis",
            "Component responsibilities separate routing, business logic, and data entities",
        ],
        "limitations": [
            "Dynamic runtime behaviors and external network calls require live telemetry",
        ],
    })

    # Concept Walkthrough Scenes (ordered by prerequisites)
    step_order = 1
    for unit in plan.teaching_units:
        comp_id = unit.associated_component_ids[0] if unit.associated_component_ids else None
        comp = understandings.get(comp_id) if comp_id else None

        if unit.depth_level in {1, 2, 3} and comp:
            sc_id = stable_id("scene", lesson_id, comp.name)
            ex_obj = unit.source_excerpts[0] if unit.source_excerpts else {}
            causal_expl = cause_engine.explain_component(comp)
            scenes.append({
                "scene_id": sc_id,
                "chapter_id": ch_foundations_id,
                "order": len(scenes) + 1,
                "kind": "code_walkthrough",
                "visual_type": "code_walkthrough",
                "title": unit.title,
                "narration": cause_engine.generate_teacher_narration(comp),
                "evidence_ids": comp.evidence_ids,
                "source_refs": [f"{comp.file_path}:{comp.line_range[0]}-{comp.line_range[1]}"],
                "code_excerpt": ex_obj.get("code", ""),
                "takeaway": unit.takeaway,
                "highlight_line": 2,
                "counterfactual": causal_expl.counterfactual_analysis,
                "duration_ms": 7500,
            })

            # Interactive Step
            st_id = stable_id("step", lesson_id, comp.name)
            prereq_steps = [step_ids[-1]] if step_ids else []
            steps.append({
                "step_id": st_id,
                "order": step_order,
                "prerequisite_step_ids": prereq_steps,
                "objective": unit.learning_objective,
                "scene_ids": [sc_id],
                "completion_criteria": {"question_score_min": 0.7, "minimum_evidence_refs": 1},
                "status": "available" if not prereq_steps else "locked",
                "support_options": ["replay_scene", "show_source_excerpt", "hint_concept"],
            })
            step_ids.append(st_id)
            step_order += 1

        elif unit.depth_level == 4:
            # End-to-end flow scene
            sc_id = stable_id("scene", lesson_id, "flow")
            flow_narr = cause_engine.generate_flow_narration(paths[0]) if paths else f"Tracing execution across component boundaries: {unit.running_example_step or 'Data enters the API route handler, passes to domain loading services, and constructs typed entity models.'} {unit.takeaway}"
            flow_steps = []
            if paths:
                for idx, st in enumerate(paths[0].steps[:6], 1):
                    target_comp = understandings.get(st.target_component_id) if st.target_component_id else None
                    source_comp = understandings.get(st.source_component_id) if st.source_component_id else None
                    name = (target_comp.name if target_comp else None) or (source_comp.name if source_comp else None) or st.operation_type
                    source_ref = f"{source_comp.file_path}:{source_comp.line_range[0]}" if source_comp else None
                    flow_steps.append({
                        "step_number": idx,
                        "component_name": name,
                        "operation_type": st.operation_type,
                        "description": st.description,
                        "source_ref": source_ref,
                    })

            scenes.append({
                "scene_id": sc_id,
                "chapter_id": ch_flow_id,
                "order": len(scenes) + 1,
                "kind": "data_flow",
                "visual_type": "data_flow",
                "title": "Complete Execution Flow",
                "narration": flow_narr,
                "evidence_ids": unit.evidence_ids,
                "source_refs": list(dict.fromkeys(e.source_path for e in snapshot.evidence if e.evidence_id in unit.evidence_ids)),
                "flow_nodes": [c.name for c in understandings.values() if c.kind in {"function", "class"}][:4],
                "execution_steps": flow_steps,
                "takeaway": unit.takeaway,
                "duration_ms": 8500,
            })
            st_id = stable_id("step", lesson_id, "flow")
            steps.append({
                "step_id": st_id,
                "order": step_order,
                "prerequisite_step_ids": [step_ids[-1]] if step_ids else [],
                "objective": unit.learning_objective,
                "scene_ids": [sc_id],
                "completion_criteria": {"question_score_min": 0.8, "minimum_evidence_refs": 2},
                "status": "locked",
                "support_options": ["hint_concept", "replay_scene", "show_source_excerpt"],
            })
            step_ids.append(st_id)
            step_order += 1

    # Recap Scene
    recap_scene_id = stable_id("scene", lesson_id, "recap")
    scenes.append({
        "scene_id": recap_scene_id,
        "chapter_id": ch_recap_id,
        "order": len(scenes) + 1,
        "kind": "recap",
        "visual_type": "summary",
        "title": "Verified Architecture & Limitations",
        "narration": "In summary, verified static relationships establish the call sequence and data transformations. Runtime database connectivity and network latency remain unverified without live telemetry.",
        "evidence_ids": [],
        "source_refs": [],
        "invariants": [
            "Typed entity models enforce strict parameter contracts",
            "Gateway routes isolate HTTP interfaces from underlying business domain logic",
        ],
        "limitations": [
            "Asynchronous external HTTP delays and exceptions are unmodeled",
            "Database connection pools are not statically observable",
        ],
        "duration_ms": 6500,
    })

    chapters = [
        {"chapter_id": ch_foundations_id, "title": "Core Architecture & Components", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == ch_foundations_id]},
        {"chapter_id": ch_flow_id, "title": "Execution Flow & Data Lineage", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == ch_flow_id]},
        {"chapter_id": ch_recap_id, "title": "Recap & Verified Invariants", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == ch_recap_id]},
    ]
    chapters = [ch for ch in chapters if ch["scene_ids"]]

    # Generate active learning checkpoints
    chk_gen = CheckpointGenerator(understandings, paths, gaps)
    checkpoints = chk_gen.generate_checkpoints_for_lesson(scenes)
    chk_dicts = [c.model_dump(mode="json") for c in checkpoints]
    
    # Attach checkpoint to matching scene
    for chk in chk_dicts:
        for s in scenes:
            if s["scene_id"] == chk["scene_id"]:
                s["checkpoint"] = chk

    all_evidence = all(s["evidence_ids"] or s["kind"] == "recap" for s in scenes)
    return LessonPlan(
        lesson_id=lesson_id,
        repository_id=repo_id,
        pkm_revision_id=snapshot.revision.pkm_revision_id,
        title=goal,
        chapters=chapters,
        scenes=scenes,
        steps=steps,
        validation_status="validated" if all_evidence else "warning",
        checkpoints=chk_dicts,
    )
