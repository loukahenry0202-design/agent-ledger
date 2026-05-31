from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_ledger.ledger import Ledger
from agent_ledger.settings import load_env, resolve_database_path
from agent_ledger.storage import GroupBy


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(
        prog="agent-ledger",
        description="Rapports de coûts API par agent IA",
    )
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument(
        "--db",
        default=os.environ.get("AGENT_LEDGER_DB"),
        help="Chemin SQLite (défaut: ~/.agent_ledger/ledger.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report_p = sub.add_parser("report", help="Rapport agrégé", parents=[db_parent])
    report_p.add_argument(
        "--group-by",
        choices=["agent", "model", "workflow", "day"],
        default="agent",
    )
    report_p.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("total", help="Dépense totale en USD", parents=[db_parent])
    sub.add_parser("recent", help="Derniers appels enregistrés", parents=[db_parent])

    dash_p = sub.add_parser("dashboard", help="Dashboard HTML + navigateur", parents=[db_parent])
    dash_p.add_argument(
        "--output",
        "-o",
        default="data/dashboard.html",
        help="Fichier HTML de sortie",
    )
    dash_p.add_argument("--no-open", action="store_true", help="Ne pas ouvrir le navigateur")

    sub.add_parser("guardrails", help="Rapport Agent Guardrails", parents=[db_parent])

    args = parser.parse_args(argv)
    Ledger.reset()
    db_default = resolve_database_path("data/demo_ledger.db")
    ledger = Ledger.get(args.db or db_default)

    if args.command == "report":
        rows = ledger.report(group_by=args.group_by)  # type: ignore[attr-defined]
        if args.as_json:
            print(
                json.dumps(
                    [
                        {
                            "group": r.group_key,
                            "calls": r.call_count,
                            "input_tokens": r.input_tokens,
                            "output_tokens": r.output_tokens,
                            "cost_usd": r.total_cost_usd,
                        }
                        for r in rows
                    ],
                    indent=2,
                )
            )
            return 0
        if not rows:
            print("Aucun appel enregistré.")
            return 0
        print(f"\n{'Groupe':<24} {'Appels':>8} {'Tokens in':>12} {'Tokens out':>12} {'USD':>10}")
        print("-" * 70)
        for r in rows:
            print(
                f"{r.group_key:<24} {r.call_count:>8} {r.input_tokens:>12} "
                f"{r.output_tokens:>12} {r.total_cost_usd:>10.4f}"
            )
        print("-" * 70)
        print(f"{'TOTAL':<24} {'':<8} {'':<12} {'':<12} {ledger.total_spend():>10.4f}")
        return 0

    if args.command == "total":
        print(f"${ledger.total_spend():.6f}")
        return 0

    if args.command == "recent":
        for r in ledger.recent(15):
            wf = f" [{r.workflow}]" if r.workflow else ""
            print(
                f"#{r.id} {r.created_at:%Y-%m-%d %H:%M} "
                f"{r.agent_id}{wf} {r.model} "
                f"in={r.input_tokens} out={r.output_tokens} ${r.cost_usd:.6f}"
            )
        return 0

    if args.command == "dashboard":
        from agent_ledger.dashboard import build_dashboard, open_in_browser

        db_path = args.db or "data/demo_ledger.db"
        if not Path(db_path).is_file():
            print(f"Base introuvable : {db_path}")
            print("Lancez d'abord : py -3 examples/demo.py")
            return 1
        out = build_dashboard(db_path, args.output)
        print(f"Dashboard généré : {out}")
        if not args.no_open:
            open_in_browser(out)
            print("Ouverture dans le navigateur…")
        return 0

    if args.command == "guardrails":
        summary = ledger.guardrail_summary()
        if summary.stopped_workflows == 0:
            print("Aucun arrêt guardrails enregistré.")
            return 0
        print(f"\nWorkflows stoppés : {summary.stopped_workflows}")
        print(f"Drift score moyen : {summary.average_drift_score:.3f}")
        print(f"Saved by Guardrails : ${summary.estimated_cost_saved:.4f}")
        print(f"Coût économisé (legacy) : ${summary.estimated_saved_usd:.4f}")
        print(f"Raisons : {summary.stop_reasons}\n")
        print(f"{'Date':<18} {'Agent':<16} {'Workflow':<16} {'Raison':<16} {'Économisé':>10}")
        print("-" * 80)
        for s in summary.stops[:20]:
            print(
                f"{s.created_at:%Y-%m-%d %H:%M} {s.agent_id:<16} "
                f"{(s.workflow or '—'):<16} {s.reason:<16} "
                f"${s.estimated_cost_saved:>9.4f}"
            )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
