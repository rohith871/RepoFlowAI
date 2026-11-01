from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.semantic_layer import ComponentUnderstanding, ExecutionPath, KnowledgeGap


class CausalExplanation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_id: str
    target_name: str
    target_type: str  # component, path, relationship
    problem_addressed: str
    trigger: str
    why_involved: str
    input_transformation: str
    downstream_behavior_enabled: str
    responsibility_boundary: str
    modification_guidance: str
    counterfactual_analysis: str  # strictly labeled [HYPOTHETICAL]
    evidence_ids: list[str] = Field(default_factory=list)


class CauseAndEffectEngine:
    """Generates grounded cause-and-effect explanations connecting implementation to behavior."""

    def __init__(
        self,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        knowledge_gaps: list[KnowledgeGap],
    ):
        self.components = components
        self.execution_paths = execution_paths
        self.knowledge_gaps = knowledge_gaps

    def explain_component(self, comp: ComponentUnderstanding) -> CausalExplanation:
        """Derive causal reasoning for an individual component."""
        inputs_str = ", ".join(f"{inp['name']} ({inp['type']})" for inp in comp.inputs) or "no input parameters"
        outputs_str = comp.outputs[0]["type"] if comp.outputs else "None"

        # Determine why involved & responsibility boundary
        if comp.execution_role == "request_handler":
            trigger = f"An API request or function call supplying {inputs_str}."
            why_involved = f"{comp.name} serves as the entry boundary, validating incoming arguments and converting internal results into an API-compatible output structure."
            resp_boundary = f"{comp.name} owns transport-level request handling and response formatting. It delegates data retrieval to downstream domain services rather than querying state directly."
            downstream = f"Enables client consumers to retrieve formatted response data ({outputs_str}) without needing direct access to domain storage."
        elif comp.execution_role == "entity_model":
            trigger = "Instantiation by domain loading services when representing an active entity."
            why_involved = f"{comp.name} provides a typed in-memory contract so all consumers can rely on defined attributes."
            resp_boundary = f"{comp.name} owns state definition and attribute structure; it does not handle network transport or query orchestration."
            downstream = f"Allows services and route handlers to pass typed {comp.name} objects safely throughout the execution chain."
        elif comp.execution_role == "data_access":
            trigger = f"Invocation by a caller requiring retrieval or creation of domain entities."
            why_involved = f"{comp.name} encapsulates the instantiation mechanics for domain models, abstracting the constructor details from callers."
            resp_boundary = f"{comp.name} owns entity construction and delegation; it is decoupled from presentation formatting."
            downstream = f"Provides callers with a verified domain entity instance ready for consumption."
        else:
            trigger = f"Invocation with {inputs_str}."
            why_involved = f"{comp.name} performs computation for {comp.responsibility}."
            resp_boundary = f"Encapsulates internal logic within {comp.file_path}."
            downstream = f"Produces {outputs_str} consumed by dependent components."

        # Input transformation
        if comp.transformations:
            transform_str = "; ".join(comp.transformations[:3])
        else:
            transform_str = f"Processes {inputs_str} and returns {outputs_str}."

        # Modification inspection guidance
        if comp.dependencies:
            dep_names = [self.components[dep].name for dep in comp.dependencies if dep in self.components]
            mod_guide = f"Before modifying {comp.name}, inspect dependencies: {', '.join(dep_names)}. Downstream callers expect output of type {outputs_str}."
        else:
            mod_guide = f"Inspect callers before altering {comp.name}; ensure compatibility with return type {outputs_str}."

        # Counterfactual reasoning (Strictly labeled [HYPOTHETICAL])
        if comp.execution_role == "request_handler" and comp.dependencies:
            counterfactual = (
                f"[HYPOTHETICAL] If downstream dependency '{comp.dependencies[0]}' failed or returned an unexpected type, "
                f"{comp.name} would fail to construct its return value or raise an unhandled exception."
            )
        elif comp.execution_role == "entity_model":
            counterfactual = (
                f"[HYPOTHETICAL] If a field in {comp.name} were renamed or made mandatory without default values, "
                f"all instantiation sites across callers would fail at runtime with a TypeError."
            )
        elif comp.execution_role == "data_access":
            counterfactual = (
                f"[HYPOTHETICAL] If {comp.name} returned None instead of a valid entity instance, "
                f"upstream callers accessing entity attributes would encounter an AttributeError."
            )
        else:
            counterfactual = (
                f"[HYPOTHETICAL] Modifying the return contract of {comp.name} would require updating "
                f"all dependent functions that consume its output."
            )

        return CausalExplanation(
            target_id=comp.component_id,
            target_name=comp.name,
            target_type="component",
            problem_addressed=comp.problem_solved,
            trigger=trigger,
            why_involved=why_involved,
            input_transformation=transform_str,
            downstream_behavior_enabled=downstream,
            responsibility_boundary=resp_boundary,
            modification_guidance=mod_guide,
            counterfactual_analysis=counterfactual,
            evidence_ids=comp.evidence_ids,
        )

    def generate_teacher_narration(self, comp: ComponentUnderstanding) -> str:
        """Generate conversational, high-quality instructor narration for a component."""
        inputs_desc = ", ".join(inp["name"] for inp in comp.inputs) if comp.inputs else "incoming parameters"
        output_desc = comp.outputs[0]["type"] if comp.outputs else "structured results"

        if comp.execution_role == "request_handler":
            return (
                f"Let's examine how {comp.name} functions as the external gateway for this workflow. "
                f"Rather than coupling network transport with internal database operations, its primary job is to accept {inputs_desc}, "
                f"validate the incoming payload, and immediately hand off control to domain services. "
                f"By keeping this gateway lean, changes to HTTP endpoints or web protocols won't destabilize your core business logic."
            )
        elif comp.execution_role == "entity_model":
            return (
                f"To keep state predictable and prevent loose dictionaries from circulating across modules, "
                f"the application defines the {comp.name} data model. "
                f"Notice on screen how it establishes a strongly-typed in-memory contract: downstream functions can confidently rely "
                f"on its attributes without writing defensive runtime assertions everywhere. "
                f"Whenever you extend this model, maintain this structure so dependent services remain intact."
            )
        elif comp.execution_role in {"data_access", "service_loader"}:
            if comp.dependencies:
                resolved_deps = [self.components[d].name for d in comp.dependencies if d in self.components]
                if not resolved_deps:
                    resolved_deps = [d.split(":")[-1] for d in comp.dependencies if not d.startswith("sym_")]
                deps_str = ", ".join(resolved_deps[:2]) if resolved_deps else "underlying services"
                return (
                    f"Next, {comp.name} coordinates domain processing by orchestrating calls to {deps_str}. "
                    f"Rather than performing raw data manipulation itself, it acts as an intermediate business coordinator, "
                    f"delegating specific retrieval tasks while guaranteeing that downstream components receive verified arguments."
                )
            return (
                f"Moving into core entity assembly, {comp.name} encapsulates direct domain instantiation. "
                f"By isolating raw data retrieval and model construction inside this function, upstream callers are shielded "
                f"from internal storage details, simplifying testing and future migrations."
            )
        else:
            return (
                f"Let's explore the role of {comp.name} in this system. "
                f"{comp.responsibility} "
                f"It processes {inputs_desc} and yields {output_desc}, allowing other modules to build on top of verified transformations. "
                f"Take note of its boundaries before modifying its logic, so upstream callers continue to receive expected outputs."
            )

    def generate_flow_narration(self, path: ExecutionPath) -> str:
        """Generate instructor narration for an end-to-end execution path."""
        entry_comp = self.components.get(path.entry_point_id)
        entry_name = entry_comp.name if entry_comp else path.name

        step_details = []
        for s in path.steps[:4]:
            step_details.append(f"then {s.description.lower()}")
        flow_chain = ", ".join(step_details) if step_details else "passing control across module boundaries"

        return (
            f"Now, let's trace the complete lifecycle of a request as it travels through the application. "
            f"Execution begins at {entry_name}. Notice how data transitions across each architectural boundary: "
            f"{flow_chain}. "
            f"Finally, the terminal result, namely {path.terminal_result}, is returned safely to the caller, ensuring a predictable execution lifecycle."
        )

    def explain_flow(self, path: ExecutionPath) -> CausalExplanation:
        """Derive causal reasoning for a complete execution path."""
        entry_comp = self.components.get(path.entry_point_id)
        entry_name = entry_comp.name if entry_comp else "entry_point"

        problem = f"Executes end-to-end request handling starting from {entry_name}."
        trigger = path.trigger
        why_involved = f"Orchestrates a sequence of {len(path.steps)} verified steps connecting API handling to domain logic."
        transform = f"Transforms initial input into terminal result: {path.terminal_result}."
        downstream = "Delivers completed operation result back to the initiating caller."
        resp_boundary = "Coordinated execution across multiple files, preserving layer boundaries."
        mod_guide = "To alter this workflow, locate the specific step component responsible for that phase rather than editing all files."
        counterfactual = (
            f"[HYPOTHETICAL] If any intermediate step in this chain fails to return its expected object, "
            f"the chain terminates prematurely before reaching the terminal step."
        )

        return CausalExplanation(
            target_id=path.path_id,
            target_name=path.name,
            target_type="path",
            problem_addressed=problem,
            trigger=trigger,
            why_involved=why_involved,
            input_transformation=transform,
            downstream_behavior_enabled=downstream,
            responsibility_boundary=resp_boundary,
            modification_guidance=mod_guide,
            counterfactual_analysis=counterfactual,
            evidence_ids=path.evidence_ids,
        )
