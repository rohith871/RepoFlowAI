# RepoFlow AI — Data Contracts

**Status:** Phase 1 contract baseline — 24 October 2026  
**Format:** JSON-compatible objects, represented by Pydantic models in the implementation.

## 1. Contract rules

- Every top-level object includes `schema_version` and stable IDs.
- IDs are opaque typed strings such as `repo_`, `file_`, `fact_`, `evidence_`, `rel_`, `lesson_`, `scene_`, `step_`, and `attempt_`.
- IDs are stable within a repository lineage. Re-analysis preserves IDs when identity and source anchor are unchanged; changed facts receive a new revision record.
- Project-specific objects always include `repository_id` and, when relevant, `pkm_revision_id`.
- Timestamps are ISO-8601 UTC; durations are integer milliseconds.
- Unknown is explicit (`unknown`, `unresolved`, `ambiguous`, or `unsupported`), never invented prose.
- Enumerations are closed in validators; new values require a schema version or compatible extension.

## 2. Core PKM entities

### Repository and source snapshot

```json
{
  "schema_version": "pkm-1.0",
  "repository_id": "repo_123",
  "name": "example-service",
  "source_kind": "local_directory",
  "root_label": "example-service",
  "default_branch": "unknown",
  "created_at": "2026-10-24T00:00:00Z",
  "latest_published_revision_id": "pkmrev_7",
  "isolation_key": "repo_123"
}
```

```json
{
  "pkm_revision_id": "pkmrev_7",
  "repository_id": "repo_123",
  "parent_revision_id": "pkmrev_6",
  "source_snapshot_id": "snap_7",
  "analysis_run_id": "run_7",
  "status": "published",
  "parser_versions": {"python-ast": "3.13", "framework-adapter": "0.1.0"},
  "created_at": "2026-10-24T00:00:00Z",
  "validation_summary": {"errors": 0, "warnings": 3}
}
```

### Directory

```json
{
  "directory_id": "dir_src_api",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "path": "src/api",
  "parent_directory_id": "dir_src",
  "child_file_ids": ["file_abc"],
  "child_directory_ids": [],
  "content_hash": "sha256:..."
}
```

A repository is the project boundary for Phase 1. Directory, file, module, symbol, and fact records must all resolve to that repository.

### File and symbol

```json
{
  "file_id": "file_abc",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "path": "src/api/routes.py",
  "content_hash": "sha256:...",
  "language": "python",
  "size_bytes": 4210,
  "analysis_status": "analysed",
  "unsupported_reason": null
}
```

```json
{
  "symbol_id": "sym_route_users",
  "repository_id": "repo_123",
  "file_id": "file_abc",
  "kind": "function",
  "qualified_name": "src.api.routes.list_users",
  "name": "list_users",
  "signature": "list_users(request) -> Response",
  "line_start": 18,
  "line_end": 34,
  "visibility": "module",
  "language_metadata": {"decorators": ["get('/users')"]}
}
```

Symbols cover modules, classes, functions, methods, relevant variables, routes, schemas, models, migrations, entry points, configuration entries, and integrations when an analyzer supports them.

Initial fact categories include `module`, `import`, `dependency`, `api_route`, `request_schema`, `response_schema`, `middleware`, `database_model`, `model_relationship`, `query`, `migration`, `configuration`, `external_integration`, and `execution_entry_point`. Unsupported categories are recorded as capability gaps rather than silently omitted.

### Fact

```json
{
  "fact_id": "fact_route_users",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "fact_type": "api_route",
  "subject_id": "sym_route_users",
  "attributes": {
    "http_method": "GET",
    "path": "/users",
    "request_schema_id": null,
    "response_schema_id": "sym_user_list"
  },
  "assertion_status": "verified_static",
  "evidence_ids": ["evidence_44"],
  "extraction_method": "python_ast+framework_adapter",
  "extractor_version": "0.1.0"
}
```

