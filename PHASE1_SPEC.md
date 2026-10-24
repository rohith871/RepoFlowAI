# RepoFlow AI — Phase 1 Specification

**Status:** Design baseline — 24 October 2026  
**Scope:** Complete Phase 1 product and engineering contract  
**Source of truth:** The Project Knowledge Model (PKM), not model memory or free-form notes.

## 1. Product intent

RepoFlow AI turns a real software repository into a source-grounded technical learning experience: a structured repository analysis becomes a narrated, animated lesson with evidence-linked explanations, interactive questions, and adaptive, sequential practice.

Phase 1 is deliberately more than a chatbot, code summary, static architecture diagram, slide deck, or animation proof of concept. It must preserve the complete flow:

```text
repository -> Project Knowledge Model -> evidence-grounded reasoning
            -> validated lesson/storyboard -> narrated animated video
            -> interactive learning -> adaptive guided practice
            -> measured completion and evaluation
```

The first useful user outcome is: a learner selects a supported repository, chooses a learning goal and prior-knowledge level, receives a validated lesson plan and rendered sample/full lesson, asks source-grounded questions while learning, and completes an ordered set of evidence-backed activities whose progression is enforced by the backend.

## 2. Phase 1 principles

1. **Evidence before fluency.** Every project-specific claim must cite PKM facts and source evidence. If evidence is incomplete, the system says so.
2. **Facts and inferences are separate.** Static analysis may suggest a relationship but cannot label it a verified runtime path without runtime evidence.
3. **PKM is shared infrastructure.** Retrieval, explanations, storyboards, visualisations, questions, and teaching policy all consume the same versioned, repository-isolated model.
4. **Learning is sequential and demonstrable.** Watching alone does not satisfy assessment criteria. Unlocking is a backend decision.
5. **Personalisation changes pedagogy, not source truth.** Depth, pacing, examples, hints, and assessment presentation may vary; repository facts may not.
6. **Quality is evaluated on rendered artefacts.** A successful render is not sufficient proof of a good lesson.
7. **Local-first and modular.** Python/FastAPI, SQLite/JSON, Ollama/Qwen2.5-Coder 7B where available, PyTorch, React/TypeScript, and Remotion are the initial targets. Provider interfaces remain replaceable.
8. **Isolation by default.** Uploaded code is parsed and indexed without arbitrary execution. Any future execution feature needs a separate sandbox design and approval.

## 3. Users and entry paths

### 3.1 Primary learner

A developer or student wants to understand an unfamiliar codebase and prove understanding through guided activities.

### 3.2 Required entry paths

1. **Related project:** continue with another project in a related domain using prior learner performance to suggest a starting level; verify mastery when the new project differs materially.
2. **Different repository:** upload or select another repository and build an isolated PKM.
3. **Goal-driven start:** choose a project, declare prior knowledge and learning goals, then receive an initial diagnostic or conservative starting level.

### 3.3 Internal/system actors

- **Ingestion coordinator:** owns repository registration, filtering, hashing, incremental analysis, and run status.
- **Analyzers:** language/framework-specific extractors that emit facts, evidence, and candidate relationships.
- **PKM validator:** checks schema, identifiers, evidence ranges, endpoint existence, version compatibility, and repository isolation.
- **Reasoning service:** retrieves and assembles evidence-grounded context and produces structured explanations.
- **Lesson planner:** turns validated PKM context into chapters, scenes, narration, visuals, questions, and ordered steps.
- **Media pipeline:** produces audio, captions, timing, animation, and render validation results.
- **Learning service:** records attempts and learner state, calls the teaching policy, and enforces progression.

## 4. Required Phase 1 capabilities

### 4.1 Repository intelligence

A supported real project can be analysed into:

- projects, directories, files, hashes, language/framework metadata;
- modules, imports, dependencies, symbols, entry points, routes, schemas, middleware;
- supported database models, relationships, queries, and migrations;
- configuration and external integrations where reliably extractable;
- source evidence with stable identifiers, paths, line ranges, excerpts/references, extraction method, parser version, and verification status;
- relationship edges with endpoints, type, evidence, verification method, and status;
- explicit unsupported-language and dynamic-behaviour records;
- incremental re-analysis metadata.

### 4.2 Reasoning and retrieval

The system combines exact code search, structured PKM queries, relationship traversal, and semantic retrieval when useful. Context assembly must preserve evidence references and distinguish verified facts, inferences, assumptions, and unresolved questions.

