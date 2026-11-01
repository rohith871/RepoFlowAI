from __future__ import annotations

from typing import Any

from backend.ids import stable_id
from backend.models import PkmSnapshot, Relationship, Symbol
from backend.semantic_layer import (
    ComponentUnderstanding,
    ExecutionPath,
    ExecutionStep,
    ProvenanceKind,
)


class ExecutionFlowTracer:
    """Reconstructs execution paths, data lineage, and state transitions across components."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        relationships: list[Relationship],
    ):
        self.snapshot = snapshot
        self.components = components
        self.relationships = relationships
        self._symbols_by_id = {s.symbol_id: s for s in snapshot.symbols}
        # Adjacency list: caller -> list of (callee_id, relationship_type)
        self._calls: dict[str, list[str]] = {}
        for r in relationships:
            if r.relationship_type in {"calls", "instantiates"}:
                self._calls.setdefault(r.source_id, []).append(r.target_id)

    def find_entry_points(self) -> list[ComponentUnderstanding]:
        """Find execution entry points (route handlers, top-level callers)."""
        all_targets = {r.target_id for r in self.relationships if r.relationship_type in {"calls", "instantiates"}}
        entry_points: list[ComponentUnderstanding] = []

        # 1. Prefer components designated as request_handler or entry_point
        for comp in self.components.values():
            if comp.execution_role in {"request_handler", "entry_point"} or "route" in comp.name.lower():
                entry_points.append(comp)

        # 2. Add components with outgoing calls that are not called by any other component
        if not entry_points:
            for comp_id, comp in self.components.items():
                if comp_id in self._calls and comp_id not in all_targets and comp.kind == "function":
                    entry_points.append(comp)

        # 3. Fallback: any function
        if not entry_points:
            entry_points = [c for c in self.components.values() if c.kind == "function"][:3]

        return entry_points

    def trace_paths(self) -> list[ExecutionPath]:
        """Trace full execution flows starting from all discovered entry points."""
        paths: list[ExecutionPath] = []
        entry_points = self.find_entry_points()

        for ep in entry_points:
            path = self._trace_from_entry_point(ep)
            if path and path.steps:
                paths.append(path)

        return paths

    def _trace_from_entry_point(self, ep: ComponentUnderstanding) -> ExecutionPath:
        """Trace sequential execution steps and data lineage for an entry point."""
        path_id = stable_id("execpath", ep.component_id)
        steps: list[ExecutionStep] = []
        visited: set[str] = set()
        evidence_ids: list[str] = list(ep.evidence_ids)

        # Step 1: Entry activation
        input_args = ", ".join(f"{inp['name']}: {inp['type']}" for inp in ep.inputs) or "no arguments"
        steps.append(ExecutionStep(
            step_number=1,
            source_component_id=ep.component_id,
            target_component_id=None,
            operation_type="entry_call",
            description=f"Request reaches {ep.name} in {ep.file_path} with {input_args}.",
            data_in=input_args,
            data_out=None,
            evidence_ids=ep.evidence_ids,
            provenance=ProvenanceKind.DETERMINISTIC_DERIVED,
        ))
        visited.add(ep.component_id)

        # Walk call hierarchy
        step_counter = 2
        queue: list[tuple[str, int]] = [(ep.component_id, 0)]  # (comp_id, depth)

        while queue and step_counter <= 15:
            current_id, depth = queue.pop(0)
            callees = self._calls.get(current_id, [])

            for target_id in callees:
                if target_id in visited:
                    continue  # prevent duplicate steps or cycles
                target_comp = self.components.get(target_id)
                target_sym = self._symbols_by_id.get(target_id)
                target_name = target_comp.name if target_comp else (target_sym.name if target_sym else target_id)
                current_comp = self.components.get(current_id)
                current_name = current_comp.name if current_comp else current_id

                op_type = "instantiates" if (target_comp and target_comp.kind == "class") else "call"
                desc = (
                    f"{current_name} instantiates class {target_name}."
                    if op_type == "instantiates"
                    else f"{current_name} invokes {target_name} in {target_comp.file_path if target_comp else ''}."
                )

                step_evidence = []
                if target_comp:
                    step_evidence.extend(target_comp.evidence_ids)
                    evidence_ids.extend(target_comp.evidence_ids)

                steps.append(ExecutionStep(
                    step_number=step_counter,
                    source_component_id=current_id,
                    target_component_id=target_id,
                    operation_type=op_type,
                    description=desc,
                    data_in=", ".join(inp["name"] for inp in target_comp.inputs) if target_comp else None,
                    data_out=target_comp.outputs[0]["type"] if (target_comp and target_comp.outputs) else None,
                    evidence_ids=step_evidence,
                    provenance=ProvenanceKind.DETERMINISTIC_DERIVED,
                ))
                step_counter += 1

                if target_id not in visited:
                    visited.add(target_id)
                    queue.append((target_id, depth + 1))

        # Terminal return step
        terminal_result = ep.outputs[0]["type"] if ep.outputs else "response"
        if ep.transformations:
            transform_desc = f"{ep.name} returns: {ep.transformations[-1]}"
        else:
            transform_desc = f"{ep.name} completes and returns {terminal_result}."

        steps.append(ExecutionStep(
            step_number=step_counter,
            source_component_id=ep.component_id,
            target_component_id=None,
            operation_type="return",
            description=transform_desc,
            data_in=None,
            data_out=terminal_result,
            evidence_ids=ep.evidence_ids,
            provenance=ProvenanceKind.DETERMINISTIC_DERIVED,
        ))

        # Reconstruct Data Lineage
        data_lineage: list[dict[str, Any]] = []
        for inp in ep.inputs:
            data_name = inp["name"]
            data_lineage.append({
                "variable": data_name,
                "origin": f"{ep.name} parameter",
                "flow": [
                    {"component": self.components[s.source_component_id].name if s.source_component_id in self.components else s.source_component_id,
                     "operation": s.operation_type}
                    for s in steps
                ],
                "transformed_to": ep.transformations[-1] if ep.transformations else "result",
                "transmitted_in_response": True,
            })

        # Reconstruct State Transitions
        state_transitions: list[dict[str, Any]] = [
            {
                "phase": "entry",
                "state_description": f"Request parameters received by {ep.name}.",
                "causing_component": ep.name,
            },
            {
                "phase": "execution",
                "state_description": f"Domain components executed: {[self.components[cid].name for cid in visited if cid in self.components]}.",
                "causing_component": "orchestrated_call_chain",
            },
            {
                "phase": "exit",
                "state_description": f"Result shaped and returned ({terminal_result}).",
                "causing_component": ep.name,
            },
        ]

        uncertainties = [
            "Actual runtime latency and network transmission are dynamic.",
            "Conditional branches not exercised in this primary static path require testing.",
        ]

        return ExecutionPath(
            path_id=path_id,
            name=f"Flow: {ep.name}",
            entry_point_id=ep.component_id,
            trigger=f"Invocation of {ep.name}",
            steps=steps,
            data_lineage=data_lineage,
            state_transitions=state_transitions,
            terminal_result=terminal_result,
            error_branches=ep.error_paths,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            provenance=ProvenanceKind.DETERMINISTIC_DERIVED,
            uncertainties=uncertainties,
        )
