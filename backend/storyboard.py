from __future__ import annotations

import re
from typing import Any

from backend.models import PkmSnapshot, Symbol


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_./:-]+", value.lower()) if len(token) > 1}


def _symbol_path(snapshot: PkmSnapshot, symbol: Symbol) -> str:
    file_item = next((item for item in snapshot.files if item.file_id == symbol.file_id), None)
    return file_item.path if file_item else ""


def _evidence_for(snapshot: PkmSnapshot, symbol: Symbol) -> list[dict[str, Any]]:
    path = _symbol_path(snapshot, symbol)
    return [
        item.model_dump(mode="json")
        for item in snapshot.evidence
        if item.source_path == path and item.line_start == symbol.line_start
    ]


def _scene_id(repository_id: str, scope: str, index: int) -> str:
    return f"story-{repository_id[-8:]}-{scope}-{index:03d}"


def build_storyboard(
    snapshot: PkmSnapshot,
    *,
    scope: str = "repository",
    question: str = "",
    detail: str = "summary",
    title: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, evidence-linked storyboard before any rendering starts."""
    scope_tokens = _tokens(question)
    symbols = [item for item in snapshot.symbols if item.kind != "module"]
    if scope in {"feature", "question", "module", "files"} and scope_tokens:
        ranked: list[tuple[float, Symbol]] = []
        for symbol in symbols:
            text = f"{symbol.name} {symbol.qualified_name} {_symbol_path(snapshot, symbol)}"
            score = float(len(scope_tokens & _tokens(text)))
            evidence_text = " ".join(item["excerpt"] or "" for item in _evidence_for(snapshot, symbol))
            score += float(len(scope_tokens & _tokens(evidence_text))) * 0.5
            if score:
                ranked.append((score, symbol))
        ranked.sort(key=lambda item: (-item[0], item[1].symbol_id))
        symbols = [symbol for _, symbol in ranked] or symbols

    symbol_limit = 14 if detail == "detailed" else 8
    selected_symbols = symbols[:symbol_limit]
    selected_ids = {item.symbol_id for item in selected_symbols}
    relationships = [
        item for item in snapshot.relationships
        if item.source_id in selected_ids or item.target_id in selected_ids
    ]
    if scope == "repository":
        relationships = snapshot.relationships[: (12 if detail == "detailed" else 6)]

    scenes: list[dict[str, Any]] = []
    scenes.append({
        "scene_id": _scene_id(snapshot.revision.repository_id, scope, 0),
        "chapter_id": "chapter-overview",
        "order": 1,
        "kind": "architecture_overview",
        "title": title or ("Repository architecture" if scope == "repository" else "Focused code explanation"),
        "objective": "Orient the viewer using the extracted repository structure.",
        "narration": (
            f"This explanation covers {len(snapshot.files)} analyzed files, {len(snapshot.symbols)} extracted symbols, "
            f"and {len(snapshot.relationships)} evidence-backed relationships. "
            "The visuals show only structures recovered from the pinned static-analysis revision."
        ),
        "source_refs": [item.path for item in snapshot.files[:8]],
        "node_ids": [item.symbol_id for item in selected_symbols[:10]],
        "edge_ids": [item.relationship_id for item in relationships[:10]],
        "visual_nodes": [{"id": item.symbol_id, "label": item.name, "kind": item.kind} for item in selected_symbols[:10]],
        "visual_edges": [{"source": item.source_id, "target": item.target_id, "type": item.relationship_type} for item in relationships[:10]],
        "visual_type": "architecture",
        "transition": "progressive-build",
        "highlight_lines": [],
    })

    for index, symbol in enumerate(selected_symbols, start=1):
        evidence = _evidence_for(snapshot, symbol)
        path = _symbol_path(snapshot, symbol)
        location = f"{path}:{symbol.line_start}-{symbol.line_end}"
        excerpt = evidence[0].get("excerpt", "") if evidence else ""
        scenes.append({
            "scene_id": _scene_id(snapshot.revision.repository_id, scope, index),
            "chapter_id": "chapter-components",
            "order": index + 1,
            "kind": "code_walkthrough",
            "title": symbol.name,
            "objective": f"Understand the {symbol.kind} {symbol.name} and its source location.",
            "narration": (
                f"The {symbol.kind} {symbol.name} is declared at {location}. "
                f"Its qualified name is {symbol.qualified_name}. "
                "The highlighted lines are taken directly from the analyzed snapshot; runtime behavior is not claimed."
            ),
            "source_refs": [location],
            "node_ids": [symbol.symbol_id],
            "edge_ids": [
                item.relationship_id
                for item in relationships
                if item.source_id == symbol.symbol_id or item.target_id == symbol.symbol_id
            ],
            "code_excerpt": excerpt,
            "visual_nodes": [{"id": symbol.symbol_id, "label": symbol.name, "kind": symbol.kind}],
            "visual_edges": [],
            "highlight_lines": list(range(symbol.line_start, min(symbol.line_end, symbol.line_start + 8) + 1)),
            "visual_type": "code",
            "transition": "focus-zoom",
        })

    for index, relationship in enumerate(relationships[: (10 if detail == "detailed" else 5)], start=len(scenes)):
        source = next((item for item in snapshot.symbols if item.symbol_id == relationship.source_id), None)
        target = next((item for item in snapshot.symbols if item.symbol_id == relationship.target_id), None)
        if source is None or target is None:
            continue
        scenes.append({
            "scene_id": _scene_id(snapshot.revision.repository_id, scope, index),
            "chapter_id": "chapter-flow",
            "order": index + 1,
            "kind": "data_flow" if relationship.relationship_type in {"reads", "writes", "imports"} else "execution_flow",
            "title": f"{source.name} → {target.name}",
            "objective": f"Trace the statically verified {relationship.relationship_type} relationship.",
            "narration": (
                f"Static analysis links {source.qualified_name} to {target.qualified_name} through a "
                f"{relationship.relationship_type} relationship. It is marked {relationship.status} with "
                f"{len(relationship.evidence_ids)} supporting evidence record(s)."
            ),
            "source_refs": list(dict.fromkeys(
                item.source_path for item in snapshot.evidence if item.evidence_id in relationship.evidence_ids
            )),
            "node_ids": [relationship.source_id, relationship.target_id],
            "edge_ids": [relationship.relationship_id],
            "flow_nodes": [source.name, target.name],
            "flow_edges": [relationship.relationship_id],
            "visual_nodes": [{"id": source.symbol_id, "label": source.name, "kind": source.kind}, {"id": target.symbol_id, "label": target.name, "kind": target.kind}],
            "visual_edges": [{"source": source.symbol_id, "target": target.symbol_id, "type": relationship.relationship_type}],
            "visual_type": "flow",
            "transition": "draw-connection",
            "highlight_lines": [],
        })

    scenes.append({
        "scene_id": _scene_id(snapshot.revision.repository_id, scope, len(scenes)),
        "chapter_id": "chapter-recap",
        "order": len(scenes) + 1,
        "kind": "recap",
        "title": "What the evidence establishes",
        "objective": "Separate verified structure from runtime uncertainty.",
        "narration": (
            "The final summary distinguishes parser-verified declarations and relationships from behavior that would "
            "require runtime observation. Use the cited source locations to continue the investigation."
        ),
        "source_refs": list(dict.fromkeys(item.source_path for item in snapshot.evidence[:8])),
        "node_ids": [item.symbol_id for item in selected_symbols[:10]],
        "edge_ids": [item.relationship_id for item in relationships[:10]],
        "visual_nodes": [{"id": item.symbol_id, "label": item.name, "kind": item.kind} for item in selected_symbols[:10]],
        "visual_edges": [{"source": item.source_id, "target": item.target_id, "type": item.relationship_type} for item in relationships[:10]],
        "visual_type": "summary",
        "transition": "fade-out",
        "highlight_lines": [],
    })
    word_count = sum(len(str(scene["narration"]).split()) for scene in scenes)
    payload = {
        "storyboard_version": "1.0",
        "repository_id": snapshot.revision.repository_id,
        "pkm_revision_id": snapshot.revision.pkm_revision_id,
        "scope": scope,
        "question": question,
        "detail": detail,
        "title": title or ("Repository architecture" if scope == "repository" else question or "Focused explanation"),
        "chapters": [
            {"chapter_id": chapter_id, "title": chapter_title, "scene_ids": [scene["scene_id"] for scene in scenes if scene["chapter_id"] == chapter_id]}
            for chapter_id, chapter_title in (
                ("chapter-overview", "Architecture overview"),
                ("chapter-components", "Important components"),
                ("chapter-flow", "Execution and data flow"),
                ("chapter-recap", "Evidence recap"),
            )
        ],
        "scenes": scenes,
        "estimated_duration_ms": int(word_count / 2.3 * 1000),
        "generation_provider": "deterministic-evidence-storyboard",
    }
    validate_storyboard(payload, snapshot)
    return payload


def validate_storyboard(storyboard: dict[str, Any], snapshot: PkmSnapshot) -> None:
    symbol_ids = {item.symbol_id for item in snapshot.symbols}
    relationship_ids = {item.relationship_id for item in snapshot.relationships}
    file_paths = {item.path for item in snapshot.files}
    for scene in storyboard.get("scenes", []):
        if not scene.get("scene_id") or not scene.get("narration"):
            raise ValueError("Storyboard scene is missing an identifier or narration")
        if not set(scene.get("node_ids", [])).issubset(symbol_ids):
            raise ValueError(f"Storyboard scene references an unknown symbol: {scene['scene_id']}")
        if not set(scene.get("edge_ids", [])).issubset(relationship_ids):
            raise ValueError(f"Storyboard scene references an unknown relationship: {scene['scene_id']}")
        for source_ref in scene.get("source_refs", []):
            path = str(source_ref).split(":", 1)[0]
            if path and path not in file_paths:
                raise ValueError(f"Storyboard scene references an unknown source file: {source_ref}")
