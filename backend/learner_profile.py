from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


CORE_CONCEPTS = [
    "entry_point_discovery",
    "api_routing",
    "domain_modeling",
    "data_lineage",
    "architectural_invariants",
    "error_handling",
    "separation_of_concerns",
]


class ConceptEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository_id: str
    project_id: str
    task_id: str
    concept: str
    is_successful: bool
    hints_used: int = 0
    attempts_count: int = 1
    tutor_assisted: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class LearnerProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    learner_id: str
    concept_mastery: dict[str, float] = Field(default_factory=lambda: {c: 0.5 for c in CORE_CONCEPTS})
    concept_attempts: dict[str, int] = Field(default_factory=lambda: {c: 0 for c in CORE_CONCEPTS})
    concept_successes: dict[str, int] = Field(default_factory=lambda: {c: 0 for c in CORE_CONCEPTS})
    history_records: list[ConceptEvidenceRecord] = Field(default_factory=list)
    projects_enrolled: list[str] = Field(default_factory=list)
    completed_projects: list[str] = Field(default_factory=list)
    project_history: list[str] = Field(default_factory=list)
    demonstrated_transfers: list[dict[str, Any]] = Field(default_factory=list)  # concepts passed in >= 2 distinct repos
    total_hints_used: int = 0
    tutor_takeovers_count: int = 0
    tutor_takeovers_used: int = 0
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def get_presentation_level(self, concept: str) -> str:
        score = self.concept_mastery.get(concept, 0.5)
        if score >= 0.8:
            return "advanced"
        elif score >= 0.45:
            return "moderate"
        return "substantial_support"

    def record_attempt(
        self,
        repository_id: str,
        project_id: str,
        task_id: str,
        concept: str,
        is_successful: bool,
        hints_used: int = 0,
        attempts_count: int = 1,
        tutor_assisted: bool = False,
    ) -> None:
        rec = ConceptEvidenceRecord(
            repository_id=repository_id,
            project_id=project_id,
            task_id=task_id,
            concept=concept,
            is_successful=is_successful,
            hints_used=hints_used,
            attempts_count=attempts_count,
            tutor_assisted=tutor_assisted,
        )
        self.history_records.append(rec)
        self.total_hints_used += hints_used
        if tutor_assisted:
            self.tutor_takeovers_count += 1
            self.tutor_takeovers_used += 1

        self.concept_attempts[concept] = self.concept_attempts.get(concept, 0) + 1
        if is_successful:
            self.concept_successes[concept] = self.concept_successes.get(concept, 0) + 1

        # Calculate updated concept mastery
        prior = self.concept_mastery.get(concept, 0.5)
        if tutor_assisted:
            # Tutor performed task: slight reduction to ensure learner reviews follow-up
            new_score = max(0.2, prior * 0.85)
        elif is_successful:
            # Reward successful independent work, slightly discount if hints were used
            bonus = 0.2 if hints_used == 0 else 0.1
            new_score = min(1.0, prior + bonus)
        else:
            # Penalize misconception
            new_score = max(0.15, prior - 0.15)

        self.concept_mastery[concept] = round(new_score, 3)

        if repository_id not in self.project_history:
            self.project_history.append(repository_id)

        # Check cross-project transfer
        repos_with_success = [
            r.repository_id for r in self.history_records
            if r.concept == concept and r.is_successful and not r.tutor_assisted
        ]
        unique_repos = list(dict.fromkeys(repos_with_success))
        if len(unique_repos) >= 2 and not any(isinstance(t, dict) and t.get("concept") == concept for t in self.demonstrated_transfers):
            self.demonstrated_transfers.append({
                "concept": concept,
                "source_repo": unique_repos[0],
                "target_repo": unique_repos[-1],
                "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()


class LearnerProfileStore:
    """Manages persistent SQLite storage of cross-project learner profiles."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
            CREATE TABLE IF NOT EXISTS learner_profiles (
                learner_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

    def get_profile(self, learner_id: str) -> LearnerProfile:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("SELECT payload FROM learner_profiles WHERE learner_id=?", (learner_id,)).fetchone()
            if row:
                try:
                    return LearnerProfile.model_validate_json(row[0])
                except Exception:
                    pass
        # Return initialized fresh profile
        prof = LearnerProfile(learner_id=learner_id)
        self.save_profile(prof)
        return prof

    def get_or_create_profile(self, learner_id: str) -> LearnerProfile:
        return self.get_profile(learner_id)

    def save_profile(self, profile: LearnerProfile) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO learner_profiles VALUES (?, ?, ?)",
                (profile.learner_id, profile.model_dump_json(), profile.updated_at),
            )