### 4.3 Lesson planning

A validated storyboard contains project-specific chapters and scenes. Every scene includes learning objective, narrative/narration, visual intent, source references, interaction metadata, and validation status.

### 4.4 Narration and visuals

The media system targets polished YouTube-style education: meaningful architecture and data-flow animation, code walkthroughs, camera transitions, captions, timing synchronisation, and project-specific visual explanations.

### 4.5 Interactive learning

The player supports chapters, replay, captions, source navigation, resume, contextual questions, and evidence-linked answers. The current lesson context and relevant source evidence are supplied to question answering.

### 4.6 Adaptive guidance

Learner-state estimation, teaching-action selection, and progression enforcement are separate responsibilities. A PyTorch policy is evaluated against fixed-hint and rule-based baselines. Inference failure falls back safely and cannot unlock future steps.

## 5. Nine milestones and acceptance gates

| Milestone | Deliverable focus | Acceptance gate |
|---|---|---|
| Milestone 1 — Architecture and contracts | Structure, boundaries, schemas, interfaces, errors, dependencies; six design documents | Contracts are internally consistent and implementation-ready |
| Milestone 2 — Repository intelligence | Ingestion, filtering, parsing, symbols, relationships, evidence, PKM | A supported real project is analysed and findings trace to source evidence |
| Milestone 3 — RAG and reasoning | Hybrid retrieval, context assembly, structured explanations, uncertainty | Answers cite relevant evidence and identify unresolved questions |
| Milestone 4 — Lesson planning | Chapters, scenes, narration scripts, visual instructions, validation | A validated storyboard is produced from PKM |
| Milestone 5 — Narration and visual system | Audio, animation, captions, synchronisation, quality checks | Rendered sample meets technical and visual quality rubric |
| Milestone 6 — Full video production | End-to-end integration and render | A real supported project produces a complete narrated animated explainer |
| Milestone 7 — Interactive learning | Player, chapters, captions, questions, source navigation, resume | Learner can ask in-context questions and resume appropriately |
| Milestone 8 — Adaptive guidance | Learner state, PyTorch policy, guided tasks, hints, progression lock | Interventions respond measurably; next step remains locked until completion |
| Milestone 9 — Integration and evaluation | Correctness, traceability, learning, video, usability, performance, errors | Documented targets are met on representative tests and baselines |

Each gate requires automated checks where practical plus a recorded manual/visual evaluation for user-facing media and progression behaviour.

## 6. Sequential learning contract

Every step has:

- stable step identifier and PKM/lesson version;
- prerequisites;
- learning objective;
- required activities;
- completion criteria;
- source evidence;
- associated scenes;
- support and hint options;
- status: `locked`, `available`, `in_progress`, or `completed`.

The backend validates completion from recorded evidence (answers, code navigation, transfer task, or other defined activity), then issues an unlock decision. Help use is recorded but does not permanently block progression. Retrying, revisiting, and transfer questions are first-class flows.

## 7. Non-goals and explicit limits

- No claim of zero hallucinations, perfect reliability, or complete runtime understanding.
- No arbitrary execution of uploaded code in the initial architecture.
- No paid model/API dependency and no unapproved model download.
- No use of a chatbot transcript as the PKM.
- No bypass of evidence validation because a language model sounds confident.
- No automatic mastery credit from video viewing when an assessment is required.

## 8. Initial assumptions and setup findings

The inspected `RepoFlowAI` directory was empty on 24 October 2026: no source files, manifests, dependency lockfiles, model configuration, tests, or Git metadata were present. Therefore this specification treats the requested Python/FastAPI + React/TypeScript + SQLite/JSON + PyTorch + Ollama/Remotion stack as the approved initial target, not as already-installed infrastructure. Runtime discovery and dependency checks are Milestone 1 implementation work. The current container check found Python 3.11.2, Node 22.23.3, and npm 10.9.9; the `sqlite3` CLI, PyTorch import, and `ollama` CLI were not available. No model configuration was present, so Qwen2.5-Coder 7B remains an unverified target rather than an assumed dependency.

## 9. Definition of done for this specification

The six Phase 1 design documents agree on:

- PKM entities and evidence semantics;
- service boundaries and failure contracts;
- lesson, scene, step, learner-state, action, and quality contracts;
- milestone order, acceptance gates, tests, and resource constraints;
- safe fallback and uncertainty behaviour.

No implementation begins beyond setup scaffolding until these contracts pass consistency review.
