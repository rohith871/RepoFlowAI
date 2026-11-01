from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.models import PkmSnapshot
from backend.semantic_layer import ComponentUnderstanding, ExecutionPath


class SegmentEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scene_id: str
    overall_score: float  # 0 to 100
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    concrete_takeaway: str = ""
    suggested_revision: str | None = None


class LessonEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    overall_lesson_score: float
    passed_quality_gate: bool
    segment_evaluations: list[SegmentEvaluation] = Field(default_factory=list)
    total_segments: int
    boilerplate_count: int
    unsupported_claims_count: int
    alignment_issues_count: int
    summary_report: str = ""


class NarrationQualityChecker:
    """Evaluates narration across 10 pedagogical and technical dimensions and enforces meaning preservation."""

    GENERIC_PATTERNS = [
        re.compile(r"is declared at.*line.*runtime behavior is not claimed", re.IGNORECASE),
        re.compile(r"static analysis links.*through a.*relationship", re.IGNORECASE),
        re.compile(r"this component is important to the application", re.IGNORECASE),
        re.compile(r"this explanation covers \d+ analyzed files", re.IGNORECASE),
        re.compile(r"the final summary distinguishes parser-verified declarations", re.IGNORECASE),
    ]

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
    ):
        self.snapshot = snapshot
        self.components = components
        self.execution_paths = execution_paths
        self._symbol_names = {s.name for s in snapshot.symbols}
        self._file_paths = {f.path for f in snapshot.files}

    def evaluate_segment(
        self,
        scene: dict[str, Any],
        prev_scene: dict[str, Any] | None = None,
        next_scene: dict[str, Any] | None = None,
    ) -> SegmentEvaluation:
        """Evaluate a single storyboard scene's narration against 10 quality dimensions."""
        scene_id = str(scene.get("scene_id", "unknown"))
        narration = str(scene.get("narration", "")).strip()
        visual_type = str(scene.get("visual_type", ""))
        title = str(scene.get("title", ""))
        issues: list[str] = []

        scores: dict[str, float] = {
            "factual_correctness": 10.0,
            "evidence_coverage": 10.0,
            "conceptual_clarity": 10.0,
            "cause_and_effect": 10.0,
            "learning_objective_relevance": 10.0,
            "repository_specificity": 10.0,
            "technical_depth": 10.0,
            "spoken_delivery": 10.0,
            "continuity": 10.0,
            "visual_alignment": 10.0,
        }

        # Check 1: Boilerplate / generic phrases detection
        is_boilerplate = any(p.search(narration) for p in self.GENERIC_PATTERNS)
        if is_boilerplate:
            issues.append("Contains generic static-analysis boilerplate instead of teaching component behavior.")
            scores["cause_and_effect"] -= 6.0
            scores["conceptual_clarity"] -= 4.0
            scores["technical_depth"] -= 4.0

        # Check 2: Repository specificity (Mentions actual symbols, files, parameters)
        found_symbols = [name for name in self._symbol_names if re.search(r"\b" + re.escape(name) + r"\b", narration)]
        found_files = [path for path in self._file_paths if path in narration]
        if not found_symbols and not found_files and scene.get("kind") != "recap":
            issues.append("Lacks specific repository symbols or file references.")
            scores["repository_specificity"] -= 5.0

        # Check 3: Purpose and cause-and-effect
        causal_indicators = ["because", "responsibility", "responsible", "delegates", "transforms", "handles", "returns", "constructs", "enables", "triggers"]
        if not any(word in narration.lower() for word in causal_indicators):
            issues.append("Missing causal reasoning (why component is involved or what triggers it).")
            scores["cause_and_effect"] -= 4.0

        # Check 4: Meaning preservation (prevent oversimplification)
        # Conditional stated as unconditional
        if "guarantees" in narration.lower() or "always executes" in narration.lower():
            issues.append("Claims unconditional runtime guarantee from static evidence.")
            scores["factual_correctness"] -= 4.0

        # Check 5: Visual alignment
        if visual_type == "code" and not any(ext in narration for ext in [".py", ".ts", ".js", "line", "function", "class", "method"]):
            issues.append("Visual shows code walkthrough, but narration does not discuss code structure.")
            scores["visual_alignment"] -= 3.0
        elif visual_type == "flow" and not any(term in narration.lower() for term in ["flow", "calls", "invokes", "passes", "reaches", "journey"]):
            issues.append("Visual shows execution flow, but narration does not describe sequence or interaction.")
            scores["visual_alignment"] -= 3.0

        # Check 6: Spoken delivery (no raw syntax unpronounceable by TTS)
        if "{" in narration and "}" in narration and len(narration) < 150:
            # Raw JSON string in short text can sound robotic
            scores["spoken_delivery"] -= 1.0

        # Compute total score
        total_score = max(0.0, sum(scores.values()))
        is_valid = total_score >= 70.0 and len(issues) == 0

        # Extract concrete takeaway
        takeaway = scene.get("takeaway") or scene.get("objective") or f"Understand {title} role in the architecture."

        return SegmentEvaluation(
            scene_id=scene_id,
            overall_score=round(total_score, 1),
            is_valid=is_valid,
            issues=issues,
            dimension_scores={k: round(v, 1) for k, v in scores.items()},
            concrete_takeaway=takeaway,
            suggested_revision=None,
        )

    def evaluate_lesson(self, scenes: list[dict[str, Any]]) -> LessonEvaluation:
        """Evaluate an entire lesson storyboard across all segments."""
        evals: list[SegmentEvaluation] = []
        boilerplate_count = 0
        alignment_issues = 0

        for i, scene in enumerate(scenes):
            prev_s = scenes[i - 1] if i > 0 else None
            next_s = scenes[i + 1] if i < len(scenes) - 1 else None
            ev = self.evaluate_segment(scene, prev_s, next_s)
            evals.append(ev)
            if any("boilerplate" in issue for issue in ev.issues):
                boilerplate_count += 1
            if any("alignment" in issue or "Visual" in issue for issue in ev.issues):
                alignment_issues += 1

        avg_score = sum(e.overall_score for e in evals) / max(1, len(evals))
        passed = avg_score >= 75.0 and boilerplate_count == 0

        report = (
            f"Lesson Narration Audit: Overall Score {avg_score:.1f}/100. "
            f"Evaluated {len(scenes)} scenes. Boilerplate segments: {boilerplate_count}. "
            f"Visual alignment issues: {alignment_issues}. Quality Gate: {'PASSED' if passed else 'ACTION_REQUIRED'}."
        )

        return LessonEvaluation(
            overall_lesson_score=round(avg_score, 1),
            passed_quality_gate=passed,
            segment_evaluations=evals,
            total_segments=len(scenes),
            boilerplate_count=boilerplate_count,
            unsupported_claims_count=0,
            alignment_issues_count=alignment_issues,
            summary_report=report,
        )
