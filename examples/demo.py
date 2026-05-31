"""Démo AgentLedger — coûts, guardrails et agent en boucle stoppé."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_ledger import (
    AgentGuardrails,
    GuardrailConfig,
    Ledger,
    agent_session,
    track_agent,
)
from agent_ledger.guardrails.exceptions import BudgetExceededError, LoopDetectedError

DB = ROOT / "data" / "demo_ledger.db"
LOOP_PROMPT = "Réessayer la même requête utilisateur sans progression"
LOOP_OUTPUT = "Tentative échouée, je réessaie immédiatement la même action"


@track_agent("research-bot", workflow="onboarding")
def run_research(ledger: Ledger) -> None:
    ledger.record(model="gpt-4o", input_tokens=12_400, output_tokens=2_100)


@track_agent("support-bot", workflow="tickets")
def run_support(ledger: Ledger) -> None:
    with agent_session("support-bot", workflow="escalation"):
        ledger.record(model="claude-3-5-sonnet-20241022", input_tokens=5_000, output_tokens=900)
    ledger.record(model="claude-3-haiku-20240307", input_tokens=1_200, output_tokens=400)


def run_orchestrator(ledger: Ledger) -> None:
    with agent_session("orchestrator", workflow="daily-sync"):
        ledger.record(
            model="gpt-4o",
            input_tokens=3_000,
            output_tokens=500,
            metadata={"step": "plan"},
        )
        ledger.record(
            model="gemini-1.5-flash",
            input_tokens=2_000,
            output_tokens=300,
            metadata={"step": "summarize"},
        )


def run_looping_agent(ledger: Ledger, guardrails: AgentGuardrails) -> None:
    """Simule un agent qui boucle jusqu'à déclenchement des guardrails."""
    guardrails.set_workflow_objective(
        "retry-loop",
        "Répondre une seule fois à la question utilisateur avec une solution concise",
    )
    config = guardrails.config
    print(f"\n=== Agent Guardrails — boucle (max {config.max_calls_per_session} appels) ===\n")

    stopped = False
    with agent_session("loop-bot", workflow="retry-loop"):
        for attempt in range(1, 25):
            try:
                ledger.record(
                    model="gpt-4o-mini",
                    input_tokens=400,
                    output_tokens=120,
                    prompt=LOOP_PROMPT,
                    output=LOOP_OUTPUT,
                    guardrails=guardrails,
                )
                print(f"  tentative {attempt}: appel enregistré")
            except LoopDetectedError as exc:
                print(f"  STOP — {exc}")
                stopped = True
                break
            except BudgetExceededError as exc:
                print(f"  STOP budget — {exc}")
                stopped = True
                break

    if not stopped:
        print("  (aucun arrêt — augmentez les tentatives ou baissez max_calls)")


def run_budget_guard_demo(ledger: Ledger) -> None:
    """Démo budget hard stop sur un workflow séparé."""
    print("\n=== Agent Guardrails — budget hard stop ===\n")
    budget_guard = AgentGuardrails.for_db(
        DB,
        GuardrailConfig(
            max_calls_per_session=100,
            budget_limit_usd=0.002,
            budget_scope="session",
        ),
    )
    with agent_session("budget-bot", workflow="expensive-task"):
        for attempt in range(1, 10):
            try:
                ledger.record(
                    model="gpt-4o",
                    input_tokens=800,
                    output_tokens=200,
                    guardrails=budget_guard,
                )
                print(f"  appel {attempt}: OK")
            except BudgetExceededError as exc:
                print(f"  STOP — {exc}")
                break


def main() -> None:
    if DB.exists():
        DB.unlink()

    Ledger.reset()
    ledger = Ledger.get(DB)
    guardrails = AgentGuardrails.for_db(
        DB,
        GuardrailConfig(
            max_calls_per_session=5,
            similar_text_threshold=0.80,
            similar_repeat_count=3,
            drift_warning_threshold=0.50,
        ),
    )

    run_research(ledger)
    run_support(ledger)
    run_orchestrator(ledger)
    run_looping_agent(ledger, guardrails)
    run_budget_guard_demo(ledger)

    print("\n=== Rapport par agent ===\n")
    for row in ledger.report(group_by="agent"):
        print(
            f"  {row.group_key}: {row.call_count} appels, "
            f"${row.total_cost_usd:.4f}"
        )

    summary = ledger.guardrail_summary()
    print("\n=== Agent Guardrails ===\n")
    print(f"  Workflows stoppés : {summary.stopped_workflows}")
    print(f"  Raisons           : {summary.stop_reasons}")
    print(f"  Drift moyen       : {summary.average_drift_score:.3f}")
    print(f"  Coût économisé    : ${summary.estimated_saved_usd:.4f}")

    print(f"\n  Dépense totale: ${ledger.total_spend():.4f}")
    print(f"  Base SQLite: {DB}")
    print("\n  CLI guardrails:")
    print(f"    py -3 -m agent_ledger.cli guardrails --db {DB}")


if __name__ == "__main__":
    main()
