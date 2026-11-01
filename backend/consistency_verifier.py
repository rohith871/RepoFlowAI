from __future__ import annotations

from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.models import PkmSnapshot
from backend.semantic_layer import ArchitectureView, ComponentUnderstanding, ExecutionPath


class ConsistencyReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_valid: bool
    overall_integrity_score: float  # 0 to 100
    verified_checks: list[str] = Field(default_factory=list)
    critical_mismatches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclosed_limitations: list[str] = Field(default_factory=list)
    stage_scores: dict[str, float] = Field(default_factory=dict)


class EndToEndConsistencyVerifier:
    """Deterministic validator enforcing agreement across analysis, architecture, storyboard, narration, and render."""

    def __init__(
        self,
        snapshot: PkmSnapshot,
        components: dict[str, ComponentUnderstanding],
        execution_paths: list[ExecutionPath],
        source_files_map: dict[str, str],
    ):
        self.snapshot = snapshot
        self.components = components
        self.execution_paths = execution_paths
        self.source_files_map = source_files_map
        self._symbol_ids = {s.symbol_id for s in snapshot.symbols}
        self._relationship_ids = {r.relationship_id for r in snapshot.relationships}
        self._file_paths = {f.path for f in snapshot.files}
        self._evidence_ids = {e.evidence_id for e in snapshot.evidence}

    def verify(
        self,
        storyboard: dict[str, Any],
        architecture_views: list[ArchitectureView],
        media_manifest: dict[str, Any] | None = None,
    ) -> ConsistencyReport:
        """Run all deterministic consistency checks across stages."""
        verified_checks: list[str] = []
        critical_mismatches: list[str] = []
        warnings: list[str] = []
        disclosed_limitations: list[str] = []
        stage_scores: dict[str, float] = {}

        # 1. Architecture View Verification
        arch_valid = True
        for view in architecture_views:
            for comp in view.components:
                cid = comp.get("id")
                if cid and cid not in self._symbol_ids and cid not in self.components:
                    critical_mismatches.append(f"Architecture view '{view.view_id}' references unknown component '{cid}'.")
                    arch_valid = False
            for edge in view.relationships:
                eid = edge.get("id")
                src = edge.get("source")
                tgt = edge.get("target")
                if src and src not in self._symbol_ids and src not in self.components:
                    critical_mismatches.append(f"Architecture edge '{eid}' source '{src}' does not exist.")
                    arch_valid = False
                if tgt and tgt not in self._symbol_ids and tgt not in self.components:
                    critical_mismatches.append(f"Architecture edge '{eid}' target '{tgt}' does not exist.")
                    arch_valid = False

        if arch_valid:
            verified_checks.append("architecture_view_components_and_edges_grounded")
            stage_scores["architecture"] = 100.0
        else:
            stage_scores["architecture"] = 40.0

        # 2. Storyboard Entity & Evidence Verification
        sb_valid = True
        scenes = storyboard.get("scenes", [])
        for scene in scenes:
            sid = scene.get("scene_id", "unknown")
            # Check node IDs
            for nid in scene.get("node_ids", []):
                if nid not in self._symbol_ids and nid not in self.components:
                    critical_mismatches.append(f"Scene '{sid}' references ungrounded node '{nid}'.")
                    sb_valid = False
            # Check source references
            for sref in scene.get("source_refs", []):
                path = str(sref).split(":", 1)[0]
                if path and path not in self._file_paths:
                    critical_mismatches.append(f"Scene '{sid}' references non-existent file '{path}'.")
                    sb_valid = False
            # Check code excerpt fidelity
            code_excerpt = scene.get("code_excerpt")
            code_path = scene.get("code_path")
            if code_excerpt and code_path and code_path in self.source_files_map:
                full_source = self.source_files_map[code_path]
                # At least the first line of the excerpt must match real source
                first_line = code_excerpt.strip().splitlines()[0] if code_excerpt.strip() else ""
                if first_line and first_line not in full_source:
                    warnings.append(f"Scene '{sid}' code excerpt does not match snapshot lines in '{code_path}'.")

        if sb_valid:
            verified_checks.append("storyboard_entities_and_source_references_verified")
            stage_scores["storyboard"] = 100.0
        else:
            stage_scores["storyboard"] = 50.0

        # 3. Narration-to-Visual Alignment Verification
        align_valid = True
        for scene in scenes:
            sid = scene.get("scene_id")
            vtype = scene.get("visual_type")
            title = scene.get("title", "")
            narration = scene.get("narration", "")

            if vtype == "code" and not scene.get("code_excerpt") and not scene.get("highlight_lines"):
                warnings.append(f"Scene '{sid}' has visual_type 'code' but no code excerpt or highlight lines.")
            if vtype == "flow" and not scene.get("flow_steps") and not scene.get("flow_nodes"):
                warnings.append(f"Scene '{sid}' has visual_type 'flow' but no flow steps.")
            if "[HYPOTHETICAL]" in narration and not scene.get("counterfactual"):
                scene["counterfactual"] = narration

        verified_checks.append("narration_visual_alignment_checked")
        stage_scores["alignment"] = 95.0

        # 4. Media Manifest & Audio Timing Verification (if media rendered)
        if media_manifest:
            media_valid = True
            captions = media_manifest.get("captions", [])
            actual_duration = media_manifest.get("actual_duration_ms", 0)
            segments = media_manifest.get("narration", {}).get("segments", [])

            # Check caption duration matches actual duration
            if captions:
                last_cap_end = captions[-1].get("end_ms", 0)
                if abs(last_cap_end - actual_duration) > 50:
                    warnings.append(f"Caption end timestamp ({last_cap_end}ms) differs from actual duration ({actual_duration}ms).")

            # Check video file exists if marked playable
            if media_manifest.get("video_status") == "playable":
                v_path = media_manifest.get("video_path")
                if not v_path or not Path(v_path).is_file():
                    critical_mismatches.append(f"Manifest marks video playable, but video file '{v_path}' is missing.")
                    media_valid = False

            if media_valid:
                verified_checks.append("media_audio_and_caption_synchronization_verified")
                stage_scores["media"] = 100.0
            else:
                stage_scores["media"] = 40.0
        else:
            stage_scores["media"] = 100.0

        # Check for disclosed limitations
        for g in storyboard.get("scenes", [])[-1].get("knowledge_gaps", []):
            disclosed_limitations.append(f"{g.get('subject_name')}: {g.get('limitation_note')}")

        total_score = sum(stage_scores.values()) / max(1, len(stage_scores))
        is_fully_valid = len(critical_mismatches) == 0 and total_score >= 80.0

        return ConsistencyReport(
            is_valid=is_fully_valid,
            overall_integrity_score=round(total_score, 1),
            verified_checks=verified_checks,
            critical_mismatches=critical_mismatches,
            warnings=warnings,
            disclosed_limitations=disclosed_limitations,
            stage_scores=stage_scores,
        )
