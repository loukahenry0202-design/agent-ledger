from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_ledger.db import sqlite_connection
from agent_ledger.models import CallRecord, CostReport

GroupBy = Literal["agent", "model", "workflow", "day"]


class Storage:
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
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    workflow TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calls_agent ON calls(agent_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calls_created ON calls(created_at)"
            )

    def insert(
        self,
        *,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        workflow: str | None,
        metadata: dict[str, Any],
        created_at: datetime | None = None,
    ) -> int:
        ts = (created_at or datetime.now(timezone.utc)).isoformat()
        with sqlite_connection(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO calls (
                    agent_id, model, input_tokens, output_tokens,
                    cost_usd, workflow, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    model,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    workflow,
                    json.dumps(metadata, ensure_ascii=False),
                    ts,
                ),
            )
            return int(cur.lastrowid)

    def _row_to_record(self, row) -> CallRecord:
        return CallRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cost_usd=row["cost_usd"],
            workflow=row["workflow"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_recent(self, limit: int = 50) -> list[CallRecord]:
        with sqlite_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM calls ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def report(self, group_by: GroupBy = "agent") -> list[CostReport]:
        key_sql = {
            "agent": "agent_id",
            "model": "model",
            "workflow": "COALESCE(workflow, '—')",
            "day": "date(created_at)",
        }[group_by]

        with sqlite_connection(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {key_sql} AS group_key,
                    COUNT(*) AS call_count,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(cost_usd) AS total_cost_usd
                FROM calls
                GROUP BY group_key
                ORDER BY total_cost_usd DESC
                """
            ).fetchall()

        return [
            CostReport(
                group_key=row["group_key"],
                call_count=row["call_count"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                total_cost_usd=round(row["total_cost_usd"], 6),
            )
            for row in rows
        ]

    def total_spend(self) -> float:
        with sqlite_connection(self.db_path) as conn:
            row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM calls").fetchone()
        return float(row[0])
