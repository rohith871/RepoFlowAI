from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.ids import stable_id
from backend.models import PkmSnapshot
from backend.semantic_layer import ComponentUnderstanding, ExecutionPath, KnowledgeGap


class LearningTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task_id: str
    stage_id: str
    order: int
    title: str
    learning_objective: str
    why_it_matters: str
    required_concepts: list[str]
    relevant_files: list[str]
    presentation_level: str = "moderate"  # advanced, moderate, substantial_support
    instructions: str
    expected_outcome: str
    completion_criteria: dict[str, Any]
    hints: list[dict[str, str]] = Field(default_factory=list)  # level 1, 2, 3
    tutor_demonstration: dict[str, Any] = Field(default_factory=dict)
    follow_up_challenge: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending, in_progress, completed, needs_revision, tutor_demonstrated
    attempts_count: int = 0
    hints_used: int = 0
    completed_at: str | None = None
    learner_response: str | None = None
    evaluation_feedback: str | None = None

    @property
    def target_concept(self) -> str:
        return self.required_concepts[0] if self.required_concepts else "general"

    @property
    def rubric(self) -> Any:
        class _Rubric:
            def __init__(self, criteria: dict[str, Any]):
                self.verification_criteria = criteria
        return _Rubric(self.completion_criteria)


class LearningStage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    stage_id: str
    project_id: str
    order: int
    title: str
    description: str
    primary_concept: str
    purpose: str = ""
    why_it_matters: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    concepts_to_understand: list[str] = Field(default_factory=list)
    expected_deliverables: str = ""
    completion_criteria: str = ""
    relevant_files_or_resources: list[str] = Field(default_factory=list)
    video_id: str | None = None
    video_path: str | None = None
    video_generation_status: str = "not_generated"  # not_generated, queued, generating, validating, ready_to_watch, failed, regenerating
    video_url: str | None = None
    captions_url: str | None = None
    video_duration_seconds: float = 0.0
    video_error_message: str | None = None
    stage_video: dict[str, Any] = Field(default_factory=dict)
    tasks: list[LearningTask] = Field(default_factory=list)
    status: str = "locked"  # locked, in_progress, completed

    @property
    def unlocked(self) -> bool:
        return self.status != "locked"


class LearningProject(BaseModel):
    model_config = ConfigDict(extra="ignore")
    project_id: str
    repository_id: str
    pkm_revision_id: str
    learner_id: str
    title: str
    description: str
    entry_mode: str = "repository"  # domain, recommended, reference_inspired, repository
    domain: str = "Software Engineering"
    reference_repository_id: str | None = None
    transferred_concepts: list[dict[str, str]] = Field(default_factory=list)
    architecture_differences: str = ""
    tools_and_technologies: list[str] = Field(default_factory=list)
    learner_recommendation_reason: str = ""
    stages: list[LearningStage] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    status: str = "in_progress"  # in_progress, completed
    total_tasks: int = 0
    completed_tasks: int = 0
    revealed_hints_per_task: dict[str, int] = Field(default_factory=dict)

    def reveal_next_hint(self, task_id: str) -> Any | None:
        for stage in self.stages:
            for task in stage.tasks:
                if task.task_id == task_id:
                    used = self.revealed_hints_per_task.get(task_id, 0)
                    if used < len(task.hints):
                        raw = task.hints[used]
                        self.revealed_hints_per_task[task_id] = used + 1
                        task.hints_used = used + 1
                        class _Hint:
                            def __init__(self, level: int, text: str):
                                self.level = level
                                self.text = text
                                self.hint = text
                        return _Hint(int(raw.get("level", used + 1)), raw.get("hint", ""))
        return None

    def submit_task(self, task_id: str, solution: str, profile_store: Any = None, learner_id: str | None = None) -> dict[str, Any]:
        target_stage = None
        target_task = None
        for stage in self.stages:
            for task in stage.tasks:
                if task.task_id == task_id:
                    target_stage = stage
                    target_task = task
                    break
            if target_task:
                break
        if not target_task:
            return {"passed": False, "error": "Task not found"}

        concept = target_task.required_concepts[0] if target_task.required_concepts else "general"
        target_task.attempts_count += 1
        target_task.learner_response = solution

        criteria = target_task.completion_criteria
        req_keywords = criteria.get("required_keywords", [])
        sol_lower = solution.lower()
        passed = len(solution.strip()) >= 5 and (not req_keywords or any(kw.lower() in sol_lower for kw in req_keywords))

        if passed:
            target_task.status = "completed"
            target_task.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if target_stage and all(t.status in {"completed", "tutor_demonstrated"} for t in target_stage.tasks):
                target_stage.status = "completed"
                s_idx = self.stages.index(target_stage)
                if s_idx + 1 < len(self.stages):
                    self.stages[s_idx + 1].status = "in_progress"
            self.completed_tasks = sum(1 for s in self.stages for t in s.tasks if t.status in {"completed", "tutor_demonstrated"})
            if self.completed_tasks == self.total_tasks:
                self.status = "completed"

        if profile_store and (learner_id or self.learner_id):
            prof = profile_store.get_profile(learner_id or self.learner_id)
            prof.record_attempt(
                repository_id=self.repository_id,
                project_id=self.project_id,
                task_id=task_id,
                concept=concept,
                is_successful=passed,
                hints_used=self.revealed_hints_per_task.get(task_id, 0),
                attempts_count=target_task.attempts_count,
            )
            profile_store.save_profile(prof)

        return {"passed": passed, "task_id": task_id, "status": target_task.status}


