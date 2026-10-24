# RepoFlow AI — Phase 1 Implementation Plan

**Status:** Controlled implementation sequence — 24 October 2026  
**Starting condition:** The inspected project directory is empty and has no Git metadata, manifests, source, tests, or verified model configuration.

## 1. Implementation strategy

Implement vertically but in dependency order. Establish contracts and a thin executable skeleton before adding intelligence or media complexity. Each stage must leave a runnable, testable slice; do not generate a large untested codebase.

### Stage 0 — Environment and repository setup

1. Confirm Python, Node, package manager, SQLite, PyTorch, Ollama, available models, RAM, VRAM, and storage.
2. Create the project Git repository/branch only when the normal project setup process authorises it.
3. Add Python and TypeScript project manifests with pinned/compatible versions after runtime discovery.
4. Add formatting, linting, type checking, test, and basic CI commands.
5. Add a minimal FastAPI health endpoint and React shell.

**Current setup evidence:** Python 3.11.2, Node 22.23.3, and npm 10.9.9 are available. The `sqlite3` CLI, PyTorch import, and `ollama` CLI are unavailable in the current container; no model configuration or manifests exist.

**Exit evidence:** setup report, reproducible commands, and health test. Missing runtimes remain documented gaps; they are not hidden by installing unapproved dependencies.

## 2. Milestone work packages

### Milestone 1 — Architecture and contracts

Deliverables from this design pass:

- `PHASE1_SPEC.md`
- `ARCHITECTURE.md`
- `DATA_CONTRACTS.md`
- `ADAPTIVE_LEARNING.md`
- `VIDEO_QUALITY.md`
- `IMPLEMENTATION_PLAN.md`

Implementation tasks:

- translate contracts into Pydantic models and JSON Schema exports;
- define stable error codes and API envelope;
- add migration/version tests;
- define provider/analyzer/policy interfaces;
- add fixture repository and fixture learner scenarios.

Checks: schema round-trip tests, invalid-object rejection, cross-document reference check, API contract smoke test.

### Milestone 2 — Repository intelligence

- repository registration and safe snapshot capture;
- filtering and content hashing;
- Python AST analyzer first;
- symbols, imports, entry points, routes, common schemas/models where detectable;
- evidence builder with line-range validation;
- relationship resolver with direct/resolved/candidate/unresolved statuses;
- SQLite store, JSON export, immutable revision publication;
- incremental re-analysis based on file hashes and dependency invalidation;
- unsupported-language/dynamic-behaviour reports.

Checks: a small real Python project plus a known fixture with expected symbols/imports/routes/calls; evidence path and line tests; repository-isolation tests; repeat-run cache tests.

### Milestone 3 — RAG and reasoning

- exact search over source/evidence;
- typed PKM queries and bounded relationship traversal;
- lexical ranking and optional semantic index only if local resource measurements support it;
- evidence-aware context assembly;
- Ollama/Qwen2.5-Coder 7B adapter if present, with a mock provider for tests;
- structured explanation output and claim validator;
- explicit assumptions, inferences, and unresolved questions;
- provider timeout/error/fallback handling.

Checks: question set with expected evidence IDs; unsupported-claim rejection; unresolved dynamic-call case; context budget and cross-repository tests; model-free deterministic tests.

### Milestone 4 — Lesson planning

- learning-goal and prior-knowledge input;
- chapter/scene/step generator from PKM;
- prompt/template or deterministic planner versioning;
- storyboard validation against PKM and data contracts;
- evidence-linked question seeds and interaction metadata;
- source navigation anchors and resume anchors.

Checks: validated storyboard fixture; missing-evidence rejection; no unsupported node/edge render instructions; prerequisite graph validation; step completion criteria tests.

### Milestone 5 — Narration and visual system

- narration provider interface and local TTS evaluation harness;
- transcript/caption generation;
- actual audio duration extraction and timing reconciliation;
- scene graph and initial Remotion components;
- code highlight, architecture/data-flow, and checkpoint components;
- preview render and automated media validation;
- quality rubric record.

Checks: short sample render, caption/audio timing tests, evidence-linked visual manifest, readable code review, TTS comparison report, resource measurements.

### Milestone 6 — Full video production

- orchestration from repository revision through final media manifest;
- resumable jobs and cached intermediate artefacts;
- complete lesson render for a representative supported project;
- user-visible progress/errors and last-known-good media retention.

Checks: clean end-to-end run and rerun with no source changes; changed-file incremental run; failure recovery; final quality rubric.

