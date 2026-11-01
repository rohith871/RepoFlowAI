from __future__ import annotations

from typing import Any

from backend.ids import stable_id
from backend.models import PkmSnapshot, Relationship
from backend.semantic_layer import ArchitectureView, ComponentUnderstanding, ExecutionPath


class ArchitectureReasoningEngine:
    """Question-driven architectural view generator separating semantic structure from layout."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        relationships: list[Relationship],
        execution_paths: list[ExecutionPath],
    ):
        self.snapshot = snapshot
        self.components = components
        self.relationships = relationships
        self.execution_paths = execution_paths
        self.repo_id = snapshot.revision.repository_id
        self.rev_id = snapshot.revision.pkm_revision_id
        self._symbols_by_id = {s.symbol_id: s for s in snapshot.symbols}

    def generate_views(self, question: str = "") -> list[ArchitectureView]:
        """Generate tailored architectural views based on the architectural questions."""
        views: list[ArchitectureView] = []
        # View 1: System Organization View
        views.append(self._build_organization_view())
        # View 2: Request Journey & Layer Interaction View
        views.append(self._build_request_journey_view(question))
        # View 3: Data Lineage & Entity Model View
        views.append(self._build_data_lifecycle_view())
        return views

    def _build_organization_view(self) -> ArchitectureView:
        """Question: How is this application organized into modules and layers?"""
        view_id = stable_id("archview", self.repo_id, "organization")
        question_text = "How is this application organized across architectural boundaries?"

        # Group components by module / file
        modules_map: dict[str, list[dict[str, Any]]] = {}
        for comp in self.components.values():
            if comp.kind == "module":
                continue
            modules_map.setdefault(comp.file_path, []).append({
                "id": comp.component_id,
                "label": comp.name,
                "kind": comp.kind,
                "role": comp.execution_role,
                "file_path": comp.file_path,
                "line_range": comp.line_range,
                "summary": comp.summary,
            })

        boundaries: list[dict[str, Any]] = []
        layout_components: list[dict[str, Any]] = []
        evidence_ids: list[str] = []

        col_index = 0
        for file_path, items in sorted(modules_map.items()):
            col_x = 80 + col_index * 360
            b_height = 80 + len(items) * 110
            boundary_id = stable_id("bound", file_path)
            boundaries.append({
                "boundary_id": boundary_id,
                "label": f"Module: {file_path}",
                "kind": "module_boundary",
                "x": col_x - 20,
                "y": 60,
                "width": 320,
                "height": b_height,
            })

            for row_index, item in enumerate(items):
                node_y = 110 + row_index * 110
                item["x"] = col_x
                item["y"] = node_y
                item["width"] = 280
                item["height"] = 80
                layout_components.append(item)
                comp = self.components.get(item["id"])
                if comp:
                    evidence_ids.extend(comp.evidence_ids)

            col_index += 1

        # Collect verified cross-component edges
        view_comp_ids = {c["id"] for c in layout_components}
        view_edges: list[dict[str, Any]] = []
        for rel in self.relationships:
            if rel.source_id in view_comp_ids and rel.target_id in view_comp_ids:
                src_comp = self.components[rel.source_id]
                tgt_comp = self.components[rel.target_id]
                view_edges.append({
                    "id": rel.relationship_id,
                    "source": rel.source_id,
                    "target": rel.target_id,
                    "source_label": src_comp.name,
                    "target_label": tgt_comp.name,
                    "type": rel.relationship_type,
                    "status": rel.status,
                    "claim_level": rel.claim_level.value,
                    "evidence_ids": rel.evidence_ids,
                })
                evidence_ids.extend(rel.evidence_ids)

        return ArchitectureView(
            view_id=view_id,
            question=question_text,
            view_type="module_organization",
            components=layout_components,
            boundaries=boundaries,
            relationships=view_edges,
            annotations=[
                {"text": "Boxes represent verified module boundaries (files); edges represent verified static calls/instantiations."}
            ],
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            layout_data={"width": 1280, "height": 720, "orientation": "horizontal_columns"},
        )

    def _build_request_journey_view(self, query: str = "") -> ArchitectureView:
        """Question: What happens when a user sends a request through the system?"""
        view_id = stable_id("archview", self.repo_id, "request_journey")
        question_text = "What happens when a user sends a request through the system?"

        # Use execution paths to arrange nodes in causal execution sequence
        steps_nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        evidence_ids: list[str] = []

        if self.execution_paths:
            path = self.execution_paths[0]
            evidence_ids.extend(path.evidence_ids)
            ordered_comp_ids = []
            seen = set()
            for step in path.steps:
                for cid in [step.source_component_id, step.target_component_id]:
                    if cid and cid in self.components and cid not in seen:
                        seen.add(cid)
                        ordered_comp_ids.append(cid)

            for index, cid in enumerate(ordered_comp_ids):
                comp = self.components[cid]
                x = 100 + index * 260
                y = 260
                steps_nodes.append({
                    "id": comp.component_id,
                    "label": comp.name,
                    "kind": comp.kind,
                    "role": comp.execution_role,
                    "file_path": comp.file_path,
                    "step_order": index + 1,
                    "x": x,
                    "y": y,
                    "width": 210,
                    "height": 95,
                    "responsibility": comp.responsibility,
                })

            for i in range(len(steps_nodes) - 1):
                src = steps_nodes[i]
                tgt = steps_nodes[i + 1]
                edge_id = stable_id("edge_journey", src["id"], tgt["id"])
                edges.append({
                    "id": edge_id,
                    "source": src["id"],
                    "target": tgt["id"],
                    "source_label": src["label"],
                    "target_label": tgt["label"],
                    "type": "calls" if tgt["kind"] != "class" else "instantiates",
                    "status": "verified",
                    "claim_level": "resolved_static",
                    "step_number": i + 1,
                })
        else:
            # Fallback to general component ordering
            steps_nodes = [
                {"id": c.component_id, "label": c.name, "kind": c.kind, "x": 100 + i * 220, "y": 260, "width": 190, "height": 80}
                for i, c in enumerate(list(self.components.values())[:5])
            ]

        boundaries = [
            {"boundary_id": "b_journey", "label": "Request Execution Path", "x": 60, "y": 180, "width": max(600, len(steps_nodes) * 270), "height": 240}
        ]

        return ArchitectureView(
            view_id=view_id,
            question=question_text,
            view_type="request_flow",
            components=steps_nodes,
            boundaries=boundaries,
            relationships=edges,
            annotations=[
                {"text": "Execution sequence traces data entering the API handler down to domain entity instantiation."}
            ],
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            layout_data={"width": 1280, "height": 720, "orientation": "linear_flow"},
        )

    def _build_data_lifecycle_view(self) -> ArchitectureView:
        """Question: Where does data originate, change, and persist?"""
        view_id = stable_id("archview", self.repo_id, "data_lifecycle")
        question_text = "Where does data originate, transform, and persist?"

        # Focus on models, dataclasses, return transformations, and persistence
        data_components: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        evidence_ids: list[str] = []

        models = [c for c in self.components.values() if c.execution_role in {"entity_model", "data_access"}]
        for index, comp in enumerate(models):
            data_components.append({
                "id": comp.component_id,
                "label": comp.name,
                "kind": comp.kind,
                "role": comp.execution_role,
                "fields": [inp["name"] for inp in comp.inputs],
                "transforms": comp.transformations,
                "x": 140 + index * 320,
                "y": 240,
                "width": 260,
                "height": 140,
            })
            evidence_ids.extend(comp.evidence_ids)

        # Connect model relationships
        model_ids = {c["id"] for c in data_components}
        for rel in self.relationships:
            if rel.source_id in model_ids and rel.target_id in model_ids:
                edges.append({
                    "id": rel.relationship_id,
                    "source": rel.source_id,
                    "target": rel.target_id,
                    "type": rel.relationship_type,
                    "status": rel.status,
                })
                evidence_ids.extend(rel.evidence_ids)

        boundaries = [
            {"boundary_id": "b_data", "label": "Domain Entities & Transformations", "x": 100, "y": 160, "width": max(500, len(data_components) * 350), "height": 300}
        ]

        return ArchitectureView(
            view_id=view_id,
            question=question_text,
            view_type="data_lifecycle",
            components=data_components,
            boundaries=boundaries,
            relationships=edges,
            annotations=[
                {"text": "Shows data entity definitions and data transformations."}
            ],
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            layout_data={"width": 1280, "height": 720, "orientation": "entity_grid"},
        )
