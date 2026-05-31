from __future__ import annotations


class GuardrailError(Exception):
    """Base des erreurs de guardrails."""


class LoopDetectedError(GuardrailError):
    """Boucle ou répétition anormale détectée."""

    def __init__(
        self,
        message: str,
        *,
        agent_id: str,
        workflow: str | None,
        call_count: int,
        reason: str,
    ) -> None:
        super().__init__(message)
        self.agent_id = agent_id
        self.workflow = workflow
        self.call_count = call_count
        self.reason = reason


class BudgetExceededError(GuardrailError):
    """Budget maximal dépassé."""

    def __init__(
        self,
        message: str,
        *,
        agent_id: str,
        workflow: str | None,
        current_cost_usd: float,
        pending_cost_usd: float,
        limit_usd: float,
    ) -> None:
        super().__init__(message)
        self.agent_id = agent_id
        self.workflow = workflow
        self.current_cost_usd = current_cost_usd
        self.pending_cost_usd = pending_cost_usd
        self.limit_usd = limit_usd


class DriftWarning(Warning):
    """Dérive par rapport à l'objectif du workflow (non bloquant par défaut)."""

    def __init__(
        self,
        message: str,
        *,
        agent_id: str,
        workflow: str | None,
        drift_score: float,
        threshold: float,
    ) -> None:
        super().__init__(message)
        self.agent_id = agent_id
        self.workflow = workflow
        self.drift_score = drift_score
        self.threshold = threshold
