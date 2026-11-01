from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ProvenanceKind(str, Enum):
    SOURCE_DECLARED = "source_declared"
    DETERMINISTIC_DERIVED = "deterministic_derived"
    MODEL_INTERPRETED = "model_interpreted"
    UNRESOLVED = "unresolved"


class ComponentUnderstanding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    component_id: str
    name: str
    kind: str  # function, class, module, route_handler, service, model
    file_path: str
    line_range: tuple[int, int]
    summary: str
    responsibility: str
    problem_solved: str
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    state_reads: list[str] = Field(default_factory=list)
    state_writes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    error_paths: list[dict[str, Any]] = Field(default_factory=list)
    external_interactions: list[str] = Field(default_factory=list)
    execution_role: str = "component"
    modification_guidance: str = ""
    limitations: list[str] = Field(default_factory=list)
    provenance: ProvenanceKind = ProvenanceKind.DETERMINISTIC_DERIVED
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="ignore")
    step_number: int
    source_component_id: str
    target_component_id: str | None = None
    operation_type: str  # call, data_transform, state_read, state_write, validation, return, error_raise, persistence
    description: str
    condition: str | None = None
    data_in: str | None = None
    data_out: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    is_async: bool = False
    provenance: ProvenanceKind = ProvenanceKind.DETERMINISTIC_DERIVED


class ExecutionPath(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path_id: str
    name: str
    entry_point_id: str
    trigger: str
    steps: list[ExecutionStep] = Field(default_factory=list)
    data_lineage: list[dict[str, Any]] = Field(default_factory=list)
    state_transitions: list[dict[str, Any]] = Field(default_factory=list)
    terminal_result: str = ""
    error_branches: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: ProvenanceKind = ProvenanceKind.DETERMINISTIC_DERIVED
    uncertainties: list[str] = Field(default_factory=list)


class KnowledgeGap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gap_id: str
    category: str  # unresolved_symbol, missing_call, incomplete_path, ambiguous_responsibility, doc_conflict, runtime_uncertainty
    subject_id: str | None = None
    subject_name: str
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    resolution_attempt: str | None = None
    resolution_status: str = "unresolved"  # unresolved, resolved_deterministic, resolved_model_aid, disclosed_limitation
    limitation_note: str = ""


class ConceptNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    concept_id: str
    title: str
    summary: str
    depth_level: int = 1  # 1=local, 2=interaction, 3=flow, 4=system, 5=design
    prerequisite_concept_ids: list[str] = Field(default_factory=list)
    associated_component_ids: list[str] = Field(default_factory=list)
    associated_path_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    learning_takeaway: str = ""
    misconceptions: list[str] = Field(default_factory=list)


class ConceptDependencyGraph(BaseModel):
    model_config = ConfigDict(extra="ignore")
    concepts: list[ConceptNode] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)


class ArchitectureView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    view_id: str
    question: str
    view_type: str  # module_organization, request_flow, api_to_domain, data_lifecycle
    components: list[dict[str, Any]] = Field(default_factory=list)
    boundaries: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    layout_data: dict[str, Any] = Field(default_factory=dict)


class SemanticRepositoryModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository_id: str
    pkm_revision_id: str
    components: dict[str, ComponentUnderstanding] = Field(default_factory=dict)
    execution_paths: list[ExecutionPath] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)
    concept_graph: ConceptDependencyGraph = Field(default_factory=ConceptDependencyGraph)
    architecture_views: list[ArchitectureView] = Field(default_factory=list)
    created_at: str = ""
    version: str = "semantic-1.0"
