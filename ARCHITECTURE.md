# RepoFlow AI — Architecture

**Status:** Phase 1 design baseline — 24 October 2026

## 1. Architectural shape

RepoFlow AI is a local-first modular application with a versioned, repository-isolated Project Knowledge Model (PKM) at its centre.

```text
React/TypeScript client
        |
        v
FastAPI application/API
  |        |          |
  |        |          +--> Learning service --> PyTorch policy adapter
  |        +--> Lesson/media orchestration
  +--> Reasoning service --> hybrid retrieval
  |                           |-- exact search
  |                           |-- PKM query/traversal
  |                           +-- optional semantic index
        |
        v
SQLite metadata + JSON artefacts + content-addressed source/cache files
        ^
        |
Ingestion coordinator -> filters -> language analyzers -> relationship resolver
                                      -> evidence builder -> PKM validator

Media worker: validated storyboard -> TTS -> captions/timing -> Remotion scene graph -> render -> quality report
```

The first implementation may run all services in one FastAPI process and worker process. Interfaces are explicit so expensive or isolated work can move to separate processes later without changing contracts.

## 2. Component boundaries

### Repository gateway

Accepts a local path/archive, assigns `repository_id`, enforces authorized-folder policy, hashes files, applies ignore/binary/size filters, and exposes immutable source snapshots. It never executes repository code and records skipped files and unsupported extensions.

### Ingestion coordinator

Creates an `analysis_run`, compares file hashes with the last successful run, schedules changed-file analysis, invalidates affected derived facts/edges, and publishes a new PKM revision only after validation succeeds. Failed runs do not replace the last known-good revision.

### Analyzer registry

Analyzers implement:

```python
analyze(snapshot: SourceSnapshot, options: AnalysisOptions) -> AnalyzerResult
```

A result contains facts, evidence, candidate relationships, warnings, and capability metadata. Python AST is the initial parser. Other adapters may be added only with explicit dependency and quality review.

### PKM store and validator

SQLite is the authoritative queryable store for metadata, facts, evidence, relationships, revisions, and validation results. JSON export is a portable snapshot/debug format, not a second mutable source of truth.

Validation checks schema/version compatibility, stable ID uniqueness, same-repository endpoints, source path/line ranges, evidence method/status, relationship support, lesson references, and repository isolation.

### Retrieval and reasoning

A query planner selects exact path/symbol/text search, structured fact filters, bounded relationship traversal, lexical ranking, and optional local semantic retrieval. Context assembly produces a bounded typed package with citations, verification labels, unresolved questions, and truncation metadata. Provider adapters return Pydantic-validated structured outputs.

### Lesson planner

Transforms a learning goal plus PKM context into chapters, validated scenes, ordered steps, question seeds, narration drafts, visual instructions, and evidence links. Generated objects carry `generation_run_id`, input PKM revision, and validation state. The planner cannot create unsupported facts.

### Media system

Separates narration text/pronunciation metadata, audio assets/durations, captions/timestamps, visual scene graph/source highlights, evidence/interaction metadata, and render configuration/quality report. Remotion is the initial rendering candidate.

### Learning service

Owns learner profiles, lesson enrollment, step attempts, hints, questions, revisits, transfer tasks, and learner-state features. It asks the policy adapter for an intervention. It alone enforces prerequisites and completion criteria; the frontend is not trusted for unlocking.

### Policy adapter

```python
select_action(state: LearnerState, action_mask: ActionMask, context: LessonContext) -> PolicyDecision
```

The adapter validates feature schema/version, masks invalid actions, applies a timeout/budget, records model version, and falls back to a deterministic rule policy if inference fails.

## 3. Data and storage layout

```text
storage/
  app.sqlite3
  repositories/<repository_id>/snapshots/<revision_id>/...
  repositories/<repository_id>/exports/<revision_id>.json
  repositories/<repository_id>/media/<lesson_id>/...
  cache/analysis/<content_hash>/...
  cache/retrieval/<pkm_revision_id>/...
  models/policies/<policy_version>/...
```

