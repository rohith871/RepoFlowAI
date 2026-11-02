from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import media
from backend.analyzer import RepositoryAnalyzer
from backend.config import Settings
from backend.storage import PkmStore
from backend.understanding import SemanticUnderstandingEngine
from backend.execution_flows import ExecutionFlowTracer
from backend.architecture_reasoning import ArchitectureReasoningEngine
from backend.knowledge_gaps import KnowledgeGapDetector
from backend.semantic_storyboard import SemanticStoryboardBuilder

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "sample_project"
MEDIA_DIR = ROOT / "media" / "production_showcase"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

print("1. Ingesting and analyzing fixture...")
settings = Settings(storage_dir=ROOT / "tmp_storage")
settings.ensure_directories()
pkm_store = PkmStore(settings.database_path)
res = RepositoryAnalyzer(settings, pkm_store).analyse(FIXTURE)
snapshot = res.snapshot
files_map = {f.path: (FIXTURE / f.path).read_text(encoding="utf-8") for f in snapshot.files if (FIXTURE / f.path).is_file()}

engine = SemanticUnderstandingEngine(snapshot, files_map)
engine.parse_all()
understandings = engine.analyze_components()
tracer = ExecutionFlowTracer(snapshot, understandings, snapshot.relationships)
paths = tracer.trace_paths()
gaps = KnowledgeGapDetector(snapshot, understandings, paths, files_map).detect_all()
arch_engine = ArchitectureReasoningEngine(snapshot, understandings, snapshot.relationships, paths)
views = arch_engine.generate_views()

print(f"Verified {len(snapshot.symbols)} symbols, {len(snapshot.relationships)} relationships, {len(views)} architecture views.")

# Construct a rich multi-scene lesson showcasing every visual type
lesson = {
    "lesson_id": "production_showcase_001",
    "title": "RepoFlow AI Architecture & Data Lineage Deep Dive",
    "repository_name": "sample_project",
    "scenes": [
        {
            "scene_id": "sc_orient",
            "title": "Gateway Boundary & Public Entry",
            "kind": "orientation",
            "visual_type": "summary",
            "narration": "Welcome to RepoFlow AI's deep dive. We trace how external HTTP queries enter the system at the API gateway.",
            "source_refs": ["api.py:1-15"],
            "duration_ms": 1500,
        },
        {
            "scene_id": "sc_code",
            "title": "API Handler Implementation",
            "kind": "code_walkthrough",
            "visual_type": "code",
            "narration": "Here the user_route function extracts the name parameter and hands execution directly to get_user.",
            "code_path": "api.py",
            "code_excerpt": "def user_route(name: str):\n    # Extract parameter and delegate\n    user = get_user(name)\n    return {'name': user.name, 'status': 'active'}",
            "highlight_lines": [3, 4],
            "key_takeaway": "Transport handlers strictly decouple network routing from domain persistence logic.",
            "failure_mode": "[HYPOTHETICAL] Inlining database access here couples HTTP controllers directly to schema definitions.",
            "source_refs": ["api.py:3-5"],
            "duration_ms": 2000,
        },
        {
            "scene_id": "sc_arch",
            "title": "Subsystem Architectural Boundaries",
            "kind": "architecture_view",
            "visual_type": "architecture",
            "narration": "Examining the system view: the Gateway communicates strictly with the Domain layer, while Domain logic reads Models.",
            "nodes": [
                {"id": "n1", "label": "API Gateway", "role": "request_handler", "status": "verified_static"},
                {"id": "n2", "label": "Domain Service", "role": "business_logic", "status": "verified_static"},
                {"id": "n3", "label": "User Model", "role": "entity_model", "status": "verified_static"}
            ],
            "edges": [
                {"source": "n1", "target": "n2", "label": "calls", "status": "verified_static"},
                {"source": "n2", "target": "n3", "label": "instantiates", "status": "verified_static"}
            ],
            "source_refs": ["api.py", "app.py", "models.py"],
            "duration_ms": 2000,
        },
        {
            "scene_id": "sc_dataflow",
            "title": "End-to-End Data Lifecycle",
            "kind": "data_flow",
            "visual_type": "data_flow",
            "narration": "Data transitions across 5 verified stages: Raw string input is validated, passed to the domain loader, instantiated as a typed User entity, and returned.",
            "pipeline_stages": [
                {"id": "p1", "name": "Raw Query", "sub": "HTTP GET", "type": "input", "detail": "name='alice'"},
                {"id": "p2", "name": "user_route", "sub": "Validation", "type": "gateway", "detail": "api.py:3"},
                {"id": "p3", "name": "get_user", "sub": "Domain Logic", "type": "service", "detail": "app.py:8"},
                {"id": "p4", "name": "User Model", "sub": "Typed Entity", "type": "model", "detail": "models.py:4"},
                {"id": "p5", "name": "JSON Out", "sub": "Response Dict", "type": "output", "detail": "{'name': 'alice'}"}
            ],
            "active_packet_label": "User Record Payload",
            "source_refs": ["api.py", "app.py", "models.py"],
            "duration_ms": 2500,
        },
        {
            "scene_id": "sc_exec",
            "title": "Causal Execution Sequence",
            "kind": "execution_trace",
            "visual_type": "execution_flow",
            "narration": "Execution flows deterministically from step 1 entry call to step 5 serialization return.",
            "steps": [
                {"step_number": 1, "operation": "ENTRY_CALL", "symbol": "api.py:user_route", "summary": "Unpack query parameters"},
                {"step_number": 2, "operation": "CROSS_CALL", "symbol": "app.py:get_user", "summary": "Invoke domain service"},
                {"step_number": 3, "operation": "INSTANTIATE", "symbol": "models.py:User", "summary": "Construct typed domain entity"},
                {"step_number": 4, "operation": "RETURN", "symbol": "app.py:get_user", "summary": "Yield User instance"},
                {"step_number": 5, "operation": "SERIALIZE", "symbol": "api.py:user_route", "summary": "Format response JSON"}
            ],
            "source_refs": ["api.py", "app.py"],
            "duration_ms": 2000,
        }
    ]
}

print("2. Rendering complete educational video via media.render_lesson()...")
manifest = media.render_lesson(lesson, MEDIA_DIR)
print(f"Render completed with renderer: {manifest['renderer']}")
print(f"Video status: {manifest.get('video_status')}")
print(f"Video path: {manifest.get('video_path')}")

video_file = Path(manifest["video_path"])
if video_file.is_file():
    size_mb = video_file.stat().st_size / (1024 * 1024)
    print(f"Video file exists! Size: {size_mb:.2f} MB")
    
    # Generate frame contact sheet via ffmpeg
    contact_sheet_path = REPORT_DIR / "remotion_startup_quality_contact_sheet.png"
    # Extract 4 sample frames tiled 2x2
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_file),
        "-vf", "select='not(mod(n\\,30))',scale=640:360,tile=2x2",
        "-frames:v", "1",
        str(contact_sheet_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Generated contact sheet at: {contact_sheet_path}")
    except Exception as exc:
        print(f"Contact sheet generation error: {exc}")
else:
    print(f"ERROR: Video file not found at {video_file}")
