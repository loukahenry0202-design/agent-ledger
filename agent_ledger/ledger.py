from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_ledger.context import current_agent, current_workflow
from agent_ledger.models import CallRecord, CostReport
from agent_ledger.pricing import compute_cost_usd
from agent_ledger.storage import GroupBy, Storage

DEFAULT_DB = Path.home() / ".agent_ledger" / "ledger.db"


class Ledger:
    """Point d'entrée singleton pour enregistrer et consulter les coûts."""

    _instance: Ledger | None = None

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = db_path or os.environ.get("AGENT_LEDGER_DB", DEFAULT_DB)
        self.storage = Storage(path)

    @classmethod
    def get(cls, db_path: str | Path | None = None) -> Ledger:
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def record(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: str | None = None,
        workflow: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CallRecord:
        agent = agent_id or current_agent()
        flow = workflow if workflow is not None else current_workflow()
        cost = compute_cost_usd(model, input_tokens, output_tokens)
        row_id = self.storage.insert(
            agent_id=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            workflow=flow,
            metadata=metadata or {},
        )
        return CallRecord(
            id=row_id,
            agent_id=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            workflow=flow,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )

    def report(self, group_by: GroupBy = "agent") -> list[CostReport]:
        return self.storage.report(group_by=group_by)

    def total_spend(self) -> float:
        return self.storage.total_spend()

    def recent(self, limit: int = 20) -> list[CallRecord]:
        return self.storage.list_recent(limit=limit)
