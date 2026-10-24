from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from backend.models import (
    Evidence,
    Fact,
    PkmRevision,
    PkmSnapshot,
    Relationship,
    Repository,
    SourceFile,
    Symbol,
)

ModelT = TypeVar("ModelT")


class PkmStore:
    """SQLite-backed immutable PKM snapshot store."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS repositories (
                    repository_id TEXT PRIMARY KEY, name TEXT NOT NULL, root_label TEXT NOT NULL,
                    source_kind TEXT NOT NULL, created_at TEXT NOT NULL,
                    latest_published_revision_id TEXT, isolation_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    pkm_revision_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    parent_revision_id TEXT, source_snapshot_id TEXT NOT NULL,
                    analysis_run_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id)
                );
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    pkm_revision_id TEXT NOT NULL, path TEXT NOT NULL, content_hash TEXT NOT NULL,
                    language TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(repository_id, pkm_revision_id, path),
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id),
                    FOREIGN KEY(pkm_revision_id) REFERENCES revisions(pkm_revision_id)
                );
                CREATE TABLE IF NOT EXISTS symbols (
                    symbol_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    pkm_revision_id TEXT NOT NULL, file_id TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id),
                    FOREIGN KEY(pkm_revision_id) REFERENCES revisions(pkm_revision_id),
                    FOREIGN KEY(file_id) REFERENCES files(file_id)
                );
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    pkm_revision_id TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id),
                    FOREIGN KEY(pkm_revision_id) REFERENCES revisions(pkm_revision_id)
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    pkm_revision_id TEXT NOT NULL, source_path TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id),
                    FOREIGN KEY(pkm_revision_id) REFERENCES revisions(pkm_revision_id)
                );
                CREATE TABLE IF NOT EXISTS relationships (
                    relationship_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    pkm_revision_id TEXT NOT NULL, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(repository_id) REFERENCES repositories(repository_id),
                    FOREIGN KEY(pkm_revision_id) REFERENCES revisions(pkm_revision_id)
                );
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(repository_id, path);
                CREATE INDEX IF NOT EXISTS idx_evidence_path ON evidence(repository_id, source_path);
                CREATE INDEX IF NOT EXISTS idx_relationship_source ON relationships(repository_id, source_id);
                CREATE INDEX IF NOT EXISTS idx_relationship_target ON relationships(repository_id, target_id);
                """
            )

    def save_snapshot(self, snapshot: PkmSnapshot) -> None:
        repo = snapshot.repositories[0]
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO repositories VALUES (?, ?, ?, ?, ?, ?, ?)",
                (repo.repository_id, repo.name, repo.root_label, repo.source_kind,
                 repo.created_at.isoformat(), None, repo.isolation_key),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (snapshot.revision.pkm_revision_id, snapshot.revision.repository_id,
                 snapshot.revision.parent_revision_id, snapshot.revision.source_snapshot_id,
                 snapshot.revision.analysis_run_id, snapshot.revision.status.value,
                 snapshot.revision.model_dump_json()),
            )
            for file_item in snapshot.files:
                db.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (file_item.file_id, file_item.repository_id, file_item.pkm_revision_id, file_item.path,
                            file_item.content_hash, file_item.language, file_item.model_dump_json()))
            for symbol_item in snapshot.symbols:
                db.execute("INSERT INTO symbols VALUES (?, ?, ?, ?, ?)",
                           (symbol_item.symbol_id, symbol_item.repository_id, symbol_item.pkm_revision_id, symbol_item.file_id,
                            symbol_item.model_dump_json()))
            for fact_item in snapshot.facts:
                db.execute("INSERT INTO facts VALUES (?, ?, ?, ?)",
                           (fact_item.fact_id, fact_item.repository_id, fact_item.pkm_revision_id, fact_item.model_dump_json()))
            for evidence_item in snapshot.evidence:
                db.execute("INSERT INTO evidence VALUES (?, ?, ?, ?, ?)",
                           (evidence_item.evidence_id, evidence_item.repository_id, evidence_item.pkm_revision_id,
                            evidence_item.source_path, evidence_item.model_dump_json()))
            for relationship_item in snapshot.relationships:
                db.execute("INSERT INTO relationships VALUES (?, ?, ?, ?, ?, ?)",
                           (relationship_item.relationship_id, relationship_item.repository_id, relationship_item.pkm_revision_id,
                            relationship_item.source_id, relationship_item.target_id, relationship_item.model_dump_json()))
            db.execute("UPDATE repositories SET latest_published_revision_id=? WHERE repository_id=?",
                       (snapshot.revision.pkm_revision_id, repo.repository_id))

    def get_snapshot(self, repository_id: str, revision_id: str | None = None) -> PkmSnapshot | None:
        with self.connection() as db:
            repo_row = db.execute("SELECT * FROM repositories WHERE repository_id=?", (repository_id,)).fetchone()
            if repo_row is None:
                return None
            revision_id = revision_id or repo_row["latest_published_revision_id"]
            if not revision_id:
                return None
            rev_row = db.execute(
                "SELECT payload FROM revisions WHERE pkm_revision_id=? AND repository_id=?",
                (revision_id, repository_id),
            ).fetchone()
            if rev_row is None:
                return None

            revision = PkmRevision.model_validate_json(rev_row["payload"])

            def load(table: str, model: type[ModelT]) -> list[ModelT]:
                rows = db.execute(
                    f"SELECT payload FROM {table} WHERE repository_id=? AND pkm_revision_id=?",
                    (repository_id, revision_id),
                )
                return [model.model_validate_json(row["payload"]) for row in rows]  # type: ignore[attr-defined]

            repo = Repository(repository_id=repo_row["repository_id"], name=repo_row["name"],
                              root_label=repo_row["root_label"], source_kind=repo_row["source_kind"],
                              created_at=repo_row["created_at"],
                              latest_published_revision_id=revision_id,
                              isolation_key=repo_row["isolation_key"])
            return PkmSnapshot(
                revision=revision,
                repositories=[repo],
                files=load("files", SourceFile),
                symbols=load("symbols", Symbol),
                facts=load("facts", Fact),
                evidence=load("evidence", Evidence),
                relationships=load("relationships", Relationship),
            )

    def list_repositories(self) -> list[Repository]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM repositories ORDER BY created_at DESC").fetchall()
            return [Repository(repository_id=row["repository_id"], name=row["name"],
                               root_label=row["root_label"], source_kind=row["source_kind"],
                               created_at=row["created_at"],
                               latest_published_revision_id=row["latest_published_revision_id"],
                               isolation_key=row["isolation_key"]) for row in rows]

    def export_snapshot(self, snapshot: PkmSnapshot, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
