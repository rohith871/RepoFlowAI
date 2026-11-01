from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from backend.ids import stable_id


class TranscriptSegment(BaseModel):
    id: str
    scene_id: str
    lesson_section: str = "general"
    spoken_text: str
    educational_purpose: str = "concept_explanation"
    source_files: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    line_refs: list[str] = Field(default_factory=list)
    diagram_nodes: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    pronunciation_hints: dict[str, str] = Field(default_factory=dict)
    estimated_duration: float = 0.0
    segment_type: str = "concept_explanation"


class TranscriptValidationIssue(BaseModel):
    severity: str  # "error", "warning", "info"
    segment_id: str
    issue_type: str
    message: str
    suggestion: str = ""


class TranscriptValidationReport(BaseModel):
    is_valid: bool
    quality_score: float  # 0.0 to 100.0
    issues: list[TranscriptValidationIssue] = Field(default_factory=list)
    cleaned_segments: list[TranscriptSegment] = Field(default_factory=list)


def build_transcript_from_lesson(lesson: dict[str, Any]) -> list[TranscriptSegment]:
    """Extract and structure transcript segments from a lesson dictionary."""
    scenes = lesson.get("scenes", [])
    segments: list[TranscriptSegment] = []
    
    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"scene_{idx}")
        spoken = str(scene.get("narration", "")).strip()
        purpose = scene.get("objective", scene.get("title", f"Scene {idx + 1}"))
        source_refs = scene.get("source_refs", [])
        
        # Parse source files and line numbers
        source_files: list[str] = []
        line_refs: list[str] = []
        for ref in source_refs:
            if ":" in ref:
                parts = ref.split(":", 1)
                source_files.append(parts[0])
                line_refs.append(ref)
            elif ref:
                source_files.append(ref)
                
        # Approximate word count / duration (avg ~140 wpm = ~2.33 words/sec)
        words = len(spoken.split())
        est_duration = max(3.0, words / 2.33) if words > 0 else 0.0

        seg = TranscriptSegment(
            id=stable_id("segment", scene_id, str(idx)),
            scene_id=scene_id,
            lesson_section=scene.get("chapter_id", "main"),
            spoken_text=spoken,
            educational_purpose=str(purpose),
            source_files=list(dict.fromkeys(source_files)),
            symbols=scene.get("node_ids", []),
            line_refs=line_refs,
            diagram_nodes=[str(n.get("label", "")) for n in scene.get("visual_nodes", []) if isinstance(n, dict)],
            terms=[],
            pronunciation_hints={},
            estimated_duration=round(est_duration, 2),
            segment_type=scene.get("visual_type", scene.get("kind", "concept_explanation")),
        )
        segments.append(seg)
        
    return segments


class TranscriptValidator:
    """Validates transcript segments for pedagogical clarity, source consistency, and audio delivery."""

    BOILERPLATE_PATTERNS = [
        re.compile(r"\b(in this video (we will|we're going to))\b", re.IGNORECASE),
        re.compile(r"\b(welcome back to my channel|like and subscribe)\b", re.IGNORECASE),
        re.compile(r"\b(simply click|it goes without saying)\b", re.IGNORECASE),
        re.compile(r"\b(as we all know|obviously|clearly)\b", re.IGNORECASE),
    ]

    def __init__(self, known_files: set[str] | None = None, known_symbols: set[str] | None = None):
        self.known_files = known_files or set()
        self.known_symbols = known_symbols or set()

    def validate(self, segments: list[TranscriptSegment]) -> TranscriptValidationReport:
        issues: list[TranscriptValidationIssue] = []
        cleaned: list[TranscriptSegment] = []

        seen_texts: list[str] = []

        for idx, seg in enumerate(segments):
            text = seg.spoken_text.strip()
            
            # 1. Check for empty segments
            if not text:
                issues.append(TranscriptValidationIssue(
                    severity="error",
                    segment_id=seg.id,
                    issue_type="empty_narration",
                    message="Segment spoken text is completely empty.",
                    suggestion="Provide educational narration explaining the scene.",
                ))
                continue

            # 2. Check for boilerplate / filler phrases
            for bp in self.BOILERPLATE_PATTERNS:
                if bp.search(text):
                    issues.append(TranscriptValidationIssue(
                        severity="warning",
                        segment_id=seg.id,
                        issue_type="boilerplate_narration",
                        message=f"Boilerplate phrase detected: '{bp.pattern}'",
                        suggestion="Replace filler with direct technical explanation.",
                    ))

            # 3. Check for repetitive narration across scenes
            words_set = set(text.lower().split())
            for prev_idx, prev_text in enumerate(seen_texts):
                prev_words = set(prev_text.lower().split())
                if words_set and prev_words:
                    overlap = len(words_set & prev_words) / min(len(words_set), len(prev_words))
                    if overlap > 0.85 and len(words_set) > 6:
                        issues.append(TranscriptValidationIssue(
                            severity="error",
                            segment_id=seg.id,
                            issue_type="duplicate_narration",
                            message=f"Narration heavily duplicates segment {prev_idx + 1} ({int(overlap*100)}% token overlap).",
                            suggestion="Ensure each scene conveys distinct pedagogical progress.",
                        ))
            seen_texts.append(text)

            # 4. Check for unsupported source claims
            if self.known_files:
                for sf in seg.source_files:
                    clean_sf = sf.split(":")[0].strip()
                    if clean_sf and clean_sf not in self.known_files:
                        issues.append(TranscriptValidationIssue(
                            severity="warning",
                            segment_id=seg.id,
                            issue_type="unsupported_source_file",
                            message=f"Referenced source file '{clean_sf}' is not in the analyzed repository snapshot.",
                            suggestion="Ground citations in verified repository files.",
                        ))

            # 5. Check transition continuity
            if idx > 0 and len(segments) > 1:
                prev_seg = segments[idx - 1]
                # If switching files entirely without bridge words
                if seg.source_files and prev_seg.source_files:
                    if not set(seg.source_files) & set(prev_seg.source_files):
                        bridge_cues = {"next", "meanwhile", "in turn", "calls", "invokes", "passing to", "tracing into", "across", "delegates", "further"}
                        has_bridge = any(c in text.lower() for c in bridge_cues)
                        if not has_bridge and len(text.split()) > 10:
                            issues.append(TranscriptValidationIssue(
                                severity="info",
                                segment_id=seg.id,
                                issue_type="abrupt_transition",
                                message=f"Context switched between files without explicit architectural transition cue.",
                                suggestion="Clarify how execution or data moved between components.",
                            ))

            cleaned.append(seg)

        # Calculate quality score
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        
        penalty = (error_count * 20.0) + (warning_count * 5.0)
        score = max(0.0, min(100.0, 100.0 - penalty))

        return TranscriptValidationReport(
            is_valid=(error_count == 0),
            quality_score=round(score, 1),
            issues=issues,
            cleaned_segments=cleaned,
        )
