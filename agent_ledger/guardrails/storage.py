from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_ledger.db import sqlite_connection
from agent_ledger.models import GuardrailStopRecord, GuardrailSummary


class GuardrailStorage:
    """Persistance SQLite des guardrails (tables dédiées)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def close(self) -> None:
        """Compatibilité lifecycle — connexions fermées par opération."""

    def _init_db(self) -> None:
        with sqlite_connection(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_objectives (
                    workflow TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guardrail_stops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    workflow TEXT,
                    session_id TEXT,
                    reason TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    calls_at_stop INTEGER NOT NULL,
                    cost_at_stop REAL NOT NULL,
                    budget_limit REAL,
                    drift_score REAL,
                    estimated_saved_usd REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guardrail_drift_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    workflow TEXT,
                    session_id TEXT,
                    drift_score REAL NOT NULL,
                    output_sample TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stops_agent ON guardrail_stops(agent_id)"
            )

    def set_workflow_objective(self, workflow: str, objective: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with sqlite_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO workflow_objectives (workflow, objective, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(workflow) DO UPDATE SET
                    objective = excluded.objective,
                    updated_at = excluded.updated_at
                """,
                (workflow, objective, ts),
            )

    def get_workflow_objective(self, workflow: str) -> str | None:
        with sqlite_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT objective FROM workflow_objectives WHERE workflow = ?",
                (workflow,),
            ).fetchone()
        return row["objective"] if row else None

    def session_cost(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str | None,
        scope: str,
    ) -> float:
        with sqlite_connection(self.db_path) as conn:
            if scope == "session" and session_id:
                row = conn.execute(
                    """
                    SELECT COALESCE(SUM(cost_usd), 0) FROM calls
                    WHERE agent_id = ?
                      AND COALESCE(workflow, '') = COALESCE(?, '')
                      AND json_extract(metadata, '$.session_id') = ?
                    """,
                    (agent_id, workflow, session_id),
                ).fetchone()
            elif scope == "agent":
                row = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE agent_id = ?",
                    (agent_id,),
                ).fetchone()
            elif scope == "workflow" and workflow:
                row = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE workflow = ?",
                    (workflow,),
                ).fetchone()
            else:
                return 0.0
        return float(row[0])

    def session_call_count(
        self, *, agent_id: str, workflow: str | None, session_id: str
    ) -> int:
        with sqlite_connection(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM calls
                WHERE agent_id = ?
                  AND COALESCE(workflow, '') = COALESCE(?, '')
                  AND json_extract(metadata, '$.session_id') = ?
                """,
                (agent_id, workflow, session_id),
            ).fetchone()
        return int(row[0])

    def insert_stop(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str | None,
        reason: str,
        detail: str,
        calls_at_stop: int,
        cost_at_stop: float,
        budget_limit: float | None,
        drift_score: float | None,
        estimated_saved_usd: float,
    ) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        with sqlite_connection(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO guardrail_stops (
                    agent_id, workflow, session_id, reason, detail,
                    calls_at_stop, cost_at_stop, budget_limit, drift_score,
                    estimated_saved_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    workflow,
                    session_id,
                    reason,
                    detail,
                    calls_at_stop,
                    cost_at_stop,
                    budget_limit,
                    drift_score,
                    estimated_saved_usd,
                    ts,
                ),
            )
            return int(cur.lastrowid)

    def log_drift(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str | None,
        drift_score: float,
        output_sample: str,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with sqlite_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO guardrail_drift_logs (
                    agent_id, workflow, session_id, drift_score, output_sample, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (agent_id, workflow, session_id, drift_score, output_sample[:500], ts),
            )

    def list_stops(self, limit: int = 100) -> list[GuardrailStopRecord]:
        with sqlite_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM guardrail_stops ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_stop(r) for r in rows]

    def summary(self) -> GuardrailSummary:
        with sqlite_connection(self.db_path) as conn:
            stops = conn.execute("SELECT COUNT(*) FROM guardrail_stops").fetchone()[0]
            saved = conn.execute(
                "SELECT COALESCE(SUM(estimated_saved_usd), 0) FROM guardrail_stops"
            ).fetchone()[0]
            avg_drift = conn.execute(
                "SELECT COALESCE(AVG(drift_score), 0) FROM guardrail_drift_logs"
            ).fetchone()[0]
            stop_avg_drift = conn.execute(
                "SELECT COALESCE(AVG(drift_score), 0) FROM guardrail_stops WHERE drift_score IS NOT NULL"
            ).fetchone()[0]
            by_reason = conn.execute(
                """
                SELECT reason, COUNT(*) AS cnt
                FROM guardrail_stops
                GROUP BY reason
                ORDER BY cnt DESC
                """
            ).fetchall()
            stop_rows = conn.execute(
                "SELECT * FROM guardrail_stops ORDER BY id DESC LIMIT ?",
                (50,),
            ).fetchall()
        drift_values = [avg_drift, stop_avg_drift]
        non_zero = [d for d in drift_values if d]
        mean_drift = sum(non_zero) / len(non_zero) if non_zero else 0.0
        return GuardrailSummary(
            stopped_workflows=int(stops),
            stop_reasons={row["reason"]: row["cnt"] for row in by_reason},
            average_drift_score=round(mean_drift, 4),
            estimated_saved_usd=round(float(saved), 6),
            stops=[self._row_to_stop(r) for r in stop_rows],
        )

    def _row_to_stop(self, row) -> GuardrailStopRecord:
        return GuardrailStopRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            workflow=row["workflow"],
            session_id=row["session_id"],
            reason=row["reason"],
            detail=row["detail"],
            calls_at_stop=row["calls_at_stop"],
            cost_at_stop=row["cost_at_stop"],
            budget_limit=row["budget_limit"],
            drift_score=row["drift_score"],
            estimated_saved_usd=row["estimated_saved_usd"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
