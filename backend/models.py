from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "pkm-1.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    INVALID = "invalid"


class AssertionStatus(str, Enum):
    VERIFIED_STATIC = "verified_static"
    VERIFIED_DECLARED = "verified_declared"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    UNSUPPORTED = "unsupported"


class ClaimLevel(str, Enum):
    DIRECT_DECLARATION = "direct_declaration"
    RESOLVED_STATIC = "resolved_static"
    CANDIDATE_STATIC = "candidate_static"
    RUNTIME_OBSERVED = "runtime_observed"
    UNRESOLVED = "unresolved"


class Repository(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    repository_id: str
    name: str
    source_kind: str = "local_directory"
    root_label: str
    created_at: datetime = Field(default_factory=utc_now)
    latest_published_revision_id: str | None = None
    isolation_key: str


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str
    repository_id: str
    pkm_revision_id: str
    path: str
    content_hash: str
    language: str
    size_bytes: int = Field(ge=0)
    analysis_status: str = "analysed"
    unsupported_reason: str | None = None
    line_count: int = Field(ge=0, default=0)


class Symbol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol_id: str
    repository_id: str
    pkm_revision_id: str
    file_id: str
    kind: str
    qualified_name: str
    name: str
    signature: str | None = None
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    language_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("line_end")
    @classmethod
    def line_end_not_before_start(cls, value: int, info: Any) -> int:
        if "line_start" in info.data and value < info.data["line_start"]:
            raise ValueError("line_end must be >= line_start")
        return value


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    repository_id: str
    pkm_revision_id: str
    file_id: str | None = None
    source_path: str
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    excerpt: str | None = None
    evidence_type: str
    extraction_method: str
    verification_method: str
    verification_status: VerificationStatus
    parser_version: str | None = None
    content_hash: str | None = None


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str
    repository_id: str
    pkm_revision_id: str
    fact_type: str
    subject_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    assertion_status: AssertionStatus
    evidence_ids: list[str] = Field(default_factory=list)
    extraction_method: str
    extractor_version: str


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationship_id: str
    repository_id: str
    pkm_revision_id: str
    source_id: str
    target_id: str
    relationship_type: str
    status: str
    claim_level: ClaimLevel
    evidence_ids: list[str] = Field(default_factory=list)
    verification_method: str
    verification_status: VerificationStatus
    confidence: float | None = Field(default=None, ge=0, le=1)
    unresolved_reason: str | None = None
    created_by: str


class PkmRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pkm_revision_id: str
    repository_id: str
    parent_revision_id: str | None = None
    source_snapshot_id: str
    analysis_run_id: str
    status: Status
    parser_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    validation_summary: dict[str, int] = Field(default_factory=lambda: {"errors": 0, "warnings": 0})


class PkmSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = SCHEMA_VERSION
    revision: PkmRevision
    repositories: list[Repository] = Field(default_factory=list)
    files: list[SourceFile] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    @property
    def repository_id(self) -> str:
        return self.revision.repository_id


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    trace_id: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