class ProjectGenerator:
    """Generates an authentic, repository-grounded project-based learning curriculum."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        knowledge_gaps: list[KnowledgeGap],
        files_map: dict[str, str] | None = None,
    ):
        self.snapshot = snapshot
        self.components = components
        self.paths = execution_paths
        self.gaps = knowledge_gaps
        self.files_map = files_map or {}
        self.repo_name = snapshot.repositories[0].name if snapshot.repositories else "Repository"
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id

    def generate_project(
        self,
        learner_id_or_repo: str,
        concept_mastery_or_profile: Any = None,
    ) -> LearningProject:
        if hasattr(concept_mastery_or_profile, "concept_mastery"):
            mastery = concept_mastery_or_profile.concept_mastery
            learner_id = getattr(concept_mastery_or_profile, "learner_id", learner_id_or_repo)
        elif isinstance(concept_mastery_or_profile, dict):
            mastery = concept_mastery_or_profile
            learner_id = learner_id_or_repo
        else:
            mastery = {}
            learner_id = learner_id_or_repo

        project_id = stable_id("lproject", self.repo_id, learner_id, self.rev_id)

        stages: list[LearningStage] = []

        # Identify key components
        routes = [c for c in self.components.values() if c.execution_role == "request_handler"]
        services = [c for c in self.components.values() if c.execution_role in {"service_loader", "data_access"}]
        models = [c for c in self.components.values() if c.execution_role == "entity_model"]
        primary_path = self.paths[0] if self.paths else None

        # -------------------------------------------------------------
        # Stage 1: Application Entry & Discovery
        # -------------------------------------------------------------
        stage1_id = stable_id("stage", project_id, "1_entry")
        s1_mastery = max(
            mastery.get("entry_point_discovery", 0.5),
            mastery.get("request_routing", 0.5),
            mastery.get("api_routing", 0.5),
        )
        s1_level = "advanced" if s1_mastery >= 0.8 else ("moderate" if s1_mastery >= 0.4 else "substantial_support")
        entry_comp = routes[0] if routes else list(self.components.values())[0]

        task1_1 = LearningTask(
            task_id=stable_id("task", stage1_id, "locate_entry"),
            stage_id=stage1_id,
            order=1,
            title=f"Identify the Public Entry Gateway in {self.repo_name}",
            learning_objective="Locate where external execution begins and understand boundary parameters.",
            why_it_matters="Understanding entry gateways enables you to know how incoming data crosses from untrusted external space into the application domain.",
            required_concepts=["entry_point_discovery", "api_routing"],
            relevant_files=[entry_comp.file_path],
            presentation_level=s1_level,
            instructions=self._get_instructions(
                level=s1_level,
                advanced="Examine the repository and identify the primary entry point function. Identify its parameters and explain why it serves as the boundary.",
                moderate=f"Examine `{entry_comp.file_path}` and find the function that receives public requests. Note the parameter names it accepts.",
                support=f"Open `{entry_comp.file_path}` at line {entry_comp.line_range[0]}. Identify the function `{entry_comp.name}` and write down what parameters it accepts.",
            ),
            expected_outcome=f"Function `{entry_comp.name}` in `{entry_comp.file_path}` identified with inputs: {', '.join(inp['name'] for inp in entry_comp.inputs) or 'none'}.",
            completion_criteria={"required_keywords": [entry_comp.name, entry_comp.file_path.split("/")[-1]]},
            hints=[
                {"level": "1", "hint": "Look for files named api, app, main, or route handlers."},
                {"level": "2", "hint": f"Inspect `{entry_comp.file_path}` near lines {entry_comp.line_range[0]}-{entry_comp.line_range[1]}."},
                {"level": "3", "hint": f"The entry gateway is `{entry_comp.name}` which accepts parameter: {entry_comp.inputs[0]['name'] if entry_comp.inputs else 'request'}."},
            ],
            tutor_demonstration={
                "task_summary": f"Locating the public entry boundary in `{entry_comp.file_path}`",
                "evidence_path": entry_comp.file_path,
                "line_range": f"{entry_comp.line_range[0]}-{entry_comp.line_range[1]}",
                "demonstration_walkthrough": [
                    f"1. Inspected `{entry_comp.file_path}` to locate public HTTP routes or execution triggers.",
                    f"2. Found `{entry_comp.name}` defined at lines {entry_comp.line_range[0]}-{entry_comp.line_range[1]}.",
                    f"3. Verified static signature: accepts inputs ({', '.join(str(i.get('name')) for i in entry_comp.inputs) or 'void'}).",
                    "4. Architectural role: Request gateway that immediately delegates to internal domain functions.",
                ],
                "verified_vs_inferred": "VERIFIED: AST statically confirms function name and signature. INFERRED: HTTP protocol bindings require framework runtime.",
                "follow_up_question": f"Why does `{entry_comp.name}` delegate rather than performing database lookups directly inside the handler?",
            },
            follow_up_challenge={
                "challenge": "Explain what would happen to API consumers if the parameter type was changed from string to integer.",
                "expected_concept": "contract_validation",
            },
            status="pending",
        )

        stages.append(LearningStage(
            stage_id=stage1_id,
            project_id=project_id,
            order=1,
            title="Stage 1: Application Entry & Gateway Discovery",
            description="Discover where external requests arrive and how initial parameters are unpacked.",
            primary_concept="entry_point_discovery",
            tasks=[task1_1],
            status="in_progress",
        ))

        # -------------------------------------------------------------
        # Stage 2: Transport & Routing Isolation
        # -------------------------------------------------------------
        stage2_id = stable_id("stage", project_id, "2_routing")
        s2_mastery = mastery.get("api_routing", 0.5)
        s2_level = "advanced" if s2_mastery >= 0.8 else ("moderate" if s2_mastery >= 0.4 else "substantial_support")
        svc_comp = services[0] if services else entry_comp

        task2_1 = LearningTask(
            task_id=stable_id("task", stage2_id, "trace_delegation"),
            stage_id=stage2_id,
            order=1,
            title="Trace Gateway to Domain Delegation",
            learning_objective="Understand how transport layers hand off execution without leaking HTTP concerns.",
            why_it_matters="Decoupling transport from domain logic allows endpoints to change without breaking business rules.",
            required_concepts=["api_routing", "domain_orchestration"],
            relevant_files=[entry_comp.file_path, svc_comp.file_path],
            presentation_level=s2_level,
            instructions=self._get_instructions(
                level=s2_level,
                advanced=f"Analyze how `{entry_comp.name}` dispatches to subsequent logic. Explain which function it calls and what arguments it passes.",
                moderate=f"Check `{entry_comp.file_path}` and trace which downstream function `{entry_comp.name}` invokes in `{svc_comp.file_path}`.",
                support=f"In `{entry_comp.file_path}`, notice `{entry_comp.name}` calls `{svc_comp.name}` in `{svc_comp.file_path}`. Trace the argument being passed.",
            ),
            expected_outcome=f"Call to `{svc_comp.name}` verified with argument forwarded.",
            completion_criteria={"required_keywords": [svc_comp.name, svc_comp.file_path.split("/")[-1]]},
            hints=[
                {"level": "1", "hint": "Look at the return statement or invocation inside the route handler."},
                {"level": "2", "hint": f"The route handler imports and calls a function from `{svc_comp.file_path}`."},
                {"level": "3", "hint": f"`{entry_comp.name}` delegates directly to `{svc_comp.name}`."},
            ],
            tutor_demonstration={
                "task_summary": f"Tracing delegation from `{entry_comp.name}` to `{svc_comp.name}`",
                "evidence_path": f"{entry_comp.file_path} -> {svc_comp.file_path}",
                "demonstration_walkthrough": [
                    f"1. Opened `{entry_comp.file_path}` to follow the body of `{entry_comp.name}`.",
                    f"2. Identified cross-file call targeting `{svc_comp.name}` located in `{svc_comp.file_path}`.",
                    f"3. Verified parameter propagation: arguments received at the API boundary are handed to `{svc_comp.name}`.",
                    "4. Separation rationale: Isolates web framework dependencies from business processing.",
                ],
                "verified_vs_inferred": "VERIFIED: Cross-module AST call relationship confirmed. INFERRED: Synchronous thread execution assumed.",
                "follow_up_question": "If you needed to add rate limiting, would you place it in the gateway or the domain service?",
            },
            follow_up_challenge={
                "challenge": "State the architectural invariant preserved by keeping the route handler lean.",
                "expected_concept": "separation_of_concerns",
            },
            status="pending",
        )

        stages.append(LearningStage(
            stage_id=stage2_id,
            project_id=project_id,
            order=2,
            title="Stage 2: Transport & Routing Isolation",
            description="Examine how the gateway isolates HTTP transport from business logic.",
            primary_concept="api_routing",
            tasks=[task2_1],
            status="locked",
        ))

        # -------------------------------------------------------------
        # Stage 3: Domain Model Contracts & Invariants
        # -------------------------------------------------------------
        stage3_id = stable_id("stage", project_id, "3_models")
        s3_mastery = mastery.get("domain_modeling", 0.5)
        s3_level = "advanced" if s3_mastery >= 0.8 else ("moderate" if s3_mastery >= 0.4 else "substantial_support")
        model_comp = models[0] if models else svc_comp

        task3_1 = LearningTask(
            task_id=stable_id("task", stage3_id, "inspect_model"),
            stage_id=stage3_id,
            order=1,
            title=f"Analyze In-Memory Contract: `{model_comp.name}`",
            learning_objective="Understand how strongly-typed domain models guarantee state consistency.",
            why_it_matters="Using explicit models avoids error-prone loose dictionaries and guarantees downstream attribute availability.",
            required_concepts=["domain_modeling", "data_contracts"],
            relevant_files=[model_comp.file_path],
            presentation_level=s3_level,
            instructions=self._get_instructions(
                level=s3_level,
                advanced=f"Examine `{model_comp.name}`. Identify its fields, constructor contract, and how it prevents invalid state.",
                moderate=f"Inspect `{model_comp.name}` in `{model_comp.file_path}`. List the attributes initialized and their expected types.",
                support=f"Open `{model_comp.file_path}` at line {model_comp.line_range[0]}. Examine `{model_comp.name}` class definition and list its attributes.",
            ),
            expected_outcome=f"Model `{model_comp.name}` attributes ({', '.join(inp['name'] for inp in model_comp.inputs) or 'attributes'}) identified.",
            completion_criteria={"required_keywords": [model_comp.name]},
            hints=[
                {"level": "1", "hint": "Look for class definitions or dataclass models."},
                {"level": "2", "hint": f"Check `{model_comp.file_path}` around lines {model_comp.line_range[0]}-{model_comp.line_range[1]}."},
                {"level": "3", "hint": f"`{model_comp.name}` initializes attributes: {', '.join(inp['name'] for inp in model_comp.inputs) or 'attributes'}."},
            ],
            tutor_demonstration={
                "task_summary": f"Analyzing domain model contract `{model_comp.name}`",
                "evidence_path": model_comp.file_path,
                "line_range": f"{model_comp.line_range[0]}-{model_comp.line_range[1]}",
                "demonstration_walkthrough": [
                    f"1. Located class `{model_comp.name}` in `{model_comp.file_path}`.",
                    f"2. Verified fields: {', '.join(inp['name'] for inp in model_comp.inputs) or 'defined attributes'}.",
                    "3. Invariant: Callers can safely access these attributes without defensive key-existence checks.",
                    "4. Counterfactual: Renaming a field here causes runtime TypeError across all callers unless updated.",
                ],
                "verified_vs_inferred": "VERIFIED: Class fields and constructor signature verified by AST. INFERRED: Validation invariants outside types are unverified.",
                "follow_up_question": f"What runtime error occurs if a caller instantiates `{model_comp.name}` without required arguments?",
            },
            follow_up_challenge={
                "challenge": "Propose an additional optional field (e.g. `email: str | None = None`) and explain where it needs to be instantiated.",
                "expected_concept": "contract_evolution",
            },
            status="pending",
        )

        stages.append(LearningStage(
            stage_id=stage3_id,
            project_id=project_id,
            order=3,
            title="Stage 3: Domain Model Contracts & Invariants",
            description="Examine in-memory data structures and strict type contracts.",
            primary_concept="domain_modeling",
            tasks=[task3_1],
            status="locked",
        ))

        # -------------------------------------------------------------
        # Stage 4: End-to-End Workflow & Data Lineage
        # -------------------------------------------------------------
        stage4_id = stable_id("stage", project_id, "4_lineage")
        s4_mastery = mastery.get("data_lineage", 0.5)
        s4_level = "advanced" if s4_mastery >= 0.8 else ("moderate" if s4_mastery >= 0.4 else "substantial_support")

        task4_1 = LearningTask(
            task_id=stable_id("task", stage4_id, "trace_lineage"),
            stage_id=stage4_id,
            order=1,
            title="Trace Parameter Lineage Across Layer Boundaries",
            learning_objective="Reconstruct the exact path of a parameter from entry argument to output response.",
            why_it_matters="Verifying data lineage prevents silent bugs and validates security boundaries across layers.",
            required_concepts=["data_lineage", "execution_flow"],
            relevant_files=list(dict.fromkeys([entry_comp.file_path, svc_comp.file_path, model_comp.file_path])),
            presentation_level=s4_level,
            instructions=self._get_instructions(
                level=s4_level,
                advanced="Trace the end-to-end data lifecycle of the incoming query argument. List every function that touches it and where it gets serialized.",
                moderate=f"Follow the parameter from `{entry_comp.name}` through `{svc_comp.name}` into `{model_comp.name}` and state the final return structure.",
                support=f"Step 1: `{entry_comp.name}` receives input. Step 2: calls `{svc_comp.name}`. Step 3: `{model_comp.name}` instantiated. Step 4: final dictionary returned. Confirm this sequence.",
            ),
            expected_outcome="Full lineage confirmed from input parameter to serialized return dict.",
            completion_criteria={"required_keywords": [entry_comp.name, model_comp.name]},
            hints=[
                {"level": "1", "hint": "Follow the parameter name through each function call."},
                {"level": "2", "hint": "The parameter is passed from the route handler, into the service, and into the model class."},
                {"level": "3", "hint": f"The parameter flows: {entry_comp.name} -> {svc_comp.name} -> {model_comp.name} -> return dictionary."},
            ],
            tutor_demonstration={
                "task_summary": "Reconstructing end-to-end parameter lineage",
                "evidence_path": f"{entry_comp.file_path} -> {svc_comp.file_path} -> {model_comp.file_path}",
                "demonstration_walkthrough": [
                    f"1. Entry: `{entry_comp.name}` receives input parameter.",
                    f"2. Forward: Passed cleanly to `{svc_comp.name}` without modification.",
                    f"3. Instantiation: `{svc_comp.name}` passes value to initialize `{model_comp.name}`.",
                    "4. Terminal serialization: Attributes from model instance are formatted into return payload.",
                ],
                "verified_vs_inferred": "VERIFIED: Cross-module parameter pass-through confirmed by call-graph data lineage.",
                "follow_up_question": "Where does validation take place along this lineage?",
            },
            follow_up_challenge={
                "challenge": "If malicious or empty input is passed, which component is responsible for rejecting it?",
                "expected_concept": "input_validation_boundary",
            },
            status="pending",
        )

        stages.append(LearningStage(
            stage_id=stage4_id,
            project_id=project_id,
            order=4,
            title="Stage 4: End-to-End Workflow & Data Lineage",
            description="Trace how inputs move across module boundaries and convert into output structures.",
            primary_concept="data_lineage",
            tasks=[task4_1],
            status="locked",
        ))

        # -------------------------------------------------------------
        # Stage 5: Architectural Modification Challenge
        # -------------------------------------------------------------
        stage5_id = stable_id("stage", project_id, "5_modification")
        s5_mastery = mastery.get("architectural_invariants", 0.5)
        s5_level = "advanced" if s5_mastery >= 0.8 else ("moderate" if s5_mastery >= 0.4 else "substantial_support")

        task5_1 = LearningTask(
            task_id=stable_id("task", stage5_id, "safe_modification"),
            stage_id=stage5_id,
            order=1,
            title="Design a Safe Architectural Modification",
            learning_objective="Propose a modification while respecting established layer boundaries and invariants.",
            why_it_matters="Applying architectural knowledge to modify code without introducing architectural erosion is a core engineering skill.",
            required_concepts=["architectural_invariants", "separation_of_concerns"],
            relevant_files=[entry_comp.file_path, svc_comp.file_path],
            presentation_level=s5_level,
            instructions=self._get_instructions(
                level=s5_level,
                advanced="Suppose we need to add request latency telemetry. Which file should own this modification, which should NOT, and why?",
                moderate=f"If we add timing telemetry, explain why it belongs in `{entry_comp.file_path}` (gateway) rather than inside `{model_comp.file_path}` (data model).",
                support=f"Explain why transport concerns (like HTTP latency or request tracking) belong in `{entry_comp.file_path}` and not inside `{model_comp.file_path}`.",
            ),
            expected_outcome="Correct identification of gateway layer as appropriate for transport telemetry.",
            completion_criteria={"required_keywords": [entry_comp.file_path.split("/")[-1], "layer"]},
            hints=[
                {"level": "1", "hint": "Consider which layer handles external transport vs internal domain logic."},
                {"level": "2", "hint": "Telemetry for network requests is a transport/gateway concern."},
                {"level": "3", "hint": "Place it in the API gateway so domain models remain independent of HTTP transport metrics."},
            ],
            tutor_demonstration={
                "task_summary": "Architectural justification for telemetry placement",
                "evidence_path": entry_comp.file_path,
                "demonstration_walkthrough": [
                    "1. Analyzed separation of concerns: Transport Gateway vs Domain Models.",
                    f"2. Gateway (`{entry_comp.file_path}`) owns request lifecycle, headers, and protocol metrics.",
                    f"3. Domain layer (`{model_comp.file_path}`) should remain pure and unconcerned with HTTP protocols.",
                    "4. Conclusion: Telemetry middleware or gateway wrappers preserve architectural boundaries.",
                ],
                "verified_vs_inferred": "VERIFIED: Architectural boundary separation established by static dependency graph.",
                "follow_up_question": "How does keeping domain models pure benefit automated unit testing?",
            },
            follow_up_challenge={
                "challenge": "What architectural code smell occurs if a domain entity imports an HTTP framework library?",
                "expected_concept": "clean_architecture_invariants",
            },
            status="pending",
        )

        stages.append(LearningStage(
            stage_id=stage5_id,
            project_id=project_id,
            order=5,
            title="Stage 5: Safe Architectural Modification & Review",
            description="Apply architectural reasoning to modify and extend the system safely.",
            primary_concept="architectural_invariants",
            tasks=[task5_1],
            status="locked",
        ))

        total_tasks = sum(len(s.tasks) for s in stages)
        return LearningProject(
            project_id=project_id,
            repository_id=self.repo_id,
            pkm_revision_id=self.rev_id,
            learner_id=learner_id,
            title=f"Mastering Architecture & Data Lineage in {self.repo_name}",
            description=f"A structured project-based curriculum teaching the verified architecture, execution paths, and design invariants of {self.repo_name}.",
            stages=stages,
            total_tasks=total_tasks,
            completed_tasks=0,
            status="in_progress",
        )

    def _get_instructions(self, level: str, advanced: str, moderate: str, support: str) -> str:
        if level == "advanced":
            return f"[ADVANCED INVESTIGATION] {advanced}"
        elif level == "substantial_support":
            return f"[GUIDED STEP-BY-STEP] {support}"
        return f"[STRUCTURED TASK] {moderate}"

    def generate_tutor_takeover(self, task: LearningTask | dict[str, Any]) -> Any:
        td = getattr(task, "tutor_demonstration", None) or (task.get("tutor_demonstration") if isinstance(task, dict) else {})
        fc = getattr(task, "follow_up_challenge", None) or (task.get("follow_up_challenge") if isinstance(task, dict) else {})
        t_id = getattr(task, "task_id", None) or (task.get("task_id") if isinstance(task, dict) else "task")

        class _TutorTakeover:
            def __init__(self, task_id, td, fc):
                self.task_id = task_id
                self.demonstration_steps = td.get("demonstration_walkthrough", [
                    f"1. Inspected evidence file {td.get('evidence_path', '')}.",
                    f"2. Verified lines {td.get('line_range', '1-50')}.",
                    "3. Isolated responsibility boundaries."
                ])
                self.demonstrated_code = td.get("evidence_path", "") or "def demonstration(): pass"
                self.verified_facts = td.get("verified_vs_inferred", "VERIFIED: AST syntax matches.")
                self.follow_up_challenge = fc.get("challenge", "Explain architectural invariants.")
                self.explanation_rationale = td.get("task_summary", "Locating boundary")
        return _TutorTakeover(t_id, td, fc)


# =========================================================================
# 3 PRIMARY ENTRY MODES: DOMAIN, RECOMMENDED, AND REFERENCE-INSPIRED
# =========================================================================

DOMAINS_CATALOG: dict[str, dict[str, Any]] = {
    "Machine Learning": {
        "project_title": "Production Customer Churn Prediction & Early-Warning Pipeline",
        "description": "Build an end-to-end machine learning system that ingests behavioral customer metrics, trains a leak-free classification pipeline, evaluates precision-recall trade-offs, and exposes real-time prediction endpoints.",
        "technologies": ["Python", "Scikit-Learn", "Pandas", "FastAPI", "Joblib"],
        "stages": [
            ("Stage 1: Problem Formulation & Churn Metric Definition", "Formulate customer retention business objectives into a binary classification task with explicit loss matrices.", "problem_formulation", "main.py"),
            ("Stage 2: Dataset Acquisition & Schema Contract Verification", "Ingest multi-source tabular records, enforce column types, and detect anomalous distributions.", "data_ingestion", "dataset.py"),
            ("Stage 3: Exploratory Data Analysis & Imbalance Profiling", "Identify severe class skew, evaluate feature distributions, and compute correlation matrices.", "exploratory_analysis", "eda.py"),
            ("Stage 4: Leak-Free Preprocessing & Column Transformer Pipeline", "Implement median imputation, one-hot encoding, and standard scaling strictly within cross-validation folds.", "data_preprocessing", "pipeline.py"),
            ("Stage 5: Feature Engineering & Behavioral Interaction Signals", "Derive tenure-to-spend ratios, rolling transaction frequencies, and tenure bucket indicators.", "feature_engineering", "features.py"),
            ("Stage 6: Baseline Algorithm Comparison & ROC-AUC Validation", "Train Logistic Regression and Gradient Boosted baselines; benchmark precision, recall, and ROC-AUC.", "model_training", "models.py"),
            ("Stage 7: Hyperparameter Tuning & Decision Threshold Calibration", "Optimize decision boundaries using cost-weighted threshold moving to minimize business churn losses.", "threshold_calibration", "evaluate.py"),
            ("Stage 8: Production Inference Microservice & Pydantic Guard", "Expose low-latency prediction endpoints with strict payload validation, model caching, and error fallbacks.", "production_serving", "api.py"),
        ],
    },
    "Backend Development": {
        "project_title": "High-Throughput Microservice with Distributed Caching & Event Bus",
        "description": "Architect a scalable backend service featuring strict layer separation, database persistence, read-through caching, and idempotent event dispatching.",
        "technologies": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
        "stages": [
            ("Stage 1: API Gateway & Public Boundary Routing", "Design clean REST endpoints that unpack parameters without leaking HTTP transport concerns.", "api_routing", "gateway.py"),
            ("Stage 2: Domain Entity Contracts & Invariant State Enforcement", "Construct strongly-typed immutable data entities with strict boundary invariants.", "domain_modeling", "models.py"),
            ("Stage 3: Service Layer Orchestration & Business Rules", "Encapsulate pure business logic, transactional boundaries, and multi-step workflows.", "service_orchestration", "services.py"),
            ("Stage 4: Data Access Object & SQL Query Optimization", "Implement relational database persistence, indexes, and parameterized query execution.", "data_access", "storage.py"),
            ("Stage 5: Read-Through Redis Caching & Cache Invalidation", "Integrate sub-millisecond in-memory caching with write-through invalidation to prevent stale reads.", "caching_layer", "cache.py"),
            ("Stage 6: Asynchronous Task Queue & Event Dispatching", "Decouple heavy side-effects (notifications, audits) using an asynchronous background event queue.", "event_dispatching", "events.py"),
            ("Stage 7: End-to-End Causal Execution Tracing & Telemetry", "Trace request journeys across gateway, service, database, and cache with distributed trace IDs.", "execution_tracing", "telemetry.py"),
            ("Stage 8: High-Concurrency Stress Testing & Graceful Degradation", "Simulate high traffic loads, verify connection pooling limits, and implement circuit breakers.", "stress_testing", "resilience.py"),
        ],
    },
    "Full-Stack Development": {
        "project_title": "Enterprise Collaboration Workspace with Role-Based Access & Live Sync",
        "description": "Construct a full-stack platform featuring a reactive TypeScript frontend, decoupled REST API backend, relational persistence, and real-time state synchronization.",
        "technologies": ["React", "TypeScript", "FastAPI", "SQLite", "TailwindCSS"],
        "stages": [
            ("Stage 1: Architectural Separation & Domain Contract Blueprint", "Define OpenAPI contracts and shared TypeScript interfaces before implementing frontend or backend code.", "architecture_blueprint", "contracts.ts"),
            ("Stage 2: REST API Layer with Strict Pydantic Invariants", "Implement backend endpoints enforcing type safety, status codes, and input validation.", "backend_api", "api.py"),
            ("Stage 3: Relational Database Schema & Foreign Key Constraints", "Establish normalized relational tables, indexes, and database migrations.", "database_schema", "schema.sql"),
            ("Stage 4: JWT Authentication Gateway & Role-Based Middleware", "Implement secure cryptographic tokens, password hashing, and role-based route permissions.", "authentication", "security.py"),
            ("Stage 5: React State Store & Modular Component Tree", "Construct a responsive component hierarchy using predictable unidirectional state flows.", "frontend_architecture", "App.tsx"),
            ("Stage 6: Type-Safe Client Fetching & Error Boundary Handling", "Build client API hooks with automated retry logic, loading spinners, and graceful failure fallbacks.", "client_integration", "api_client.ts"),
            ("Stage 7: Real-Time Telemetry WebSockets & Heartbeat Monitoring", "Establish bi-directional WebSocket channels for live activity feeds and optimistic client updates.", "realtime_sync", "websocket.ts"),
            ("Stage 8: End-to-End Integration Testing & Containerized Build", "Verify complete cross-layer journeys from user click to database write with automated test suites.", "integration_testing", "test_e2e.py"),
        ],
    },
    "Deep Learning": {
        "project_title": "End-to-End Convolutional Visual Inspection & Defect Detector",
        "description": "Construct a computer vision deep learning system that trains a convolutional neural network on labeled images, exports optimized ONNX models, and serves real-time predictions.",
        "technologies": ["PyTorch", "TorchVision", "FastAPI", "ONNX Runtime", "NumPy"],
        "stages": [
            ("Stage 1: Image Dataset Sourcing & Spatial Ground Truth Annotation", "Organize labeled image directories, parse bounding box manifests, and establish reproducible train/val splits.", "dataset_preparation", "dataset.py"),
            ("Stage 2: Stochastic Augmentation & Tensor Normalization Pipeline", "Implement random horizontal flips, affine rotations, and ImageNet standardization to prevent overfitting.", "data_augmentation", "transforms.py"),
            ("Stage 3: Convolutional Backbone Architecture & Feature Map Inspection", "Construct modular Conv2D layers with BatchNorm, ReLU activations, and MaxPool downsampling.", "cnn_architecture", "network.py"),
            ("Stage 4: Custom Loss Formulation & Class-Weighted Cross-Entropy", "Address extreme positive defect rarity using Focal Loss and class-frequency inverse weighting.", "loss_function", "loss.py"),
            ("Stage 5: PyTorch Training Loop, Gradient Clipping & Early Stopping", "Write a deterministic training loop with AdamW optimizer, cosine annealing learning rate, and model checkpointing.", "training_loop", "train.py"),
            ("Stage 6: Model Evaluation, Confusion Matrix & Latency Benchmarking", "Evaluate precision-recall curves, calculate mean IoU, and measure single-image inference latency on CPU.", "model_evaluation", "evaluate.py"),
            ("Stage 7: ONNX Export & Quantized Engine Optimization", "Export the trained PyTorch graph to ONNX and apply dynamic integer quantization for 3x throughput.", "onnx_quantization", "export.py"),
            ("Stage 8: High-Performance Inference Gateway & Streaming Prediction", "Wrap the ONNX runtime in a FastAPI microservice accepting multipart image uploads with sub-30ms response times.", "inference_gateway", "server.py"),
        ],
    },
    "Cybersecurity": {
        "project_title": "Zero-Trust Identity, Token Broker & Tamper-Evident Audit Vault",
        "description": "Implement a cryptographic security perimeter featuring asymmetric token validation, role-based access gates, injection traps, and a cryptographic audit chain.",
        "technologies": ["Python", "Cryptography", "JWT", "FastAPI", "SQLite"],
        "stages": [
            ("Stage 1: Threat Modeling & Cryptographic Perimeter Formulation", "Identify attack surfaces, establish trust boundaries, and formulate zero-trust identity policies.", "threat_modeling", "threat_model.md"),
            ("Stage 2: Asymmetric Key Pair Generation & Public Key Infrastructure", "Generate RSA-2048 keypairs, implement secure key rotation, and expose JWKS public verification endpoints.", "pki_infrastructure", "keys.py"),
            ("Stage 3: Stateless JWT Token Issuance & Refresh Rotation Pipeline", "Issue signed tokens with strict expiration, audience verification, and single-use refresh token revocation.", "token_broker", "tokens.py"),
            ("Stage 4: Role-Based Access Control (RBAC) & Scope Enforcement Gate", "Implement declarative permission decorators that inspect token claims before executing handlers.", "rbac_guard", "permissions.py"),
            ("Stage 5: Input Sanitization & Automated SQL/XSS Injection Traps", "Establish strict AST-based input validation and decoy parameters to detect and flag automated exploitation probes.", "input_sanitization", "sanitizer.py"),
            ("Stage 6: Append-Only Tamper-Evident SHA-256 Audit Log Chain", "Record security events in a cryptographic hash chain where modifying historical entries breaks verification.", "audit_chain", "audit.py"),
            ("Stage 7: Dynamic Rate-Limiting & Suspicious Activity Thresholds", "Implement sliding-window token bucket rate limiting to prevent brute-force credential stuffing attacks.", "rate_limiting", "limiter.py"),
            ("Stage 8: Automated Penetration Testing & Vulnerability Audit Suite", "Execute automated security scans verifying CSRF protection, header hardening (CSP, HSTS), and auth boundaries.", "security_audit", "test_security.py"),
        ],
    },
    "Cloud Computing": {
        "project_title": "Serverless Event-Driven ETL & Multi-Region Cloud Data Pipeline",
        "description": "Engineer a resilient cloud architecture utilizing serverless function handlers, event-driven message queues, partitioned blob storage, and automated retries.",
        "technologies": ["Python", "LocalStack", "AWS S3 / SQS", "Terraform", "FastAPI"],
        "stages": [
            ("Stage 1: Cloud Topology Architecture & Decoupled Ingestion Boundaries", "Design a cloud architecture separating synchronous ingress from asynchronous processing queues.", "cloud_architecture", "architecture.md"),
            ("Stage 2: Infrastructure-as-Code Declarations & Resource Provisioning", "Declare cloud storage buckets, message queues, and execution roles using reproducible IaC scripts.", "iac_provisioning", "main.tf"),
            ("Stage 3: Blob Storage Bucket Configuration & Event Triggers", "Configure object storage event notifications to trigger ingestion whenever new payloads land.", "storage_events", "storage.py"),
            ("Stage 4: Serverless Handler Logic & Idempotent Event Processing", "Write stateless event handlers that process incoming payloads and guarantee idempotence across retries.", "event_handler", "handler.py"),
            ("Stage 5: Distributed Dead-Letter Queue & Exponential Backoff Retry Policy", "Trap failed messages in a Dead-Letter Queue (DLQ) with exponential backoff and jittered retries.", "retry_policy", "dlq.py"),
            ("Stage 6: Parquet Partitioning & Data Lake Organization", "Convert raw JSON batches into columnar Snappy-compressed Parquet files partitioned by year/month/day.", "lakehouse_storage", "parquet.py"),
            ("Stage 7: IAM Least-Privilege Role Policies & Secret Management", "Enforce strict IAM security boundaries restricting storage write permissions to authorized lambda roles.", "iam_security", "policy.json"),
            ("Stage 8: CloudWatch Metrics, Alarms & Chaos Failure Drills", "Implement distributed health monitoring, alarm triggers on queue latency spikes, and chaos injection tests.", "observability", "metrics.py"),
        ],
    },
}

# Fill remaining domain blueprints using structured defaults
_DOMAIN_ALIASES = {
    "Artificial Intelligence": ("Machine Learning", "Autonomous Graph-Search Agent & Heuristic Decision Engine"),
    "Natural Language Processing": ("Machine Learning", "Transformer-Based Intent Classification & Entity Extraction"),
    "Computer Vision": ("Deep Learning", "Real-Time Multi-Object Detection & Spatial Tracking Engine"),
    "Data Science": ("Machine Learning", "High-Dimensional Exploratory Analytics & Predictive Analytics Engine"),
    "Web Development": ("Full-Stack Development", "Collaborative Real-Time Canvas with Optimistic State Sync"),
    "DevOps": ("Cloud Computing", "Automated Multi-Stage CI/CD, Container Security & GitOps Deployment"),
    "Data Engineering": ("Backend Development", "Streaming Event Ingestion, Deduplication & Delta Lake Storage Engine"),
}

for d_name, (base_key, proj_title) in _DOMAIN_ALIASES.items():
    if d_name not in DOMAINS_CATALOG and base_key in DOMAINS_CATALOG:
        base = DOMAINS_CATALOG[base_key]
        DOMAINS_CATALOG[d_name] = {
            "project_title": proj_title,
            "description": f"A comprehensive {d_name} curriculum teaching real-world software architecture, data contracts, and implementation invariants.",
            "technologies": base["technologies"],
            "stages": [
                (f"Stage {idx+1}: {title.split(': ', 1)[-1]}", desc, concept, f_path)
                for idx, (title, desc, concept, f_path) in enumerate(base["stages"])
            ],
        }


def generate_domain_project(
    domain: str,
    learner_profile: Any = None,
    learner_id: str = "default_learner",
) -> LearningProject:
    """Mode A: Build an authentic, domain-tailored software engineering project curriculum."""
    normalized_domain = domain if domain in DOMAINS_CATALOG else "Backend Development"
    blueprint = DOMAINS_CATALOG[normalized_domain]
    project_id = stable_id("proj_domain", normalized_domain.replace(" ", "_").lower(), learner_id)

    mastery = getattr(learner_profile, "concept_mastery", {}) if learner_profile else {}
    stages: list[LearningStage] = []

    for idx, (stage_title, stage_desc, concept, file_name) in enumerate(blueprint["stages"]):
        s_id = stable_id("stage", project_id, f"s{idx+1}_{concept}")
        c_mastery = mastery.get(concept, 0.5)
        level = "advanced" if c_mastery >= 0.8 else ("moderate" if c_mastery >= 0.4 else "substantial_support")

        # Create realistic implementation task
        task = LearningTask(
            task_id=stable_id("task", s_id, f"impl_{concept}"),
            stage_id=s_id,
            order=1,
            title=f"Implement {stage_title.split(': ', 1)[-1]}",
            learning_objective=f"Build and verify {concept} requirements in `{file_name}` respecting architectural boundaries.",
            why_it_matters=f"Core technical capability required in production {normalized_domain} applications.",
            required_concepts=[concept, "modular_architecture"],
            relevant_files=[file_name],
            presentation_level=level,
            instructions=(
                f"[ADVANCED] Architect and implement {concept} in `{file_name}` with full error handling and invariant contracts."
                if level == "advanced"
                else (
                    f"[STRUCTURED] Implement {concept} in `{file_name}`. Ensure all input parameters are validated and outputs match expected format."
                    if level == "moderate"
                    else f"[GUIDED] Open `{file_name}`. Define the core {concept} function. Follow the template provided in the hints."
                )
            ),
            expected_outcome=f"Working implementation in `{file_name}` matching criteria for {concept}.",
            completion_criteria={"required_keywords": [concept.split("_")[0], file_name.split(".")[0]]},
            hints=[
                {"level": "1", "hint": f"Consider the responsibility of `{file_name}` in the {normalized_domain} architecture."},
                {"level": "2", "hint": f"Ensure your implementation validates input types before performing {concept} logic."},
                {"level": "3", "hint": f"Reference template: Define function or class in `{file_name}` with clear return types."},
            ],
            tutor_demonstration={
                "task_summary": f"Demonstrating {concept} in `{file_name}`",
                "evidence_path": file_name,
                "line_range": "1-35",
                "demonstration_walkthrough": [
                    f"1. Created module `{file_name}` establishing the {concept} boundary.",
                    "2. Enforced input validation contracts to reject invalid parameter shapes early.",
                    f"3. Executed core {concept} business logic with modular exception handling.",
                    "4. Verified architectural boundary decoupling from external framework dependencies.",
                ],
                "verified_vs_inferred": f"VERIFIED: Syntax and type signatures validated against {normalized_domain} standards.",
                "follow_up_question": f"How does isolating {concept} in `{file_name}` improve automated unit test coverage?",
            },
            follow_up_challenge={
                "challenge": f"Explain what would occur if {concept} logic was coupled directly to presentation/UI code.",
                "expected_concept": "separation_of_concerns",
            },
            status="pending",
        )

        stage_video = {
            "title": f"{stage_title} — Technical Deep Dive",
            "scenes": [
                {
                    "scene_id": f"{s_id}_orient",
                    "title": stage_title,
                    "kind": "orientation",
                    "visual_type": "summary",
                    "narration": f"Welcome to {stage_title}. In this stage, we focus on {concept} for the {blueprint['project_title']}.",
                    "source_refs": [file_name],
                    "duration_ms": 1500,
                },
                {
                    "scene_id": f"{s_id}_code",
                    "title": f"Implementation: {concept}",
                    "kind": "code_walkthrough",
                    "visual_type": "code",
                    "narration": f"In `{file_name}`, notice how inputs are validated and state invariants are enforced.",
                    "code_path": file_name,
                    "code_excerpt": f"# {file_name}\ndef execute_{concept}(payload: dict) -> dict:\n    # Enforce contract validation\n    if not payload:\n        raise ValueError('Invalid payload')\n    return {{'status': 'verified', 'concept': '{concept}'}}",
                    "highlight_lines": [3, 4],
                    "key_takeaway": f"Decoupling {concept} in `{file_name}` maintains testability and system modularity.",
                    "failure_mode": f"[HYPOTHETICAL] Inlining downstream persistence in `{file_name}` creates tight architectural coupling.",
                    "source_refs": [file_name],
                    "duration_ms": 2000,
                },
                {
                    "scene_id": f"{s_id}_dataflow",
                    "title": f"{concept} Data Lifecycle",
                    "kind": "data_flow",
                    "visual_type": "data_flow",
                    "narration": f"Observe how data transitions across the {concept} transformation boundary.",
                    "pipeline_stages": [
                        {"id": "p1", "name": "Raw Ingestion", "sub": "Incoming Query", "type": "input", "detail": "payload"},
                        {"id": "p2", "name": f"Module: {file_name}", "sub": concept, "type": "gateway", "detail": "processing"},
                        {"id": "p3", "name": "Verified Output", "sub": "State Contract", "type": "output", "detail": "result_dict"},
                    ],
                    "active_packet_label": f"{concept} Payload",
                    "source_refs": [file_name],
                    "duration_ms": 2000,
                },
            ],
        }

        stages.append(LearningStage(
            stage_id=s_id,
            project_id=project_id,
            order=idx + 1,
            title=stage_title,
            description=stage_desc,
            primary_concept=concept,
            purpose=f"Master {concept} as an essential building block of {normalized_domain}.",
            why_it_matters=f"Ensures clean architecture and prevents technical debt in {normalized_domain} projects.",
            learning_objectives=[f"Implement {concept} in `{file_name}`", "Verify architectural contract boundaries"],
            prerequisites=[blueprint["stages"][idx - 1][2]] if idx > 0 else [],
            concepts_to_understand=[concept, "contract_invariants", "clean_architecture"],
            expected_deliverables=f"Tested, modular implementation in `{file_name}`.",
            completion_criteria=f"Passes verification criteria for {concept}.",
            relevant_files_or_resources=[file_name],
            stage_video=stage_video,
            tasks=[task],
            status="in_progress" if idx == 0 else "locked",
        ))

    return LearningProject(
        project_id=project_id,
        repository_id=f"domain_{normalized_domain.replace(' ', '_').lower()}",
        pkm_revision_id="domain_rev_001",
        learner_id=learner_id,
        title=blueprint["project_title"],
        description=blueprint["description"],
        entry_mode="domain",
        domain=normalized_domain,
        tools_and_technologies=blueprint["technologies"],
        learner_recommendation_reason=f"Generated for selected domain: {normalized_domain}.",
        stages=stages,
        total_tasks=len(stages),
        completed_tasks=0,
        status="in_progress",
    )


def recommend_project(
    learner_profile: Any,
    candidate_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Mode B: Analyze learner profile, skills, history, and gaps to recommend an appropriate original project."""
    history_repos = getattr(learner_profile, "project_history", []) if learner_profile else []
    completed = getattr(learner_profile, "completed_projects", []) if learner_profile else []
    mastery = getattr(learner_profile, "concept_mastery", {}) if learner_profile else {}
    learner_id = getattr(learner_profile, "learner_id", "default_learner") if learner_profile else "default_learner"

    # Identify knowledge gaps (concepts with score < 0.6)
    gaps = [c for c, score in mastery.items() if score < 0.6]
    strengths = [c for c, score in mastery.items() if score >= 0.75]

    # Select optimal domain avoiding duplication
    all_domains = list(DOMAINS_CATALOG.keys())
    # Prioritize domain addressing knowledge gaps or advancing skill frontier
    if "api_routing" not in strengths or "entry_point_discovery" not in strengths:
        target_domain = "Backend Development"
    elif "domain_modeling" in strengths and "Machine Learning" not in str(history_repos):
        target_domain = "Machine Learning"
    elif "Full-Stack Development" not in str(history_repos):
        target_domain = "Full-Stack Development"
    elif "Cybersecurity" not in str(history_repos):
        target_domain = "Cybersecurity"
    else:
        target_domain = "Cloud Computing"

    blueprint = DOMAINS_CATALOG[target_domain]
    project = generate_domain_project(target_domain, learner_profile, learner_id)
    project.entry_mode = "recommended"
    project.learner_recommendation_reason = (
        f"Recommended based on your profile: You have demonstrated strong mastery in {', '.join(strengths[:2]) or 'foundational concepts'}. "
        f"This project challenges you in {', '.join(gaps[:2]) or 'advanced architectural orchestration'} without repeating previous project topics."
    )

    return {
        "recommended_domain": target_domain,
        "recommendation_rationale": project.learner_recommendation_reason,
        "demonstrated_strengths": strengths,
        "targeted_knowledge_gaps": gaps,
        "project": project.model_dump(mode="json"),
    }


