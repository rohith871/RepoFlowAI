from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.ids import stable_id
from backend.models import PkmSnapshot


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


def plan_lesson(snapshot: PkmSnapshot, goal: str = "Understand the repository architecture") -> LessonPlan:
    lesson_id = stable_id("lesson", snapshot.revision.repository_id, snapshot.revision.pkm_revision_id, goal)
    repo_id = snapshot.revision.repository_id
    chapter_id = stable_id("chapter", lesson_id, "architecture")
    scenes: list[dict[str, Any]] = []
    scenes.append({"scene_id": stable_id("scene", lesson_id, "intro"), "chapter_id": chapter_id, "order": 1, "kind": "orientation", "title": "What this repository does", "narration": f"We will understand {goal.lower()} using the analysed source repository.", "evidence_ids": [e.evidence_id for e in snapshot.evidence[:3]], "source_refs": [e.source_path for e in snapshot.evidence[:3]], "duration_ms": 7000})
    for index, symbol in enumerate(snapshot.symbols[:6], start=2):
        symbol_evidence = [e.evidence_id for e in snapshot.evidence if e.file_id == symbol.file_id and e.line_start == symbol.line_start]
        scenes.append({"scene_id": stable_id("scene", lesson_id, symbol.symbol_id), "chapter_id": chapter_id, "order": index, "kind": "code_walkthrough", "title": symbol.name, "narration": f"The {symbol.kind} {symbol.name} is declared in {symbol.qualified_name}.", "evidence_ids": symbol_evidence, "source_refs": [e.source_path for e in snapshot.evidence if e.evidence_id in symbol_evidence], "duration_ms": 7000})
    if snapshot.relationships:
        rel = snapshot.relationships[0]
        scenes.append({"scene_id": stable_id("scene", lesson_id, rel.relationship_id), "chapter_id": chapter_id, "order": len(scenes) + 1, "kind": "data_flow", "title": "How components connect", "narration": f"Static analysis identifies a {rel.relationship_type} relationship from {rel.source_id} to {rel.target_id}. The verification status is {rel.status}.", "evidence_ids": rel.evidence_ids, "source_refs": [e.source_path for e in snapshot.evidence if e.evidence_id in rel.evidence_ids], "duration_ms": 8000})
    scenes.append({"scene_id": stable_id("scene", lesson_id, "recap"), "chapter_id": chapter_id, "order": len(scenes) + 1, "kind": "recap", "title": "What remains uncertain", "narration": "The lesson separates verified findings from unresolved behaviour; revisit the source when a relationship is ambiguous.", "evidence_ids": [], "source_refs": [], "duration_ms": 6000})
    steps = [{"step_id": stable_id("step", lesson_id, "orientation"), "order": 1, "prerequisite_step_ids": [], "objective": "Identify the repository's main analysed components", "scene_ids": [scenes[0]["scene_id"]], "completion_criteria": {"question_score_min": 0.6, "minimum_evidence_refs": 1}, "status": "available", "support_options": ["replay_scene", "show_source_excerpt"]}]
    if len(scenes) > 1:
        steps.append({"step_id": stable_id("step", lesson_id, "trace"), "order": 2, "prerequisite_step_ids": [steps[0]["step_id"]], "objective": "Trace one source-backed relationship", "scene_ids": [scene["scene_id"] for scene in scenes[1:]], "completion_criteria": {"question_score_min": 0.75, "minimum_evidence_refs": 2}, "status": "locked", "support_options": ["hint_concept", "replay_scene", "show_source_excerpt"]})
    return LessonPlan(lesson_id=lesson_id, repository_id=repo_id, pkm_revision_id=snapshot.revision.pkm_revision_id, title=goal, chapters=[{"chapter_id": chapter_id, "title": "Repository architecture", "scene_ids": [scene["scene_id"] for scene in scenes]}], scenes=scenes, steps=steps, validation_status="validated" if all(scene["evidence_ids"] or scene["kind"] == "recap" for scene in scenes) else "warning")
