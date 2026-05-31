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


@dataclass(frozen=True)
class GuardrailStopRecord:
    id: int
    agent_id: str
    workflow: str | None
    session_id: str | None
    reason: str
    detail: str
    calls_at_stop: int
    cost_at_stop: float
    budget_limit: float | None
    drift_score: float | None
    estimated_saved_usd: float
    created_at: datetime


@dataclass
class GuardrailSummary:
    stopped_workflows: int
    stop_reasons: dict[str, int]
    average_drift_score: float
    estimated_saved_usd: float
    stops: list[GuardrailStopRecord] = field(default_factory=list)
