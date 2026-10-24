# RepoFlow AI — Video Quality and Media System

**Status:** Phase 1 design baseline — 24 October 2026

## 1. Quality objective

The output is a professionally narrated, YouTube-style technical lesson: understandable without staring at raw code, visually purposeful, synchronised to speech, grounded in the actual project, and useful as part of an interactive learning flow.

A render that completes technically but contains generic boxes, unreadable code, poor audio, unsynchronised captions, or unsupported claims fails the quality gate.

## 2. Media pipeline

```text
validated lesson/storyboard
  -> narration draft + claim/evidence validation
  -> local TTS candidate audio
  -> audio analysis (duration, pauses, loudness, timing where available)
  -> caption segments
  -> scene timing reconciliation
  -> project-specific visual scene graph
  -> Remotion render candidate
  -> automated media checks
  -> human/visual rubric review
  -> immutable media manifest + quality report
```

Narration and animation are not independently timed after the fact. Actual audio timing is an input to the scene timeline. If timing changes, captions and visual beats are regenerated or marked invalid.

## 3. Scene contract

Each scene binds:

- narrative purpose and learning objectives;
- validated narration claims;
- source evidence IDs and source navigation anchors;
- visual intent and scene type;
- code highlight ranges or graph nodes;
- camera/transition plan;
- actual audio and caption assets;
- interaction metadata: question anchors, replay range, resume point;
- validation status and failure reasons.

Initial scene types:

1. **orientation:** project goal, scope, and analysis limits;
2. **architecture:** project-specific modules and boundaries;
3. **code walkthrough:** readable source excerpt with progressive highlighting;
4. **execution/data flow:** supported static path with claim-level labels;
5. **data model:** models/relationships/query path where extracted;
6. **comparison/decision:** alternatives or trade-offs marked as explanation, not source fact;
7. **checkpoint:** question/transfer prompt with evidence references;
8. **recap:** verified facts, unresolved questions, and next-step preview.

## 4. Timing and synchronisation

- Store audio duration in milliseconds from the actual asset, not an estimate.
- Captions have start/end timestamps, text, scene ID, and optional word timing.
- Visual beats have start/end timestamps and an intended focal target.
- Scene boundaries allow configurable transition padding but cannot overlap required captions or hide source highlights.
- A timing validator rejects negative durations, excessive gaps, caption overflow, unreadable highlight windows, and metadata that references absent assets.
- Render manifests include renderer version, frame rate, resolution, audio sample rate, and asset hashes.

When word timing is unavailable, sentence/segment timing is acceptable only if visual review confirms intelligibility and alignment.

## 5. Visual identity

The design system defines and keeps consistent:

- typography hierarchy and minimum readable code/caption sizes;
- colour semantics for verified fact, inference, unresolved, warning, and learner focus;
- spacing/grid and safe areas;
- source-path and line-range labels;
- graph/node styles and arrow semantics;
- camera movement limits and transition vocabulary;
- caption style, contrast, and speaker treatment.

Movement must communicate a relationship, focus, sequence, or change in understanding. Decorative motion without learning purpose is discouraged.

## 6. Source-grounded visualisation rules

- Every project-specific node, arrow, code excerpt, route, schema, and label resolves to PKM IDs.
- Inferred edges are visually distinct from directly established facts.
- Unresolved or unsupported behaviour is shown as a boundary/question, not a confident animation.
- Code highlights show repository path and line range and are validated against the pinned snapshot.
- A scene cannot render as `validated` if an evidence reference is missing, cross-repository, or invalid.

## 7. Narration quality

Evaluate local TTS options rather than assuming any engine is acceptable. Record engine/version, voice, speed, pronunciation overrides, and audio hash.

Target checks:

- intelligibility for technical names and paths;
- natural pacing and pauses;
- no clipped words or overlapping segments;
- consistent loudness across scenes;
- pronunciation dictionary for symbols/acronyms;
- narration claim coverage and uncertainty language;
- transcript/caption agreement.

A human review sample is required for each narration engine/version before it becomes the default.

## 8. Automated quality checks

Every rendered lesson runs:

- media file/container/audio-track validation;
- duration and frame-count checks;
- caption bounds and overlap checks;
- scene asset/evidence reference checks;
- source path and line-range checks;
- resolution/frame-rate/audio sample-rate checks;
- blank-frame/frozen-frame detection where practical;
- text overflow and safe-area checks where the renderer exposes bounds;
- render determinism check on a small sample;
- manifest and checksum generation.

## 9. Human/visual rubric

Score 1–5 and record evidence for each category:

| Category | Passing target |
|---|---:|
| Technical correctness and evidence traceability | >= 4 |
| Narration intelligibility/naturalness | >= 4 |
| Caption accuracy and timing | >= 4 |
| Visual legibility and typography | >= 4 |
| Meaningful project-specific animation | >= 4 |
| Camera/transition purpose | >= 3 |
| Learning objective clarity | >= 4 |
| Audio/visual synchronisation | >= 4 |
| Interaction/resume metadata integrity | 100% automated validity |

A sample lesson must include at least one architecture/data-flow visual, one readable code walkthrough, one evidence-linked checkpoint, and one explicitly labelled uncertainty or analysis boundary.

## 10. Resource-aware rendering

Start with a low-resolution preview and short sample render before full output. Cache TTS, captions, parsed code images, and deterministic scene assets by content hash. Limit concurrency based on actual RAM/VRAM measurements. Do not download extra models without approval.

The initial quality gate records render time, peak memory, output size, and CPU/GPU use so quality improvements can be balanced against local hardware.

## 11. Failure handling

A failed scene does not silently produce a misleading video. The lesson remains in `draft` or `media_invalid`, the report identifies the scene/evidence/timing error, and previous validated media remains available if it exists. The player never presents a media asset whose manifest is invalid.
