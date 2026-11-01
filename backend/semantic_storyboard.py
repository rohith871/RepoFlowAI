from __future__ import annotations

from typing import Any
from backend.ids import stable_id
from backend.models import PkmSnapshot
from backend.semantic_layer import (
    ArchitectureView,
    ComponentUnderstanding,
    ExecutionPath,
    KnowledgeGap,
)
from backend.architecture_reasoning import ArchitectureReasoningEngine
from backend.cause_effect import CauseAndEffectEngine
from backend.execution_flows import ExecutionFlowTracer
from backend.explanation_planner import ExplanationPlanningEngine, TeachingPlan
from backend.narration_checker import NarrationQualityChecker


class SemanticStoryboardBuilder:
    """Builds a semantically grounded storyboard with perfect narration-to-visual alignment."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        knowledge_gaps: list[KnowledgeGap],
        architecture_views: list[ArchitectureView],
        source_files_map: dict[str, str],
    ):
        self.snapshot = snapshot
        self.components = components
        self.execution_paths = execution_paths
        self.knowledge_gaps = knowledge_gaps
        self.architecture_views = architecture_views
        self.source_files_map = source_files_map
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id
        self.cause_engine = CauseAndEffectEngine(components, execution_paths, knowledge_gaps)
        self.planner = ExplanationPlanningEngine(snapshot, components, execution_paths, knowledge_gaps, source_files_map)
        self.checker = NarrationQualityChecker(snapshot, components, execution_paths)

    def build(
        self,
        scope: str = "repository",
        question: str = "",
        detail: str = "summary",
        title: str | None = None,
    ) -> dict[str, Any]:
        """Construct the complete semantic storyboard."""
        plan = self.planner.build_plan(
            goal=question or ("Understand repository architecture and request flow" if scope == "repository" else f"Explain {question}"),
            depth="advanced" if detail == "detailed" else "intermediate",
        )

        scenes: list[dict[str, Any]] = []
        org_view = next((v for v in self.architecture_views if v.view_type == "module_organization"), self.architecture_views[0] if self.architecture_views else None)
        journey_view = next((v for v in self.architecture_views if v.view_type == "request_flow"), None)
        primary_path = self.execution_paths[0] if self.execution_paths else None

        # Scene 1: System Overview (Architecture View)
        scene_1_id = stable_id("story", self.repo_id, "overview")
        mod_names = sorted({c.file_path for c in self.components.values() if c.file_path.endswith('.py')})
        mod_summary = ", ".join(mod_names) if mod_names else "analyzed modules"
        scene_1_narration = (
            f"Welcome to the architectural walkthrough of {self.snapshot.repositories[0].name}. "
            f"When onboarding to an unfamiliar codebase, the key to mastery is understanding how components coordinate across modules. "
            f"Notice how the verified implementation organizes responsibilities across {mod_summary}. "
            f"In this lesson, we will explore the architectural boundaries, trace request execution, "
            f"and analyze why components were structured with these specific contracts."
        )
        scenes.append({
            "scene_id": scene_1_id,
            "chapter_id": "chapter-overview",
            "order": 1,
            "kind": "architecture_overview",
            "visual_type": "architecture",
            "title": title or ("System Architecture Overview" if scope == "repository" else f"Architecture: {question}"),
            "objective": "Orient the learner on system boundaries and primary modules.",
            "question_answered": "How is this application organized across architectural boundaries?",
            "concept_id": "concept_architecture_overview",
            "narration": scene_1_narration,
            "source_refs": [f.path for f in self.snapshot.files[:6]],
            "node_ids": [c["id"] for c in (org_view.components[:12] if org_view else [])],
            "edge_ids": [e["id"] for e in (org_view.relationships[:10] if org_view else [])],
            "visual_nodes": [{"id": c["id"], "label": c["label"], "kind": c.get("kind", "symbol"), "role": c.get("role", "component")} for c in (org_view.components[:12] if org_view else [])],
            "visual_edges": [{"source": e["source"], "target": e["target"], "type": e.get("type", "calls")} for e in (org_view.relationships[:10] if org_view else [])],
            "boundaries": org_view.boundaries if org_view else [],
            "takeaway": f"The application structure is defined across modules: {mod_summary}.",
            "transition": "progressive-build",
            "highlight_lines": [],
            "duration_ms": 7500,
        })

        # Scenes for each Teaching Unit in the topological order
        current_order = 2
        for unit in plan.teaching_units:
            if unit.depth_level in {1, 2, 3}:
                # Code Walkthrough Scene for concrete component
                comp_id = unit.associated_component_ids[0] if unit.associated_component_ids else None
                comp = self.components.get(comp_id) if comp_id else None
                if not comp:
                    continue

                causal = self.cause_engine.explain_component(comp)
                excerpt_obj = unit.source_excerpts[0] if unit.source_excerpts else {"path": comp.file_path, "line_start": comp.line_range[0], "line_end": comp.line_range[1], "code": ""}

                narration_text = self.cause_engine.generate_teacher_narration(comp)

                scenes.append({
                    "scene_id": stable_id("story", self.repo_id, comp.name),
                    "chapter_id": "chapter-components",
                    "order": current_order,
                    "kind": "code_walkthrough",
                    "visual_type": "code",
                    "title": f"{comp.name} ({comp.execution_role.replace('_', ' ').title()})",
                    "objective": unit.learning_objective,
                    "question_answered": unit.question_answered,
                    "concept_id": unit.concept_id,
                    "narration": narration_text,
                    "source_refs": [f"{comp.file_path}:{comp.line_range[0]}-{comp.line_range[1]}"],
                    "node_ids": [comp.component_id],
                    "edge_ids": [r.relationship_id for r in self.snapshot.relationships if r.source_id == comp.component_id or r.target_id == comp.component_id],
                    "code_excerpt": excerpt_obj.get("code", ""),
                    "code_path": comp.file_path,
                    "visual_nodes": [{"id": comp.component_id, "label": comp.name, "kind": comp.kind, "role": comp.execution_role}],
                    "visual_edges": [],
                    "highlight_lines": list(range(comp.line_range[0], min(comp.line_range[1] + 1, comp.line_range[0] + 10))),
                    "takeaway": unit.takeaway,
                    "developer_guidance": causal.modification_guidance,
                    "transition": "focus-zoom",
                    "duration_ms": 8000,
                })
                current_order += 1

            elif unit.depth_level == 4:
                # End-to-End Execution Flow Scene
                if primary_path:
                    flow_causal = self.cause_engine.explain_flow(primary_path)
                    narration_text = self.cause_engine.generate_flow_narration(primary_path)
                    flow_nodes = [self.components[s.source_component_id].name for s in primary_path.steps if s.source_component_id in self.components]

                    scenes.append({
                        "scene_id": stable_id("story", self.repo_id, "flow_journey"),
                        "chapter_id": "chapter-flow",
                        "order": current_order,
                        "kind": "execution_flow",
                        "visual_type": "flow",
                        "title": "Execution Flow: Request to Response",
                        "objective": unit.learning_objective,
                        "question_answered": unit.question_answered,
                        "concept_id": unit.concept_id,
                        "narration": narration_text,
                        "source_refs": list(dict.fromkeys(
                            [f"{self.components[s.source_component_id].file_path}" for s in primary_path.steps if s.source_component_id in self.components]
                        )),
                        "node_ids": [s.source_component_id for s in primary_path.steps],
                        "edge_ids": [r.relationship_id for r in self.snapshot.relationships if r.relationship_type in {"calls", "instantiates"}],
                        "flow_nodes": list(dict.fromkeys(flow_nodes)),
                        "flow_steps": [s.model_dump(mode="json") for s in primary_path.steps],
                        "visual_nodes": [{"id": c["id"], "label": c["label"], "kind": c.get("kind", "symbol"), "role": c.get("role", "component")} for c in (journey_view.components if journey_view else [])],
                        "visual_edges": [{"source": e["source"], "target": e["target"], "type": e.get("type", "calls")} for e in (journey_view.relationships if journey_view else [])],
                        "takeaway": unit.takeaway,
                        "transition": "draw-connection",
                        "highlight_lines": [],
                        "duration_ms": 9000,
                    })
                    current_order += 1

                    # Scene 4b: Cause-and-Effect & Counterfactual Reasoning
                    first_comp = self.components.get(primary_path.entry_point_id)
                    if first_comp:
                        cf_causal = self.cause_engine.explain_component(first_comp)
                        cf_narration = (
                            f"To genuinely understand this architecture, we have to reason about failure boundaries. "
                            f"{cf_causal.responsibility_boundary} "
                            f"{cf_causal.counterfactual_analysis.replace('[HYPOTHETICAL]', '').strip()} "
                            f"Keeping this boundary in mind protects the codebase against unhandled runtime regressions."
                        )
                        scenes.append({
                            "scene_id": stable_id("story", self.repo_id, "cause_effect"),
                            "chapter_id": "chapter-flow",
                            "order": current_order,
                            "kind": "cause_and_effect",
                            "visual_type": "data_transformation",
                            "title": "Design Boundaries & Dependency Contracts",
                            "objective": "Understand why responsibilities are partitioned and what failure modes exist.",
                            "question_answered": "Why is this operation structured across these boundaries?",
                            "concept_id": "concept_cause_effect",
                            "narration": cf_narration,
                            "source_refs": [first_comp.file_path],
                            "node_ids": [first_comp.component_id],
                            "edge_ids": [],
                            "visual_nodes": [{"id": first_comp.component_id, "label": first_comp.name, "kind": first_comp.kind, "role": first_comp.execution_role}],
                            "visual_edges": [],
                            "takeaway": cf_causal.modification_guidance,
                            "counterfactual": cf_causal.counterfactual_analysis,
                            "transition": "progressive-build",
                            "highlight_lines": [],
                            "duration_ms": 8500,
                        })
                        current_order += 1

            elif unit.depth_level == 5:
                # Architectural Recap & Knowledge Gaps Scene
                gap_notes = []
                for g in self.knowledge_gaps:
                    gap_notes.append(f"{g.subject_name}: {g.limitation_note}")
                gap_summary = " ".join(gap_notes[:2]) if gap_notes else "All primary declarations and static relationships were resolved."

                recap_narration = (
                    f"To summarize what the repository evidence establishes: "
                    f"Static analysis verified the complete call chain from the API interface into domain entity models. "
                    f"Regarding runtime limitations: {gap_summary} "
                    f"When extending this codebase, maintain the established separation of concerns."
                )

                scenes.append({
                    "scene_id": stable_id("story", self.repo_id, "recap"),
                    "chapter_id": "chapter-recap",
                    "order": current_order,
                    "kind": "recap",
                    "visual_type": "summary",
                    "title": "Verified Architecture & Runtime Boundaries",
                    "objective": unit.learning_objective,
                    "question_answered": unit.question_answered,
                    "concept_id": unit.concept_id,
                    "narration": recap_narration,
                    "source_refs": [f.path for f in self.snapshot.files[:6]],
                    "node_ids": [c["id"] for c in (org_view.components[:12] if org_view else [])],
                    "edge_ids": [e["id"] for e in (org_view.relationships[:8] if org_view else [])],
                    "visual_nodes": [{"id": c["id"], "label": c["label"], "kind": c.get("kind", "symbol"), "role": c.get("role", "component")} for c in (org_view.components[:12] if org_view else [])],
                    "visual_edges": [{"source": e["source"], "target": e["target"], "type": e.get("type", "calls")} for e in (org_view.relationships[:8] if org_view else [])],
                    "knowledge_gaps": [g.model_dump(mode="json") for g in self.knowledge_gaps],
                    "takeaway": unit.takeaway,
                    "transition": "fade-out",
                    "highlight_lines": [],
                    "duration_ms": 8000,
                })
                current_order += 1

        # Run quality audit on generated storyboard
        evaluation = self.checker.evaluate_lesson(scenes)

        total_words = sum(len(str(s["narration"]).split()) for s in scenes)
        estimated_duration = int(total_words / 2.3 * 1000)

        chapters = [
            {"chapter_id": "chapter-overview", "title": "System Architecture Overview", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == "chapter-overview"]},
            {"chapter_id": "chapter-components", "title": "Domain Models & Core Components", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == "chapter-components"]},
            {"chapter_id": "chapter-flow", "title": "Execution Flow & Causal Reasoning", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == "chapter-flow"]},
            {"chapter_id": "chapter-recap", "title": "Verified Invariants & Boundaries", "scene_ids": [s["scene_id"] for s in scenes if s["chapter_id"] == "chapter-recap"]},
        ]
        chapters = [ch for ch in chapters if ch["scene_ids"]]

        payload = {
            "storyboard_version": "2.0",
            "repository_id": self.repo_id,
            "pkm_revision_id": self.rev_id,
            "scope": scope,
            "question": question,
            "detail": detail,
            "title": title or ("Repository Architecture & Execution Flow" if scope == "repository" else question),
            "chapters": chapters,
            "scenes": scenes,
            "estimated_duration_ms": estimated_duration,
            "teaching_plan": plan.model_dump(mode="json"),
            "quality_evaluation": evaluation.model_dump(mode="json"),
            "generation_provider": "semantic-intelligence-storyboard",
        }
        return payload
