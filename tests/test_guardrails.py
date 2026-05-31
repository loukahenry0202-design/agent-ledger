"""Tests Agent Guardrails."""

from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

from agent_ledger import AgentGuardrails, GuardrailConfig, Ledger, agent_session
from agent_ledger.guardrails.drift import compute_drift_score
from agent_ledger.guardrails.exceptions import BudgetExceededError, DriftWarning, LoopDetectedError
from agent_ledger.guardrails.similarity import jaccard_similarity, text_similarity


class SimilarityTests(unittest.TestCase):
    def test_identical_texts(self) -> None:
        self.assertGreater(jaccard_similarity("hello world", "hello world"), 0.99)

    def test_different_texts(self) -> None:
        self.assertLess(text_similarity("bonjour", "quantum physics"), 0.3)


class DriftTests(unittest.TestCase):
    def test_aligned_output_low_drift(self) -> None:
        objective = "Répondre une seule fois avec une solution concise"
        output = "Voici la solution concise demandée en une seule réponse"
        self.assertLess(compute_drift_score(objective, output), 0.6)

    def test_off_topic_high_drift(self) -> None:
        objective = "Répondre une seule fois avec une solution concise"
        output = "Je réessaie encore et encore sans jamais répondre au sujet"
        self.assertGreater(compute_drift_score(objective, output), 0.4)


class GuardrailEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / "test.db"
        Ledger.reset()
        self.ledger = Ledger.get(self.db)
        self.guardrails = AgentGuardrails.for_db(
            str(self.db),
            GuardrailConfig(
                max_calls_per_session=3,
                similar_text_threshold=0.85,
                similar_repeat_count=3,
                budget_limit_usd=0.01,
                budget_scope="session",
            ),
        )

    def tearDown(self) -> None:
        if self.guardrails is not None:
            self.guardrails.close()
        Ledger.reset()
        self.guardrails = None
        self.tmp.cleanup()

    def test_max_calls_triggers_loop_error(self) -> None:
        with agent_session("bot", workflow="wf"):
            for _ in range(3):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=100,
                    output_tokens=50,
                    guardrails=self.guardrails,
                )
            with self.assertRaises(LoopDetectedError):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=100,
                    output_tokens=50,
                    guardrails=self.guardrails,
                )

    def test_similar_prompts_trigger_loop(self) -> None:
        prompt = "réessayer la même requête sans progression"
        with agent_session("bot", workflow="loop-wf"):
            for _ in range(2):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=50,
                    output_tokens=20,
                    prompt=prompt,
                    guardrails=self.guardrails,
                )
            with self.assertRaises(LoopDetectedError) as ctx:
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=50,
                    output_tokens=20,
                    prompt=prompt,
                    guardrails=self.guardrails,
                )
        self.assertIn("similar", ctx.exception.reason)

    def test_budget_hard_stop(self) -> None:
        guard = AgentGuardrails.for_db(
            str(self.db),
            GuardrailConfig(max_calls_per_session=50, budget_limit_usd=0.001),
        )
        with agent_session("budget-bot", workflow="expensive"):
            with self.assertRaises(BudgetExceededError) as ctx:
                self.ledger.record(
                    model="gpt-4o",
                    input_tokens=5000,
                    output_tokens=1000,
                    guardrails=guard,
                )
        self.assertGreater(ctx.exception.limit_usd, 0)

    def test_drift_warning_emitted(self) -> None:
        self.guardrails.set_workflow_objective("drift-wf", "Répondre sobrement une seule fois")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with agent_session("bot", workflow="drift-wf"):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=100,
                    output_tokens=50,
                    output="Je boucle encore et encore sans répondre au problème initial",
                    guardrails=self.guardrails,
                )
        drift_warnings = [w for w in caught if issubclass(w.category, DriftWarning)]
        self.assertTrue(drift_warnings)

    def test_stop_persisted_in_summary(self) -> None:
        with agent_session("bot", workflow="persist"):
            for _ in range(3):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=10,
                    output_tokens=5,
                    guardrails=self.guardrails,
                )
            with self.assertRaises(LoopDetectedError):
                self.ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=10,
                    output_tokens=5,
                    guardrails=self.guardrails,
                )
        summary = self.ledger.guardrail_summary()
        self.assertEqual(summary.stopped_workflows, 1)
        self.assertGreater(summary.estimated_saved_usd, 0)


if __name__ == "__main__":
    unittest.main()
