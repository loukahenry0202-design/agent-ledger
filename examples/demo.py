"""Démo AgentLedger — simule une flotte de 3 agents sans appels API réels."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_ledger import Ledger, agent_session, track_agent

DB = ROOT / "data" / "demo_ledger.db"


@track_agent("research-bot", workflow="onboarding")
def run_research() -> None:
    ledger = Ledger.get(DB)
    ledger.record(model="gpt-4o", input_tokens=12_400, output_tokens=2_100)
    ledger.record(model="gpt-4o-mini", input_tokens=800, output_tokens=350)


@track_agent("support-bot", workflow="tickets")
def run_support() -> None:
    ledger = Ledger.get(DB)
    with agent_session("support-bot", workflow="escalation"):
        ledger.record(model="claude-3-5-sonnet-20241022", input_tokens=5_000, output_tokens=900)
    ledger.record(model="claude-3-haiku-20240307", input_tokens=1_200, output_tokens=400)


def run_orchestrator() -> None:
    with agent_session("orchestrator", workflow="daily-sync"):
        ledger = Ledger.get(DB)
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


def main() -> None:
    Ledger.reset()
    Ledger.get(DB)
    run_research()
    run_support()
    run_orchestrator()

    ledger = Ledger.get(DB)
    print("=== Rapport par agent ===\n")
    for row in ledger.report(group_by="agent"):
        print(
            f"  {row.group_key}: {row.call_count} appels, "
            f"${row.total_cost_usd:.4f} ({row.input_tokens + row.output_tokens} tokens)"
        )

    print(f"\n  Dépense totale: ${ledger.total_spend():.4f}")
    print(f"\n  Base SQLite: {DB}")
    print("\n  CLI: python -m agent_ledger.cli report --db", DB)


if __name__ == "__main__":
    main()
