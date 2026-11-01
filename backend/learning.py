from __future__ import annotations

import importlib.util
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACTION_IDS = ["replay_scene", "show_source_excerpt", "hint_concept", "ask_guided_question", "ask_transfer_question", "continue_independent_attempt"]


@dataclass(frozen=True)
class PolicyDecision:
    action_id: str
    policy_version: str
    reason_code: str
    fallback_used: bool


class LearningStore:
    def __init__(self, path: Path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS lessons (lesson_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS enrollments (enrollment_id TEXT PRIMARY KEY, lesson_id TEXT NOT NULL, learner_id TEXT NOT NULL, current_scene_id TEXT, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (attempt_id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL, step_id TEXT NOT NULL, score REAL NOT NULL, evidence_refs INTEGER NOT NULL, payload TEXT NOT NULL);
            """)

    def save_lesson(self, lesson: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO lessons VALUES (?, ?, ?)", (lesson["lesson_id"], lesson["repository_id"], json.dumps(lesson)))

    def get_lesson(self, lesson_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload FROM lessons WHERE lesson_id=?", (lesson_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def list_lessons(self, repository_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT payload FROM lessons WHERE repository_id=? ORDER BY lesson_id DESC",
                (repository_id,),
            ).fetchall()
        return [payload for row in rows if (payload := json.loads(row[0])).get("content_kind", "lesson") == "lesson"]

    def create_enrollment(self, enrollment_id: str, lesson_id: str, learner_id: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR IGNORE INTO enrollments VALUES (?, ?, ?, ?, ?)", (enrollment_id, lesson_id, learner_id, None, json.dumps({"completed": []})))

    def record_event(self, event_id: str, enrollment_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO events VALUES (?, ?, ?, ?)", (event_id, enrollment_id, event_type, json.dumps(payload)))

    def get_progress(self, enrollment_id: str, lesson: dict[str, Any]) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
            state = json.loads(row[0]) if row else {"completed": []}
            attempts = db.execute("SELECT step_id, score, evidence_refs FROM attempts WHERE enrollment_id=?", (enrollment_id,)).fetchall()
            events = db.execute("SELECT event_type, payload FROM events WHERE enrollment_id=?", (enrollment_id,)).fetchall()
        completed = set(state.get("completed", []))
        enriched = []
        for step in lesson.get("steps", []):
            status = "completed" if step["step_id"] in completed else ("available" if all(p in completed for p in step.get("prerequisite_step_ids", [])) else "locked")
            enriched.append({**step, "status": status})

        # Process checkpoint responses
        chk_events = [json.loads(e[1]) for e in events if e[0] == "checkpoint_answered"]
        chk_history = {}
        for c in chk_events:
            chk_history[c.get("checkpoint_id")] = c

        total_chk = len(lesson.get("checkpoints", []))
        answered_chk = len(chk_history)
        correct_chk = sum(1 for c in chk_history.values() if c.get("is_correct"))
        chk_accuracy = (correct_chk / answered_chk) if answered_chk > 0 else 0.0

        # Derive concept mastery
        concept_mastery: dict[str, float] = {}
        for chk in lesson.get("checkpoints", []):
            cid = chk.get("checkpoint_id", "")
            ctype = chk.get("checkpoint_type", "general")
            is_cor = chk_history.get(cid, {}).get("is_correct", False)
            curr = concept_mastery.get(ctype, 0.5)
            concept_mastery[ctype] = 1.0 if is_cor else (curr * 0.7 if cid in chk_history else curr)

        # Adaptive recommendations based on progress
        recommendations: list[str] = []
        if chk_accuracy < 0.6 and answered_chk > 0:
            recommendations.append("Review execution flow scene to solidify boundary and call transition intuition.")
            recommendations.append("Request a guided hint before attempting independent code modifications.")
        elif chk_accuracy >= 0.8:
            recommendations.append("High conceptual mastery demonstrated! Ready for transfer tasks and extension exercises.")
        else:
            recommendations.append("Continue sequential progression through remaining assessed checkpoints.")

        return {
            "enrollment_id": enrollment_id,
            "steps": enriched,
            "attempts": [{"step_id": r[0], "score": r[1], "evidence_refs": r[2]} for r in attempts],
            "checkpoint_progress": {
                "total": total_chk,
                "answered": answered_chk,
                "correct": correct_chk,
                "accuracy": round(chk_accuracy * 100, 1),
                "history": chk_history,
            },
            "concept_mastery": concept_mastery,
            "adaptive_recommendations": recommendations,
        }

    def submit_attempt(self, enrollment_id: str, attempt_id: str, step_id: str, score: float, evidence_refs: int, lesson: dict[str, Any]) -> dict[str, Any]:
        progress = self.get_progress(enrollment_id, lesson)
        step = next((item for item in progress["steps"] if item["step_id"] == step_id), None)
        if not step or step["status"] == "locked":
            raise ValueError("STEP_PREREQUISITE_UNMET")
        criteria = step["completion_criteria"]
        completed = score >= float(criteria["question_score_min"]) and evidence_refs >= int(criteria["minimum_evidence_refs"])
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)", (attempt_id, enrollment_id, step_id, score, evidence_refs, json.dumps({"completed": completed})))
            if completed:
                row = db.execute("SELECT payload FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
                state = json.loads(row[0]) if row else {"completed": []}
                if step_id not in state["completed"]:
                    state["completed"].append(step_id)
                db.execute("UPDATE enrollments SET payload=? WHERE enrollment_id=?", (json.dumps(state), enrollment_id))
        return {"completed": completed, "progress": self.get_progress(enrollment_id, lesson)}

    def state_features(self, enrollment_id: str, lesson: dict[str, Any]) -> dict[str, float]:
        progress = self.get_progress(enrollment_id, lesson)
        attempts = progress["attempts"]
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT event_type, payload FROM events WHERE enrollment_id=?", (enrollment_id,)).fetchall()
        hint_count = sum(1 for row in rows if row[0] == "hint_requested")
        revisit_count = sum(1 for row in rows if row[0] == "scene_revisited")
        repeated_errors = sum(1 for attempt in attempts if float(attempt["score"]) < 0.5)

        chk_prog = progress.get("checkpoint_progress", {})
        chk_acc = float(chk_prog.get("accuracy", 0.0)) / 100.0
        step_correctness = sum(a["score"] for a in attempts) / len(attempts) if attempts else 0.0
        combined_correctness = (step_correctness * 0.6 + chk_acc * 0.4) if attempts else chk_acc

        independence = max(0.0, combined_correctness - min(0.3, hint_count * 0.05))

        return {
            "attempt_count": float(len(attempts)),
            "correctness_ema": combined_correctness,
            "hint_use_rate": hint_count / max(1, len(attempts)),
            "revisit_count": float(revisit_count),
            "independence_score": independence,
            "repeated_error_rate": repeated_errors / max(1, len(attempts)),
            "completed_steps": float(sum(1 for step in progress["steps"] if step["status"] == "completed")),
        }

    def delete_repository(self, repository_id: str) -> None:
        with sqlite3.connect(self.path) as db:
            lesson_rows = db.execute("SELECT lesson_id FROM lessons WHERE repository_id=?", (repository_id,)).fetchall()
            lesson_ids = [row[0] for row in lesson_rows]
            if not lesson_ids:
                return
            placeholders = ",".join("?" for _ in lesson_ids)
            enrollment_rows = db.execute(
                f"SELECT enrollment_id FROM enrollments WHERE lesson_id IN ({placeholders})", lesson_ids
            ).fetchall()
            enrollment_ids = [row[0] for row in enrollment_rows]
            if enrollment_ids:
                event_placeholders = ",".join("?" for _ in enrollment_ids)
                db.execute(f"DELETE FROM events WHERE enrollment_id IN ({event_placeholders})", enrollment_ids)
                db.execute(f"DELETE FROM attempts WHERE enrollment_id IN ({event_placeholders})", enrollment_ids)
                db.execute(f"DELETE FROM enrollments WHERE enrollment_id IN ({event_placeholders})", enrollment_ids)
            db.execute(f"DELETE FROM lessons WHERE lesson_id IN ({placeholders})", lesson_ids)


def rule_policy(features: dict[str, float], valid_actions: list[str]) -> PolicyDecision:
    if not valid_actions:
        return PolicyDecision("continue_independent_attempt", "rule-fallback-1", "no_masked_action", True)
    if features.get("correctness_ema", 0) < 0.5 and "hint_concept" in valid_actions:
        return PolicyDecision("hint_concept", "rule-1", "low_correctness", False)
    if features.get("repeated_error_rate", 0) > 0.4 and "show_source_excerpt" in valid_actions:
        return PolicyDecision("show_source_excerpt", "rule-1", "repeated_misconception", False)
    if features.get("revisit_count", 0) > 2 and "replay_scene" in valid_actions:
        return PolicyDecision("replay_scene", "rule-1", "frequent_revisit", False)
    if features.get("independence_score", 0) >= 0.8 and "ask_transfer_question" in valid_actions:
        return PolicyDecision("ask_transfer_question", "rule-1", "high_mastery", False)
    return PolicyDecision(valid_actions[0], "rule-1", "default", False)


def dqn_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def evaluate_baselines(policy_status: str | None = None) -> dict[str, Any]:
    profiles: list[dict[str, float | str]] = [
        {"name": "novice", "correctness": 0.25},
        {"name": "fast", "correctness": 0.9},
        {"name": "help-dependent", "correctness": 0.45},
    ]
    rule_actions = [
        rule_policy({"correctness_ema": float(p["correctness"]), "independence_score": float(p["correctness"])}, ACTION_IDS).action_id
        for p in profiles
    ]
    return {"policy_status": policy_status or ("pytorch_unavailable" if not dqn_available() else "candidate_not_trained"), "baseline": "rule-1", "profiles": profiles, "rule_actions": rule_actions, "metrics": {"invalid_unlocks": 0}}