Fact `assertion_status` values: `verified_static`, `verified_declared`, `inferred`, `unresolved`, `unsupported`. A fact never claims runtime execution unless runtime evidence is separately provided and verified.

## 3. Source evidence

```json
{
  "evidence_id": "evidence_44",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "file_id": "file_abc",
  "source_path": "src/api/routes.py",
  "line_start": 18,
  "line_end": 19,
  "excerpt": "@router.get('/users')\\ndef list_users(...):",
  "evidence_type": "source_declaration",
  "extraction_method": "python_ast",
  "verification_method": "parser_location",
  "verification_status": "verified",
  "parser_version": "3.13",
  "content_hash": "sha256:..."
}
```

Long excerpts are bounded and redacted for secrets. A reference can point to a source range without storing the full excerpt. Line ranges are checked against the immutable snapshot.

## 4. Relationships

```json
{
  "relationship_id": "rel_calls_91",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "source_id": "sym_route_users",
  "target_id": "sym_user_service",
  "relationship_type": "calls",
  "status": "ambiguous",
  "claim_level": "candidate_static",
  "evidence_ids": ["evidence_44", "evidence_51"],
  "verification_method": "name_resolution+import_graph",
  "verification_status": "partially_verified",
  "confidence": 0.72,
  "unresolved_reason": "dynamic dependency injection may select another implementation",
  "created_by": "python-ast+resolver@0.1.0"
}
```

Required relationship types initially include `imports`, `depends_on`, `calls`, `routes_to`, `uses_schema`, `uses_service`, `service_reads`, `service_writes`, `model_relates_to`, `query_reads`, `query_writes`, `migration_changes`, and `entry_point_reaches`.

Allowed claim levels are `direct_declaration`, `resolved_static`, `candidate_static`, `runtime_observed`, and `unresolved`. Static evidence alone cannot use `runtime_observed`.

## 5. Retrieval and reasoning contracts

```json
{
  "retrieval_request": {
    "repository_id": "repo_123",
    "pkm_revision_id": "pkmrev_7",
    "query": "How does a GET /users request reach the database?",
    "modes": ["exact", "structured", "graph", "semantic"],
    "max_items": 30,
    "include_unresolved": true
  },
  "retrieval_result": {
    "result_id": "retr_1",
    "items": [
      {"item_id": "fact_route_users", "kind": "fact", "rank": 1, "evidence_ids": ["evidence_44"]},
      {"item_id": "rel_calls_91", "kind": "relationship", "rank": 2, "evidence_ids": ["evidence_44", "evidence_51"]}
    ],
    "unresolved_questions": ["Runtime dependency selection is not established"],
    "truncated": false
  }
}
```

```json
{
  "explanation": {
    "explanation_id": "exp_1",
    "repository_id": "repo_123",
    "pkm_revision_id": "pkmrev_7",
    "answer": "The route is declared in ...",
    "claims": [
      {"text": "...", "classification": "verified_fact", "evidence_ids": ["evidence_44"]},
      {"text": "...", "classification": "inference", "evidence_ids": ["evidence_51"], "confidence": 0.72}
    ],
    "assumptions": [],
    "unresolved_questions": ["..."],
    "validation_status": "valid"
  }
}
```

## 6. Lesson, scene, and step contracts

```json
{
  "lesson_id": "lesson_1",
  "repository_id": "repo_123",
  "pkm_revision_id": "pkmrev_7",
  "goal": "Trace a request from route to persistence",
  "chapters": ["chapter_1"],
  "generation_run_id": "gen_1",
  "validation_status": "validated"
}
```

