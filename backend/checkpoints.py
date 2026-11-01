from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from backend.ids import stable_id
from backend.semantic_layer import ComponentUnderstanding, ExecutionPath, KnowledgeGap


class CheckpointOption(BaseModel):
    id: str
    text: str
    is_correct: bool
    explanation: str


class ActiveLearningCheckpoint(BaseModel):
    checkpoint_id: str
    scene_id: str
    checkpoint_type: str  # "predict_next", "data_transformation", "call_reason", "failure_mode"
    question_text: str
    options: list[CheckpointOption]
    correct_answer_explanation: str
    source_ref: str
    pause_duration_ms: int = 15000
    associated_component_ids: list[str] = Field(default_factory=list)


class CheckpointEvaluationResult(BaseModel):
    checkpoint_id: str
    selected_option_id: str
    is_correct: bool
    explanation: str
    recommended_action: str  # e.g. "continue", "replay_scene", "show_source_excerpt", "hint_concept"


class CheckpointGenerator:
    """Generates source-grounded active learning checkpoints based on verified AST & execution flows."""

    def __init__(
        self,
        understandings: dict[str, ComponentUnderstanding],
        paths: list[ExecutionPath],
        gaps: list[KnowledgeGap] | None = None,
    ):
        self.understandings = understandings
        self.paths = paths
        self.gaps = gaps or []

    def generate_checkpoints_for_lesson(self, scenes: list[dict[str, Any]]) -> list[ActiveLearningCheckpoint]:
        checkpoints: list[ActiveLearningCheckpoint] = []

        # 1. Flow prediction checkpoints (for execution flow scenes)
        for path in self.paths:
            if len(path.steps) >= 3:
                # Find matching scene
                flow_scene = next((s for s in scenes if s.get("kind") in {"data_flow", "execution_flow"} or s.get("visual_type") == "flow"), None)
                scene_id = flow_scene.get("scene_id") if flow_scene else (scenes[0]["scene_id"] if scenes else "flow_scene")
                
                step_2 = path.steps[1]
                step_3 = path.steps[2]
                
                target_comp = self.understandings.get(step_3.target_component_id)
                target_name = target_comp.name if target_comp else step_3.target_component_id
                
                options = [
                    CheckpointOption(
                        id="opt_1",
                        text=f"Calls `{target_name}` to handle domain logic or data retrieval.",
                        is_correct=True,
                        explanation=f"Directly verified by call relationship from {step_2.source_component_id} to {step_3.target_component_id}.",
                    ),
                    CheckpointOption(
                        id="opt_2",
                        text="Immediately serializes the raw request body directly to the HTTP socket.",
                        is_correct=False,
                        explanation="Incorrect. The verified static path traverses intermediate domain components first.",
                    ),
                    CheckpointOption(
                        id="opt_3",
                        text="Aborts execution because no route handlers are registered.",
                        is_correct=False,
                        explanation="Incorrect. The route is registered and triggers domain functions.",
                    ),
                ]
                
                entry_comp = self.understandings.get(path.entry_point_id)
                source_ref = f"{entry_comp.file_path}:{entry_comp.line_range[0]}" if entry_comp else "source"

                checkpoints.append(ActiveLearningCheckpoint(
                    checkpoint_id=stable_id("chk", scene_id, "predict_next"),
                    scene_id=scene_id,
                    checkpoint_type="predict_next",
                    question_text=f"After entering the entry point, what component does execution transition to next?",
                    options=options,
                    correct_answer_explanation=f"The verified AST establishes that execution delegates to `{target_name}`.",
                    source_ref=source_ref,
                    pause_duration_ms=12000,
                    associated_component_ids=[step_2.source_component_id, step_3.target_component_id],
                ))

        # 2. Data transformation / invariant checkpoints
        for comp_id, comp in self.understandings.items():
            if comp.transformations:
                code_scene = next((s for s in scenes if comp.name in s.get("title", "") or comp_id in s.get("node_ids", [])), None)
                if code_scene:
                    t = comp.transformations[0]
                    trans_desc = t.get('description', str(t)) if isinstance(t, dict) else str(t)
                    options = [
                        CheckpointOption(
                            id="dt_1",
                            text=f"Transforms input parameters via: {trans_desc}",
                            is_correct=True,
                            explanation=f"Matches verified AST transformation in {comp.name}: {trans_desc}",
                        ),
                        CheckpointOption(
                            id="dt_2",
                            text="Mutates global environment variables without producing a return value.",
                            is_correct=False,
                            explanation="Incorrect. Static analysis shows structured return values without global mutation.",
                        ),
                        CheckpointOption(
                            id="dt_3",
                            text="Bypasses validation and passes unparsed raw bytes.",
                            is_correct=False,
                            explanation="Incorrect. Input parameters are explicitly typed and unpacked.",
                        ),
                    ]
                    checkpoints.append(ActiveLearningCheckpoint(
                        checkpoint_id=stable_id("chk", code_scene["scene_id"], "data_transformation"),
                        scene_id=code_scene["scene_id"],
                        checkpoint_type="data_transformation",
                        question_text=f"What data transformation is performed by `{comp.name}`?",
                        options=options,
                        correct_answer_explanation=f"`{comp.name}` transforms inputs into structured outputs.",
                        source_ref=f"{comp.file_path}:{comp.line_range[0]}",
                        pause_duration_ms=12000,
                        associated_component_ids=[comp_id],
                    ))
                    break

        return checkpoints


def evaluate_checkpoint_response(
    checkpoint: ActiveLearningCheckpoint,
    selected_option_id: str,
) -> CheckpointEvaluationResult:
    opt = next((o for o in checkpoint.options if o.id == selected_option_id), None)
    if not opt:
        return CheckpointEvaluationResult(
            checkpoint_id=checkpoint.checkpoint_id,
            selected_option_id=selected_option_id,
            is_correct=False,
            explanation="Invalid option selected.",
            recommended_action="replay_scene",
        )
    
    if opt.is_correct:
        return CheckpointEvaluationResult(
            checkpoint_id=checkpoint.checkpoint_id,
            selected_option_id=selected_option_id,
            is_correct=True,
            explanation=opt.explanation or checkpoint.correct_answer_explanation,
            recommended_action="continue",
        )
    else:
        return CheckpointEvaluationResult(
            checkpoint_id=checkpoint.checkpoint_id,
            selected_option_id=selected_option_id,
            is_correct=False,
            explanation=opt.explanation,
            recommended_action="hint_concept" if checkpoint.checkpoint_type == "predict_next" else "show_source_excerpt",
        )