### Milestone 7 — Interactive learning

- player with chapters, replay, captions, resume;
- current-scene/step context service;
- source navigation with evidence permissions;
- contextual question endpoint and answer validator;
- attempt/hint/revisit/transfer event recording;
- authoritative progress UI with locked/available/in-progress/completed states.

Checks: resume after interruption; contextual question evidence tests; frontend cannot unlock; help/retry/revisit flows; keyboard/accessibility smoke tests.

### Milestone 8 — Adaptive guidance

- learner event ledger and state estimator;
- deterministic rule baseline;
- PyTorch simulator, DQN-style candidate, offline evaluation harness;
- policy registry/versioning and action masks;
- fallback and timeout behaviour;
- progression enforcement integration.

Checks: simulator reproducibility; baseline comparison; invalid-action masking; policy failure fallback; no invalid unlock in adversarial tests; measurable intervention response.

### Milestone 9 — Integration and evaluation

- representative repository matrix and expected PKM facts;
- end-to-end correctness/evidence tests;
- video rubric reports;
- learning progression and policy evaluation;
- performance/resource baselines;
- usability/error recovery scenarios;
- known limitations and release decision.

Checks: documented target table with actual measured results, not aspirational claims.

## 3. Representative fixtures

Create small, legally safe fixtures rather than depending on a single large repository:

1. Python web service with routes, service layer, repository/data access, model, migration, and one dynamic/unresolved call.
2. Python package with imports, classes, methods, functions, CLI entry point, and configuration.
3. Unsupported-language fixture to verify explicit limitations.
4. Repository pair with same file names but different facts to test isolation.
5. Learner scenarios covering novice, help-dependent, returning, and transfer learners.

Add at least one real supported project only when permission and local resources are confirmed.

## 4. Authorised intelligent improvements

These are approved as low-risk design choices because they preserve the requested scope:

- **Immutable PKM revisions + content-addressed caches:** prevents lessons from silently drifting and reduces repeated analysis. Cost: disk and migration discipline.
- **Evidence-first context budgets:** rank exact/structured evidence before semantic results to reduce local inference cost and unsupported context. Cost: more retrieval plumbing.
- **Candidate relationship states:** preserve ambiguity instead of forcing false certainty. Cost: UI and explanation complexity.
- **Schema-generated validation:** use Pydantic/JSON Schema and contract tests to catch drift across analyzers, planners, media, and frontend. Cost: upfront model work.
- **Model-free deterministic fallbacks:** keep tests and local operation useful when Ollama/TTS/PyTorch are unavailable. Cost: two paths to maintain.
- **Preview-before-full-render:** reduce wasted compute and expose quality problems early. Cost: additional render orchestration.
- **Rule baseline before DQN activation:** gives a measurable, interpretable teaching policy and prevents premature ML dependency. Cost: staged rollout.
- **Append-only learner events:** supports reproducibility and future policy training without overwriting history. Cost: retention/privacy policy needed.

These improvements do not remove any mandatory Phase 1 capability or acceptance criterion.

## 5. Resource and privacy guardrails

- Do not add paid API dependencies.
- Do not download models without explicit approval.
- Verify actual Ollama/model availability before building around it.
- Keep source excerpts bounded and avoid secrets in logs/exports.
- Never execute uploaded code in the initial pipeline.
- Prefer CPU-compatible, small deterministic tests; reserve model/render tests for explicit integration jobs.
- Record RAM/VRAM/storage and latency baselines before choosing concurrency or semantic index settings.

## 6. Evaluation record format

For each milestone, record date and commit, fixture/repository and PKM revision, command and working directory, input/model/parser/policy/renderer versions, expected/actual result, timing/resource measurements, failures/warnings/known limitations, and acceptance decision/follow-up issue.

The evaluation record is part of the product evidence, not an informal note.

## 7. Initial checks to establish after setup

Use the project's actual manifests once created. The expected command families are:

```text
Python:  pytest -q
Python:  ruff check .
Python:  mypy <configured packages>
Web:     npm test / npm run lint / npm run typecheck / npm run build
Media:   preview render + media validation command
```

These are planned command families, not claims that they currently exist. The first setup task must replace them with exact commands and record missing tools honestly.

## 8. Completion definition

Phase 1 is complete only when all nine acceptance gates pass on representative fixtures and at least one supported real project, with documented limitations, evidence traceability, rendered-video quality review, interactive progression tests, and adaptive-policy baseline results. A demo that omits PKM traceability, visual quality, interaction, or progression enforcement is not a Phase 1 completion.