SQLite tables are normalized for queryability. JSON artefacts are immutable exports and media manifests. Content-addressed caches are safe to delete and rebuild.

`repository_id` is mandatory on every project-specific table and cache key. Cross-repository joins are rejected at the data-access boundary.

## 4. PKM lifecycle

1. Register repository and capture a source snapshot.
2. Filter files and record exclusions.
3. Run analyzers for changed/affected files.
4. Resolve symbols and candidate relationships.
5. Attach source evidence and verification metadata.
6. Validate the candidate revision.
7. Publish an immutable `pkm_revision` only if validation passes.
8. Build/reuse exact, structured, and optional semantic indexes.
9. Make the revision addressable by lessons and explanations.

A new analysis revision never silently mutates the source of an existing lesson. Lessons pin their input PKM revision and display when newer analysis is available.

## 5. Trust and failure boundaries

| Boundary | Failure handling |
|---|---|
| Archive/path input | Reject traversal, unauthorized paths, oversized/binary abuse; record safe diagnostic |
| Parser | Isolate per file; preserve partial facts and warning; do not fail whole repository unnecessarily |
| Relationship resolver | Emit `ambiguous`/`unresolved`; never upgrade static candidates to runtime verified |
| Model provider | Timeout/retry within budget; return typed provider error or deterministic fallback where safe |
| TTS/render | Preserve prior artefact; mark scene/media invalid with actionable diagnostics |
| Learner policy | Mask invalid actions; use rule fallback; never unlock by policy suggestion |
| SQLite/JSON | Transactional revision publish; retain last known-good revision |
| Frontend | Treat server statuses as authoritative; show locked state from server |

## 6. API surface (initial)

All project-specific endpoints require `repository_id` and relevant revision/lesson identifiers.

- `POST /api/repositories` — register/upload metadata, no execution.
- `POST /api/repositories/{id}/analysis-runs` — start analysis.
- `GET /api/repositories/{id}/analysis-runs/{run_id}` — inspect progress/errors.
- `GET /api/repositories/{id}/pkm/{revision_id}` — query/export validated PKM.
- `POST /api/repositories/{id}/retrieve` — run typed hybrid retrieval.
- `POST /api/lessons` — plan a lesson from PKM revision and goal.
- `GET /api/lessons/{id}/storyboard` — inspect validation/evidence links.
- `POST /api/lessons/{id}/render` — enqueue media production.
- `GET /api/lessons/{id}/media` — retrieve manifest/quality report.
- `POST /api/enrollments/{id}/questions` — ask in current lesson context.
- `POST /api/steps/{id}/attempts` — submit activity evidence.
- `POST /api/steps/{id}/hints` — request support.
- `GET /api/enrollments/{id}/progress` — authoritative statuses and next allowed action.

Responses use `DATA_CONTRACTS.md`; errors use stable codes and include a trace ID, not a raw stack trace.

## 7. Dependency policy

Required initial targets: Python/FastAPI, Pydantic, SQLite/JSON, Python AST and appropriate parsers, PyTorch, React/TypeScript, Remotion candidate, local narration tools, Git/GitHub, and existing Ollama/Qwen2.5-Coder 7B if available.

No paid API, model download, or material external dependency is introduced without approval. Discovery is a setup gate because the inspected directory contains no manifests or lockfiles.

## 8. Observability

Every analysis, retrieval, generation, render, policy decision, and progression decision records trace/run ID, input revision/model/policy versions, duration/resource counters where available, validation outcome, warnings/fallback reason, and output artifact IDs. Logs must not include secrets or full private source excerpts by default.

## 9. Decisions and trade-offs

- **SQLite + JSON first:** low operational overhead and reproducible local development; migration discipline is needed before multi-user scale.
- **Immutable revisions:** improves traceability and rollback; uses more disk, mitigated by content-addressed snapshots/incremental analysis.
- **Provider adapters:** keeps local inference replaceable; adds interface/test maintenance.
- **Optional semantic index:** exact/structured retrieval remains useful on low-resource hardware; semantic search is additive, not a hidden requirement.
- **Single-process initial deployment:** simplifies setup; worker boundaries prevent permanent coupling.
