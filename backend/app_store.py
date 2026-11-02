from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AppStore:
    """Application-level persistence for jobs, repository metadata, conversations and videos."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _initialise(self) -> None:
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS repository_metadata (
                    repository_id TEXT PRIMARY KEY,
                    source_url TEXT,
                    source_path TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    languages_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    message_id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    lesson_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    path TEXT,
                    manifest_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_conversations_repo ON conversations(repository_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_videos_repo ON videos(repository_id, created_at);
                """
            )

    def upsert_repository(self, repository_id: str, source_path: str, *, source_url: str | None = None,
                          description: str = "", languages: list[str] | None = None,
                          status: str = "ready", last_error: str | None = None) -> None:
        now = _now()
        with sqlite3.connect(self.path) as db:
            db.execute(
                """INSERT INTO repository_metadata
                (repository_id, source_url, source_path, description, languages_json, status, created_at, updated_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                  source_url=COALESCE(excluded.source_url, repository_metadata.source_url), source_path=excluded.source_path,
                  description=CASE WHEN excluded.description = '' THEN repository_metadata.description ELSE excluded.description END,
                  languages_json=CASE WHEN excluded.languages_json = '[]' THEN repository_metadata.languages_json ELSE excluded.languages_json END,
                  status=excluded.status, updated_at=excluded.updated_at, last_error=excluded.last_error""",
                (repository_id, source_url, source_path, description, json.dumps(languages or []), status, now, now, last_error),
            )

    def list_repositories(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT * FROM repository_metadata ORDER BY updated_at DESC").fetchall()
        return [self._repository_row(row) for row in rows]

    def get_repository(self, repository_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT * FROM repository_metadata WHERE repository_id=?", (repository_id,)).fetchone()
        return self._repository_row(row) if row else None

    @staticmethod
    def _repository_row(row: tuple[Any, ...]) -> dict[str, Any]:
        return {"repository_id": row[0], "source_url": row[1], "source_path": row[2], "description": row[3],
                "languages": json.loads(row[4]), "status": row[5], "created_at": row[6], "updated_at": row[7],
                "last_error": row[8]}

    def delete_repository_metadata(self, repository_id: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM repository_metadata WHERE repository_id=?", (repository_id,))
            db.execute("DELETE FROM conversations WHERE repository_id=?", (repository_id,))
            db.execute("DELETE FROM videos WHERE repository_id=?", (repository_id,))

    def create_job(self, job_id: str, kind: str, payload: dict[str, Any]) -> None:
        now = _now()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO jobs VALUES (?, ?, 'queued', 0, 'queued', 'Waiting to start', ?, NULL, NULL, ?, ?, 0)",
                       (job_id, kind, json.dumps(payload), now, now))

    def update_job(self, job_id: str, *, status: str | None = None, progress: float | None = None,
                   stage: str | None = None, message: str | None = None,
                   result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        fields: list[str] = []
        values: list[Any] = []
        for name, value in (("status", status), ("progress", progress), ("stage", stage), ("message", message)):
            if value is not None:
                fields.append(f"{name}=?")
                values.append(value)
        if result is not None:
            fields.append("result_json=?")
            values.append(json.dumps(result))
        if error is not None:
            fields.append("error_json=?")
            values.append(json.dumps(error))
        fields.append("updated_at=?")
        values.append(_now())
        values.append(job_id)
        with sqlite3.connect(self.path) as db:
            db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id=?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        return {"job_id": row[0], "kind": row[1], "status": row[2], "progress": row[3], "stage": row[4],
                "message": row[5], "payload": json.loads(row[6]), "result": json.loads(row[7]) if row[7] else None,
                "error": json.loads(row[8]) if row[8] else None, "created_at": row[9], "updated_at": row[10],
                "cancel_requested": bool(row[11])}

    def request_cancel(self, job_id: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE jobs SET cancel_requested=1, updated_at=? WHERE job_id=?", (_now(), job_id))

    def is_cancel_requested(self, job_id: str) -> bool:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    def add_message(self, message_id: str, repository_id: str, role: str, content: str,
                    citations: list[dict[str, Any]] | None = None, lesson_id: str | None = None) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (message_id, repository_id, lesson_id, role, content, json.dumps(citations or []), _now()))

    def list_messages(self, repository_id: str, lesson_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM conversations WHERE repository_id=?"
        params: list[Any] = [repository_id]
        if lesson_id:
            query += " AND lesson_id=?"
            params.append(lesson_id)
        query += " ORDER BY created_at"
        with sqlite3.connect(self.path) as db:
            rows = db.execute(query, params).fetchall()
        return [{"message_id": row[0], "repository_id": row[1], "lesson_id": row[2], "role": row[3],
                 "content": row[4], "citations": json.loads(row[5]), "created_at": row[6]} for row in rows]

    def upsert_video(self, video_id: str, lesson_id: str, repository_id: str, title: str, topic: str,
                     status: str, path: str | None, manifest: dict[str, Any]) -> None:
        now = _now()
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET status=excluded.status, path=excluded.path,
                manifest_json=excluded.manifest_json, updated_at=excluded.updated_at""",
                       (video_id, lesson_id, repository_id, title, topic, status, path, json.dumps(manifest), now, now))

    def save_video(self, data: dict[str, Any]) -> None:
        self.upsert_video(
            video_id=data["video_id"],
            lesson_id=data.get("lesson_id", ""),
            repository_id=data.get("repository_id", ""),
            title=data.get("title", ""),
            topic=data.get("topic", ""),
            status=data.get("status", "playable"),
            path=data.get("path") or (data.get("manifest", {}).get("video_path")),
            manifest=data.get("manifest", {}),
        )

    def list_videos(self, repository_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM videos"
        params: list[Any] = []
        if repository_id:
            query += " WHERE repository_id=?"
            params.append(repository_id)
        query += " ORDER BY updated_at DESC"
        with sqlite3.connect(self.path) as db:
            rows = db.execute(query, params).fetchall()
        return [self._video_row(row) for row in rows]

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
        return self._video_row(row) if row else None

    @staticmethod
    def _video_row(row: tuple[Any, ...]) -> dict[str, Any]:
        return {"video_id": row[0], "lesson_id": row[1], "repository_id": row[2], "title": row[3],
                "topic": row[4], "status": row[5], "path": row[6], "manifest": json.loads(row[7]),
                "created_at": row[8], "updated_at": row[9]}
