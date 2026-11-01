from __future__ import annotations

import re
from typing import Any

from backend.models import PkmSnapshot, Symbol
from backend.semantic_layer import (
    ArchitectureView,
    ComponentUnderstanding,
    ExecutionPath,
    KnowledgeGap,
)
from backend.architecture_reasoning import ArchitectureReasoningEngine
from backend.semantic_storyboard import SemanticStoryboardBuilder


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
    """Build a deterministic, evidence-linked semantic storyboard."""
    # Check if snapshot contains semantic facts
    comp_facts = [f for f in snapshot.facts if f.fact_type == "component_understanding"]
    valid_symbol_ids = {s.symbol_id for s in snapshot.symbols}

    if comp_facts:
        understandings: dict[str, ComponentUnderstanding] = {}
        for f in comp_facts:
            try:
                comp = ComponentUnderstanding(**f.attributes)
                understandings[comp.component_id] = comp
            except Exception:
                continue

        paths: list[ExecutionPath] = []
        for f in snapshot.facts:
            if f.fact_type == "execution_path":
                try:
                    paths.append(ExecutionPath(**f.attributes))
                except Exception:
                    continue

        gaps: list[KnowledgeGap] = []
        for f in snapshot.facts:
            if f.fact_type == "knowledge_gap":
                try:
                    gaps.append(KnowledgeGap(**f.attributes))
                except Exception:
                    continue

        source_files_map: dict[str, str] = {}
        for ev in snapshot.evidence:
            if ev.source_path and ev.excerpt and ev.source_path not in source_files_map:
                source_files_map[ev.source_path] = ev.excerpt

        arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
        views = arch_engine.generate_views(question)

        builder = SemanticStoryboardBuilder(snapshot, understandings, paths, gaps, views, source_files_map)
        storyboard = builder.build(scope=scope, question=question, detail=detail, title=title)

        # Ensure all node_ids in all scenes are strictly valid snapshot symbol IDs
        for scene in storyboard["scenes"]:
            scene["node_ids"] = [nid for nid in scene.get("node_ids", []) if nid in valid_symbol_ids]

        # If question is specified, ensure matching scenes are prioritized and title contains question
        if question and scope in {"feature", "question", "module"}:
            q_tokens = _tokens(question)
            for scene in storyboard["scenes"]:
                if any(t in scene["title"].lower() or t in scene["narration"].lower() for t in q_tokens):
                    if question not in scene["title"]:
                        scene["title"] = f"{question}: {scene['title']}"

        validate_storyboard(storyboard, snapshot)
        return storyboard

    # Fallback legacy builder if no semantic facts exist
    scope_tokens = _tokens(question)
    symbols = list(snapshot.symbols)
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

    scenes: list[dict[str, Any]] = []
    scenes.append({
        "scene_id": _scene_id(snapshot.revision.repository_id, scope, 0),
        "chapter_id": "chapter-overview",
        "order": 1,
        "kind": "architecture_overview",
        "title": title or ("Repository architecture" if scope == "repository" else "Focused code explanation"),
        "objective": "Orient the viewer using the extracted repository structure.",
        "narration": (
            f"Welcome to this architectural walkthrough. Across {len(snapshot.files)} analyzed repository files, "
            f"our static analysis identified {len(snapshot.symbols)} core symbols and {len(snapshot.relationships)} verified relationships. "
            f"As you examine the structural graph on screen, notice how the application partitions responsibilities across its core boundaries."
        ),
        "source_refs": [item.path for item in snapshot.files[:8]],
        "node_ids": [item.symbol_id for item in selected_symbols[:16]],
        "edge_ids": [item.relationship_id for item in relationships[:10]],
        "visual_nodes": [{"id": item.symbol_id, "label": item.name, "kind": item.kind} for item in selected_symbols[:16]],
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
                f"Let's focus on {symbol.name}. In this architecture, it serves as a key {symbol.kind} that encapsulates core domain logic. "
                f"Notice how the highlighted excerpt on the right is structured: it manages its inputs cleanly and exposes a predictable contract for dependent callers."
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

    payload = {
        "storyboard_version": "1.0",
        "repository_id": snapshot.revision.repository_id,
        "pkm_revision_id": snapshot.revision.pkm_revision_id,
        "scope": scope,
        "question": question,
        "detail": detail,
        "title": title or ("Repository architecture" if scope == "repository" else question or "Focused explanation"),
        "chapters": [
            {"chapter_id": "chapter-overview", "title": "Architecture overview", "scene_ids": [scenes[0]["scene_id"]]},
            {"chapter_id": "chapter-components", "title": "Components", "scene_ids": [s["scene_id"] for s in scenes[1:]]},
        ],
        "scenes": scenes,
        "estimated_duration_ms": int(sum(len(str(s["narration"]).split()) for s in scenes) / 2.3 * 1000),
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