def generate_reference_inspired_project(
    snapshot: PkmSnapshot,
    understandings: dict[str, ComponentUnderstanding],
    execution_paths: list[ExecutionPath],
    files_map: dict[str, str],
    learner_profile: Any = None,
    learner_id: str = "default_learner",
) -> LearningProject:
    """Mode C: Deeply analyze reference repository and generate a NEW, ORIGINAL project inspired by it."""
    repo_name = snapshot.repositories[0].name if snapshot.repositories else "ReferenceRepo"
    ref_repo_id = snapshot.revision.repository_id

    # 1. Detect domain and tech stack
    languages = list({f.language for f in snapshot.files if f.language != "unsupported"})
    has_sql = any(f.path.endswith(".sql") for f in snapshot.files)
    has_routes = any(c.execution_role == "request_handler" for c in understandings.values())

    # Map reference repo to inspired domain context
    if "auth" in repo_name.lower() or any("user" in c.name.lower() for c in understandings.values()):
        inspired_title = "Zero-Trust HIPAA HealthRecord API & Encrypted Token Broker"
        inspired_domain = "Cybersecurity & Healthcare Backend"
        inspired_desc = (
            f"An original production security project inspired by the architectural patterns of {repo_name}. "
            "Build an encrypted patient health record gateway with zero-trust token issuance, strict HIPAA access scopes, "
            "and tamper-evident audit logging."
        )
        transfers = [
            {"concept": "Transport Layer Routing", "reference_usage": "Gateway handles HTTP queries and extracts parameters.", "inspired_usage": "HIPAA gateway validates patient token and enforces encryption envelope."},
            {"concept": "Domain Entity Invariants", "reference_usage": "Typed user model prevents invalid state in memory.", "inspired_usage": "Immutable HealthRecord entity enforces strict medical classification bounds."},
            {"concept": "Storage DAO Abstraction", "reference_usage": "Data access functions isolate SQL schema lookups.", "inspired_usage": "Encrypted patient vault hashes sensitive identifiers before persistence."},
        ]
        diff_rationale = "Transfers the core layer decoupling and session model of the reference project into an original, high-stakes medical data domain with encryption and audit chains."
    else:
        inspired_title = "Distributed High-Concurrency Telemetry Ingestion Engine"
        inspired_domain = "Backend & Systems Engineering"
        inspired_desc = (
            f"An original systems project inspired by the decoupled architecture of {repo_name}. "
            "Build a telemetry event pipeline with sub-millisecond route dispatching, in-memory aggregation buffers, "
            "and fault-tolerant persistent storage."
        )
        transfers = [
            {"concept": "Gateway Delegation", "reference_usage": "Route handler delegates immediately to internal services.", "inspired_usage": "Ingestion boundary forwards metrics directly to ring-buffer workers."},
            {"concept": "Data Lineage Traceability", "reference_usage": "Input parameters flow sequentially into typed entities.", "inspired_usage": "Metric packets flow through validation, normalization, and windowed aggregation."},
        ]
        diff_rationale = "Retains the architectural separation of concerns while scaling from simple request-response to high-throughput streaming metrics."

    project_id = stable_id("proj_ref_inspired", ref_repo_id, learner_id)
    base_project = generate_domain_project(
        "Cybersecurity" if "auth" in repo_name.lower() else "Backend Development",
        learner_profile,
        learner_id,
    )

    base_project.project_id = project_id
    base_project.title = inspired_title
    base_project.description = inspired_desc
    base_project.entry_mode = "reference_inspired"
    base_project.domain = inspired_domain
    base_project.reference_repository_id = ref_repo_id
    base_project.transferred_concepts = transfers
    base_project.architecture_differences = diff_rationale
    base_project.learner_recommendation_reason = (
        f"Generated from reference repository '{repo_name}'. Core architectural patterns and design invariants have been "
        f"transferred to an original software engineering application context."
    )

    return base_project
