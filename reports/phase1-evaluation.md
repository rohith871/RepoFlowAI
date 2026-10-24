# RepoFlow AI — Phase 1 Evaluation Record

**Date:** 24 October 2026  
**Environment:** Windows host, Python 3.13 project virtual environment, Node/npm frontend toolchain

## Implemented slices

| Milestone | Current evidence |
|---|---|
| 1 | Pydantic PKM contracts, stable IDs, FastAPI error-shaped responses, environment configuration, health endpoint |
| 2 | Safe static repository scan, Python AST symbols/imports/calls, web/SQL heuristics, source evidence, immutable SQLite revisions, JSON export, isolation keys, unchanged-revision reuse |
| 3 | Exact/structured/lexical evidence retrieval, unresolved relationship reporting, deterministic explanation fallback, optional Ollama provider adapter |
| 4 | Evidence-linked chapters, scenes, narration text, source references, ordered steps, prerequisites, completion criteria, validation status |
| 5 | Scene manifest, SVG visual frames, caption timing metadata, evidence/source labels, media capability detection, truthful TTS/render fallback |
| 6 | End-to-end repository -> PKM -> lesson -> media manifest orchestration; playable MP4 is attempted only when FFmpeg and a rasteriser are available |
| 7 | FastAPI question, source, enrollment, progress, attempt, hint, and media endpoints; React repository/lesson/progress/question workflow |
| 8 | Append-only event/attempt storage, learner-state features, deterministic rule policy, lazy PyTorch DQN candidate interface, baseline evaluation report |
| 9 | Fixture repository, automated tests, backend static checks, frontend typecheck/build, documented limitations |

## Commands actually run

Backend:

```text
".venv-win/Scripts/ruff.exe" check .
".venv-win/Scripts/mypy.exe" .
".venv-win/Scripts/python.exe" -m pytest -q
```

Frontend:

```text
npm install
npm run typecheck
npm run build
```

End-to-end API smoke flow:

```text
analyse fixture -> create lesson -> enrol learner -> read progress
-> submit evidence-backed attempt -> ask evidence question -> render media
```

Observed result: repository analysis, lesson creation, enrollment, locked-step progress, completed-attempt unlocking, evidence-ranked question response, and media manifest generation all returned successfully for `fixtures/sample_project`.

## Current limitations

- The current environment does not expose FFmpeg, an SVG rasteriser, or a local TTS engine. The media pipeline therefore reports `blocked_missing_ffmpeg` and `fallback_text_only` rather than claiming a playable narrated video.
- PyTorch is not installed in the project environment. The rule-based policy is the active fallback; the DQN adapter and evaluation interface are present but no neural policy has been trained or evaluated.
- Ollama availability is detected at runtime through its HTTP API. A deterministic evidence-first answer is returned if the service/model is unavailable or returns malformed structured output.
- Web and framework analysis uses conservative regular-expression adapters in this slice. Unsupported and dynamic behaviour is surfaced rather than treated as verified.
- The current frontend uses scene navigation and timing metadata as a fallback player until a validated playable media asset is available.

## Quality and safety notes

- Uploaded repository code is not executed.
- Source snapshots are copied into repository/revision-scoped storage and addressed by immutable PKM revision.
- Cross-repository PKM references are rejected by the model/store boundary design.
- Completion is backend-validated using score and evidence-reference criteria; policy suggestions never unlock steps.
- No claims of zero hallucinations, perfect reliability, trained neural policy performance, or successful video rendering are made when dependencies are unavailable.
