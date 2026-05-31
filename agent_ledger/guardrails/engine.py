from __future__ import annotations

from dataclasses import dataclass, field

from agent_ledger.context import current_agent, current_session_id, current_workflow
from agent_ledger.guardrails.config import GuardrailConfig
from agent_ledger.guardrails.drift import compute_drift_score
from agent_ledger.guardrails.exceptions import (
    BudgetExceededError,
    DriftWarning,
    LoopDetectedError,
)
from agent_ledger.guardrails.similarity import text_similarity
from agent_ledger.guardrails.storage import GuardrailStorage


@dataclass
class _SessionState:
    call_count: int = 0
    recent_prompts: list[str] = field(default_factory=list)
    recent_outputs: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    stopped: bool = False


class AgentGuardrails:
    """Moteur de guardrails : boucles, budget, dérive."""

    def __init__(
        self,
        storage: GuardrailStorage,
        config: GuardrailConfig | None = None,
    ) -> None:
        self._storage = storage
        self._config = config or GuardrailConfig()
        self._sessions: dict[str, _SessionState] = {}

    @classmethod
    def for_db(
        cls,
        db_path: str,
        config: GuardrailConfig | None = None,
    ) -> AgentGuardrails:
        return cls(GuardrailStorage(db_path), config)

    @property
    def config(self) -> GuardrailConfig:
        return self._config

    def set_workflow_objective(self, workflow: str, objective: str) -> None:
        self._storage.set_workflow_objective(workflow, objective)

    def close(self) -> None:
        self._storage.close()

    def _session_key(self, agent_id: str, workflow: str | None, session_id: str) -> str:
        return f"{agent_id}:{workflow or ''}:{session_id}"

    def _state(self, agent_id: str, workflow: str | None, session_id: str) -> _SessionState:
        key = self._session_key(agent_id, workflow, session_id)
        if key not in self._sessions:
            self._sessions[key] = _SessionState()
        return self._sessions[key]

    def validate_before_record(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str,
        cost_usd: float,
        prompt: str | None = None,
        output: str | None = None,
    ) -> float | None:
        """
        Vérifie les guardrails avant enregistrement.
        Retourne le drift_score si calculé, sinon None.
        Lève LoopDetectedError ou BudgetExceededError si stop.
        """
        state = self._state(agent_id, workflow, session_id)
        if state.stopped:
            raise LoopDetectedError(
                f"Agent '{agent_id}' déjà stoppé (workflow '{workflow or '—'}')",
                agent_id=agent_id,
                workflow=workflow,
                call_count=state.call_count,
                reason="already_stopped",
            )

        persisted_calls = self._storage.session_call_count(
            agent_id=agent_id, workflow=workflow, session_id=session_id
        )
        next_call_index = persisted_calls + 1

        if next_call_index > self._config.max_calls_per_session:
            self._stop_loop(
                agent_id=agent_id,
                workflow=workflow,
                session_id=session_id,
                state=state,
                reason="max_calls",
                detail=(
                    f"{next_call_index} appels prévus, limite {self._config.max_calls_per_session}"
                ),
                call_count=next_call_index,
            )

        if prompt:
            self._check_similarity_streak(
                agent_id=agent_id,
                workflow=workflow,
                session_id=session_id,
                state=state,
                text=prompt,
                bucket=state.recent_prompts,
                label="prompt",
                call_count=next_call_index,
            )
        if output:
            self._check_similarity_streak(
                agent_id=agent_id,
                workflow=workflow,
                session_id=session_id,
                state=state,
                text=output,
                bucket=state.recent_outputs,
                label="output",
                call_count=next_call_index,
            )

        if self._config.budget_limit_usd is not None:
            current = self._storage.session_cost(
                agent_id=agent_id,
                workflow=workflow,
                session_id=session_id,
                scope=self._config.budget_scope,
            )
            projected = current + cost_usd
            if projected > self._config.budget_limit_usd:
                self._stop_budget(
                    agent_id=agent_id,
                    workflow=workflow,
                    session_id=session_id,
                    state=state,
                    current_cost=current,
                    pending_cost=cost_usd,
                    call_count=next_call_index,
                )

        drift_score: float | None = None
        if workflow and output:
            objective = self._storage.get_workflow_objective(workflow)
            if objective:
                drift_score = compute_drift_score(objective, output)
                self._storage.log_drift(
                    agent_id=agent_id,
                    workflow=workflow,
                    session_id=session_id,
                    drift_score=drift_score,
                    output_sample=output,
                )
                if drift_score >= self._config.drift_warning_threshold:
                    import warnings

                    warnings.warn(
                        DriftWarning(
                            (
                                f"Dérive détectée pour '{agent_id}' / '{workflow}': "
                                f"score={drift_score:.2f} (seuil {self._config.drift_warning_threshold})"
                            ),
                            agent_id=agent_id,
                            workflow=workflow,
                            drift_score=drift_score,
                            threshold=self._config.drift_warning_threshold,
                        ),
                        stacklevel=3,
                    )
                if self._config.block_on_drift and drift_score >= self._config.drift_warning_threshold:
                    self._stop_loop(
                        agent_id=agent_id,
                        workflow=workflow,
                        session_id=session_id,
                        state=state,
                        reason="drift",
                        detail=f"drift_score={drift_score:.3f}",
                        call_count=next_call_index,
                        drift_score=drift_score,
                    )

        return drift_score

    def after_record(self, *, cost_usd: float, prompt: str | None, output: str | None) -> None:
        agent_id = current_agent()
        workflow = current_workflow()
        session_id = current_session_id()
        state = self._state(agent_id, workflow, session_id)
        state.call_count += 1
        state.total_cost_usd += cost_usd
        if prompt:
            state.recent_prompts.append(prompt)
            state.recent_prompts = state.recent_prompts[-10:]
        if output:
            state.recent_outputs.append(output)
            state.recent_outputs = state.recent_outputs[-10:]

    def summary(self):
        return self._storage.summary()

    def _check_similarity_streak(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str,
        state: _SessionState,
        text: str,
        bucket: list[str],
        label: str,
        call_count: int,
    ) -> None:
        if not bucket:
            return
        similar_streak = 0
        for previous in reversed(bucket):
            if text_similarity(text, previous) >= self._config.similar_text_threshold:
                similar_streak += 1
            else:
                break
        if similar_streak + 1 >= self._config.similar_repeat_count:
            self._stop_loop(
                agent_id=agent_id,
                workflow=workflow,
                session_id=session_id,
                state=state,
                reason=f"similar_{label}",
                detail=(
                    f"{self._config.similar_repeat_count} {label}s similaires "
                    f"(seuil {self._config.similar_text_threshold})"
                ),
                call_count=call_count,
            )

    def _estimate_saved(self, state: _SessionState, avg_cost: float) -> float:
        remaining = max(
            0,
            self._config.estimated_calls_if_unbounded - state.call_count,
        )
        return round(remaining * avg_cost, 6)

    def _avg_cost(self, state: _SessionState) -> float:
        if state.call_count <= 0:
            return 0.001
        return max(state.total_cost_usd / state.call_count, 0.001)

    def _stop_loop(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str,
        state: _SessionState,
        reason: str,
        detail: str,
        call_count: int,
        drift_score: float | None = None,
    ) -> None:
        state.stopped = True
        saved = self._estimate_saved(state, self._avg_cost(state))
        self._storage.insert_stop(
            agent_id=agent_id,
            workflow=workflow,
            session_id=session_id,
            reason=reason,
            detail=detail,
            calls_at_stop=call_count,
            cost_at_stop=state.total_cost_usd,
            budget_limit=self._config.budget_limit_usd,
            drift_score=drift_score,
            estimated_saved_usd=saved,
        )
        raise LoopDetectedError(
            (
                f"Boucle détectée — agent '{agent_id}' (workflow '{workflow or '—'}'): "
                f"{detail} après {call_count} appel(s)"
            ),
            agent_id=agent_id,
            workflow=workflow,
            call_count=call_count,
            reason=reason,
        )

    def _stop_budget(
        self,
        *,
        agent_id: str,
        workflow: str | None,
        session_id: str,
        state: _SessionState,
        current_cost: float,
        pending_cost: float,
        call_count: int,
    ) -> None:
        state.stopped = True
        limit = self._config.budget_limit_usd or 0.0
        saved = self._estimate_saved(state, pending_cost or self._avg_cost(state))
        self._storage.insert_stop(
            agent_id=agent_id,
            workflow=workflow,
            session_id=session_id,
            reason="budget",
            detail=(
                f"coût actuel ${current_cost:.4f} + appel ${pending_cost:.4f} "
                f"> seuil ${limit:.4f}"
            ),
            calls_at_stop=call_count,
            cost_at_stop=current_cost,
            budget_limit=limit,
            drift_score=None,
            estimated_saved_usd=saved,
        )
        raise BudgetExceededError(
            (
                f"Budget dépassé — agent '{agent_id}' (workflow '{workflow or '—'}'): "
                f"coût actuel ${current_cost:.4f} + ${pending_cost:.4f} "
                f"> seuil ${limit:.4f}"
            ),
            agent_id=agent_id,
            workflow=workflow,
            current_cost_usd=current_cost,
            pending_cost_usd=pending_cost,
            limit_usd=limit,
        )
