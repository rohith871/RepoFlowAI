from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.ids import stable_id
from backend.models import PkmSnapshot
from backend.semantic_layer import (
    ComponentUnderstanding,
    ConceptDependencyGraph,
    ConceptNode,
    ExecutionPath,
    KnowledgeGap,
)


class ConceptTeachingUnit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    concept_id: str
    title: str
    depth_level: int
    prerequisites: list[str] = Field(default_factory=list)
    learning_objective: str
    question_answered: str
    source_excerpts: list[dict[str, Any]] = Field(default_factory=list)
    running_example_step: str = ""
    developer_question: str
    misconception_addressed: str
    takeaway: str
    associated_component_ids: list[str] = Field(default_factory=list)
    associated_relationship_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TeachingPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    repository_id: str
    pkm_revision_id: str
    learning_goal: str
    learner_experience_level: str  # beginner, intermediate, advanced
    final_mental_model: str
    topological_concept_order: list[str] = Field(default_factory=list)
    teaching_units: list[ConceptTeachingUnit] = Field(default_factory=list)
    concept_dependency_graph: ConceptDependencyGraph = Field(default_factory=ConceptDependencyGraph)


class ExplanationPlanningEngine:
    """Builds a pedagogically sound teaching plan structured by concept dependencies."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        knowledge_gaps: list[KnowledgeGap],
        source_files_map: dict[str, str],
    ):
        self.snapshot = snapshot
        self.components = components
        self.execution_paths = execution_paths
        self.knowledge_gaps = knowledge_gaps
        self.source_files_map = source_files_map
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id

    def build_plan(
        self,
        goal: str = "Understand repository architecture and request execution flow",
        depth: str = "intermediate",
    ) -> TeachingPlan:
        """Construct the Concept Dependency Graph and teaching units."""
        units: list[ConceptTeachingUnit] = []
        concepts: list[ConceptNode] = []

        # 1. Base Domain Entities (Prerequisites for everything else)
        models = [c for c in self.components.values() if c.execution_role == "entity_model"]
        model_unit_ids: list[str] = []
        for model in models:
            cid = stable_id("concept", "model", model.name)
            model_unit_ids.append(cid)
            excerpt = self._get_minimal_excerpt(model.file_path, model.line_range[0], model.line_range[1])
            unit = ConceptTeachingUnit(
                concept_id=cid,
                title=f"Domain Model: {model.name}",
                depth_level=1,
                prerequisites=[],
                learning_objective=f"Understand how the entity '{model.name}' structures application state.",
                question_answered=f"What data attributes define a {model.name}?",
                source_excerpts=[excerpt],
                developer_question=f"Where is {model.name} defined and what fields does it require?",
                misconception_addressed=f"A {model.name} is an in-memory dataclass model rather than an active ORM record directly writing to disk.",
                takeaway=f"The {model.name} entity provides a typed structure for user attributes (name).",
                associated_component_ids=[model.component_id],
                evidence_ids=model.evidence_ids,
            )
            units.append(unit)
            concepts.append(ConceptNode(
                concept_id=cid,
                title=unit.title,
                summary=unit.takeaway,
                depth_level=1,
                prerequisite_concept_ids=[],
                associated_component_ids=[model.component_id],
                evidence_ids=model.evidence_ids,
                learning_takeaway=unit.takeaway,
            ))

        # 2. Data Access / Service Layer (Prerequisite: Models)
        services = [c for c in self.components.values() if c.execution_role in {"data_access", "domain_service"}]
        service_unit_ids: list[str] = []
        for srv in services:
            cid = stable_id("concept", "service", srv.name)
            service_unit_ids.append(cid)
            prereqs = list(model_unit_ids)
            excerpt = self._get_minimal_excerpt(srv.file_path, srv.line_range[0], srv.line_range[1])
            unit = ConceptTeachingUnit(
                concept_id=cid,
                title=f"Service Delegation: {srv.name}",
                depth_level=2,
                prerequisites=prereqs,
                learning_objective=f"Understand how '{srv.name}' encapsulates entity retrieval logic.",
                question_answered=f"How does {srv.name} construct and return domain data?",
                source_excerpts=[excerpt],
                developer_question=f"Why does {srv.name} delegate instead of handling API concerns?",
                misconception_addressed=f"{srv.name} handles domain construction; it is not coupled to HTTP request objects or JSON formatting.",
                takeaway=f"{srv.name} cleanly separates entity construction from API transport protocols.",
                associated_component_ids=[srv.component_id],
                evidence_ids=srv.evidence_ids,
            )
            units.append(unit)
            concepts.append(ConceptNode(
                concept_id=cid,
                title=unit.title,
                summary=unit.takeaway,
                depth_level=2,
                prerequisite_concept_ids=prereqs,
                associated_component_ids=[srv.component_id],
                evidence_ids=srv.evidence_ids,
                learning_takeaway=unit.takeaway,
            ))

        # 3. API Route Handler Layer (Prerequisite: Services)
        handlers = [c for c in self.components.values() if c.execution_role in {"request_handler", "entry_point"} or "route" in c.name.lower()]
        handler_unit_ids: list[str] = []
        for handler in handlers:
            cid = stable_id("concept", "handler", handler.name)
            handler_unit_ids.append(cid)
            prereqs = list(service_unit_ids)
            excerpt = self._get_minimal_excerpt(handler.file_path, handler.line_range[0], handler.line_range[1])
            unit = ConceptTeachingUnit(
                concept_id=cid,
                title=f"API Interface: {handler.name}",
                depth_level=3,
                prerequisites=prereqs,
                learning_objective=f"Understand how '{handler.name}' accepts inputs, calls services, and formats the response.",
                question_answered=f"What triggers {handler.name} and what response does it produce?",
                source_excerpts=[excerpt],
                developer_question=f"What parameters does {handler.name} accept and what format is returned?",
                misconception_addressed=f"{handler.name} does not perform data loading itself; it delegates to service functions and packages the result into a response dict.",
                takeaway=f"{handler.name} acts as the boundary between client requests and internal services.",
                associated_component_ids=[handler.component_id],
                evidence_ids=handler.evidence_ids,
            )
            units.append(unit)
            concepts.append(ConceptNode(
                concept_id=cid,
                title=unit.title,
                summary=unit.takeaway,
                depth_level=3,
                prerequisite_concept_ids=prereqs,
                associated_component_ids=[handler.component_id],
                evidence_ids=handler.evidence_ids,
                learning_takeaway=unit.takeaway,
            ))

        # 4. End-to-End Execution Flow (Prerequisite: Models, Services, Handlers)
        flow_cid = stable_id("concept", "e2e_flow")
        flow_prereqs = model_unit_ids + service_unit_ids + handler_unit_ids
        flow_steps_desc = ""
        flow_ev_ids = []
        if self.execution_paths:
            p = self.execution_paths[0]
            flow_steps_desc = " -> ".join(s.description.split(".")[0] for s in p.steps[:4])
            flow_ev_ids = p.evidence_ids

        flow_unit = ConceptTeachingUnit(
            concept_id=flow_cid,
            title="End-to-End Request Journey",
            depth_level=4,
            prerequisites=flow_prereqs,
            learning_objective="Trace an operation from entry through service delegation down to model return.",
            question_answered="How do components cooperate during a complete request lifecycle?",
            source_excerpts=[],
            running_example_step=flow_steps_desc,
            developer_question="What is the exact sequence of invocations from request entry to exit?",
            misconception_addressed="The request flow is an orchestrated multi-file journey, not an isolated single-function execution.",
            takeaway="Data enters the route handler, flows into domain services for entity construction, and returns formatted as an API payload.",
            associated_component_ids=list(self.components.keys()),
            evidence_ids=flow_ev_ids,
        )
        units.append(flow_unit)
        concepts.append(ConceptNode(
            concept_id=flow_cid,
            title=flow_unit.title,
            summary=flow_unit.takeaway,
            depth_level=4,
            prerequisite_concept_ids=flow_prereqs,
            evidence_ids=flow_ev_ids,
            learning_takeaway=flow_unit.takeaway,
        ))

        # 5. Architecture Recap & Boundaries (Prerequisite: Flow)
        recap_cid = stable_id("concept", "recap_boundaries")
        recap_unit = ConceptTeachingUnit(
            concept_id=recap_cid,
            title="Architectural Boundaries & Limitations",
            depth_level=5,
            prerequisites=[flow_cid],
            learning_objective="Identify verified system boundaries, modification guidelines, and runtime uncertainties.",
            question_answered="What should a developer verify before modifying this codebase?",
            source_excerpts=[],
            developer_question="Where are the critical extension points and what runtime caveats exist?",
            misconception_addressed="Static verification establishes declarations and call relationships, but runtime network, database, and telemetry require live verification.",
            takeaway="The architecture enforces clean separation of concerns: routes format transport, services manage workflow, models structure data.",
            associated_component_ids=list(self.components.keys()),
            evidence_ids=[],
        )
        units.append(recap_unit)
        concepts.append(ConceptNode(
            concept_id=recap_cid,
            title=recap_unit.title,
            summary=recap_unit.takeaway,
            depth_level=5,
            prerequisite_concept_ids=[flow_cid],
            evidence_ids=[],
            learning_takeaway=recap_unit.takeaway,
        ))

        # Build Topological Sort of concept IDs
        topological_order = [u.concept_id for u in units]

        plan_id = stable_id("plan", self.repo_id, goal)
        final_mental_model = (
            "A layered Python application where route handlers receive client input, "
            "delegate to domain services for business logic and entity construction, "
            "and shape structured output without mixing concerns."
        )

        return TeachingPlan(
            plan_id=plan_id,
            repository_id=self.repo_id,
            pkm_revision_id=self.rev_id,
            learning_goal=goal,
            learner_experience_level=depth,
            final_mental_model=final_mental_model,
            topological_concept_order=topological_order,
            teaching_units=units,
            concept_dependency_graph=ConceptDependencyGraph(
                concepts=concepts,
                topological_order=topological_order,
            ),
        )

    def _get_minimal_excerpt(self, path: str, start: int, end: int) -> dict[str, Any]:
        """Extract a minimal, readable source excerpt bounded to max 12 lines."""
        content = self.source_files_map.get(path, "")
        lines = content.splitlines()
        bounded_end = min(end, start + 11)
        sub_lines = lines[max(0, start - 1):bounded_end]
        return {
            "path": path,
            "line_start": start,
            "line_end": bounded_end,
            "code": "\n".join(sub_lines),
        }
