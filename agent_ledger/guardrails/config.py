from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class GuardrailConfig:
    """Configuration des guardrails pour une session ou un agent."""

    max_calls_per_session: int = 20
    similar_text_threshold: float = 0.85
    similar_repeat_count: int = 3
    prompt_history_size: int = 4
    budget_limit_usd: float | None = None
    budget_scope: Literal["session", "agent", "workflow"] = "session"
    drift_warning_threshold: float = 0.55
    block_on_drift: bool = False
    estimated_calls_if_unbounded: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.estimated_calls_if_unbounded <= 0:
            self.estimated_calls_if_unbounded = self.max_calls_per_session * 2
