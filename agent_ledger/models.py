from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CallRecord:
    id: int
    agent_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    workflow: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass
class CostReport:
    group_key: str
    call_count: int
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    rows: list[CallRecord] = field(default_factory=list)