```json
{
  "scene_id": "scene_3",
  "lesson_id": "lesson_1",
  "chapter_id": "chapter_1",
  "order": 3,
  "learning_objectives": ["Identify the route-to-service handoff"],
  "narration": {"text": "...", "claim_refs": ["fact_route_users", "rel_calls_91"]},
  "visual": {
    "kind": "data_flow",
    "nodes": ["sym_route_users", "sym_user_service"],
    "highlight_ranges": ["evidence_44"],
    "camera_plan": ["wide", "route_zoom", "service_follow"]
  },
  "audio_asset_id": null,
  "caption_asset_id": null,
  "timing": {"duration_ms": null, "source": "pending_audio"},
  "interaction": {"question_ids": ["question_2"], "resume_anchor": "scene_3"},
  "evidence_ids": ["evidence_44", "evidence_51"],
  "validation_status": "draft"
}
```

```json
{
  "step_id": "step_2",
  "lesson_id": "lesson_1",
  "order": 2,
  "prerequisite_step_ids": ["step_1"],
  "objective": "Explain the route-to-service handoff with evidence",
  "required_activities": ["answer_question", "trace_source"],
  "completion_criteria": {
    "all": [
      {"type": "question_score", "minimum": 0.75},
      {"type": "evidence_trace", "minimum_valid_refs": 2}
    ]
  },
  "source_evidence_ids": ["evidence_44", "evidence_51"],
  "scene_ids": ["scene_3"],
  "support_options": ["replay_scene", "hint_1", "show_source_excerpt"],
  "status": "locked"
}
```

## 7. Learner and policy contracts

```json
{
  "learner_state": {
    "learner_id": "learner_1",
    "enrollment_id": "enrol_1",
    "lesson_id": "lesson_1",
    "state_schema_version": "learner-state-1.0",
    "features": {
      "attempt_count": 2,
      "correctness_ema": 0.5,
      "repeated_error_rate": 0.5,
      "hint_use_rate": 0.5,
      "revisit_count": 1,
      "concept_mastery": {"route": 0.7, "service": 0.35},
      "independence_score": 0.4,
      "recency_seconds": 120
    },
    "normalization_version": "norm-1",
    "valid_action_ids": ["replay_scene", "hint_concept", "transfer_question"]
  }
}
```

```json
{
  "policy_decision": {
    "decision_id": "decision_1",
    "policy_version": "rule-fallback-1",
    "state_schema_version": "learner-state-1.0",
    "action_id": "hint_concept",
    "reason_code": "repeated_error",
    "confidence": 0.8,
    "fallback_used": true,
    "masked_action_ids": ["unlock_step_3"]
  }
}
```

The policy cannot emit an unlock action. Only the progression service can produce:

```json
{"step_id":"step_2","decision":"completed","evidence":"attempt_9","next_step_id":"step_3","next_status":"available"}
```

## 8. Errors and validation

```json
{
  "error": {
    "code": "PKM_EVIDENCE_RANGE_INVALID",
    "message": "Evidence line range is outside the captured source snapshot",
    "trace_id": "trace_1",
    "retryable": false,
    "details": {"evidence_id": "evidence_44", "path": "src/api/routes.py"}
  }
}
```

Initial stable error families: `INPUT_UNAUTHORIZED`, `INPUT_TOO_LARGE`, `UNSUPPORTED_LANGUAGE`, `PARSER_FAILED`, `PKM_SCHEMA_INVALID`, `PKM_EVIDENCE_RANGE_INVALID`, `PKM_CROSS_REPOSITORY_REFERENCE`, `RETRIEVAL_EMPTY`, `GENERATION_INVALID`, `MEDIA_TIMING_INVALID`, `PROVIDER_UNAVAILABLE`, `POLICY_INFERENCE_FAILED`, `STEP_PREREQUISITE_UNMET`, and `COMPLETION_CRITERIA_UNMET`.

Validation is blocking for published PKM, validated storyboards, and completion/unlock decisions. Warnings remain visible and are included in evaluation reports.

## 9. Versioning and migration

Schema versions use `name-major.minor`. A major version may break fields or semantics. A minor version may add optional fields or enum values only when readers have a documented default. Every stored artefact records PKM, parser, analyzer, prompt/template, model provider, TTS engine, renderer, policy, and normalization versions.

Migration code is required before reading an older published revision with a newer service. Never silently reinterpret old evidence.
