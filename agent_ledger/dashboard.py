from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from agent_ledger.ledger import Ledger
from agent_ledger.models import GuardrailStopRecord
from agent_ledger.settings import load_env, resolve_database_path

DEFAULT_OUTPUT = Path("data") / "dashboard.html"

WORKFLOW_LABELS: dict[str, str] = {
    "onboarding": "Intégration utilisateur — analyse initiale",
    "tickets": "Traitement des tickets support",
    "escalation": "Escalade ticket prioritaire",
    "daily-sync": "Synchronisation quotidienne des agents",
    "retry-loop": "Répondre une seule fois avec une solution concise",
    "expensive-task": "Tâche coûteuse — surveillance budget",
}


def _serialize_report(rows: list) -> list[dict]:
    return [
        {
            "group": r.group_key,
            "calls": r.call_count,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": round(r.total_cost_usd, 6),
        }
        for r in rows
    ]


def _serialize_calls(records: list) -> list[dict]:
    return [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "model": r.model,
            "workflow": r.workflow or "—",
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": round(r.cost_usd, 6),
            "drift_score": r.metadata.get("drift_score"),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in records
    ]


def _agent_kind(agent_id: str) -> str:
    aid = agent_id.lower()
    if "research" in aid:
        return "research"
    if "orchestrat" in aid:
        return "orchestrator"
    if "support" in aid:
        return "support"
    if "loop" in aid:
        return "loop"
    if "budget" in aid:
        return "budget"
    return "bot"


def _task_label(workflow: str | None) -> str:
    if not workflow:
        return "Tâche en cours"
    return WORKFLOW_LABELS.get(workflow, workflow.replace("-", " ").capitalize())


def _format_stop_message(stop: GuardrailStopRecord) -> str:
    if stop.reason == "budget":
        return f"Budget dépassé — agent '{stop.agent_id}'"
    if stop.reason == "LoopDetected":
        return f"STOP – Boucle détectée – {stop.detail}"
    if stop.reason == "similar_prompt":
        return f"STOP – Boucle détectée – {stop.detail}"
    if stop.reason == "similar_output":
        return f"STOP – Sortie répétitive – {stop.detail}"
    if stop.reason == "max_calls":
        return f"STOP – Limite d'appels – {stop.detail}"
    if stop.reason == "drift":
        return f"STOP – Dérive détectée – {stop.detail}"
    return f"STOP – {stop.reason} – {stop.detail}"


def _build_agent_cards(
    by_agent: list[dict],
    recent,
    stops: list[GuardrailStopRecord],
) -> list[dict]:
    latest_workflow: dict[str, str | None] = {}
    for call in recent:
        if call.agent_id not in latest_workflow:
            latest_workflow[call.agent_id] = call.workflow

    stop_by_agent: dict[str, GuardrailStopRecord] = {}
    for stop in stops:
        if stop.agent_id not in stop_by_agent:
            stop_by_agent[stop.agent_id] = stop

    agents_seen: set[str] = set()
    cards: list[dict] = []

    def _append_card(agent_id: str, row: dict | None) -> None:
        if agent_id in agents_seen:
            return
        agents_seen.add(agent_id)
        workflow = latest_workflow.get(agent_id) or (
            stop_by_agent[agent_id].workflow if agent_id in stop_by_agent else None
        )
        stop = stop_by_agent.get(agent_id)
        status = row["status"] if row else ("blocked" if stop else "ok")
        card: dict = {
            "agent_id": agent_id,
            "status": status,
            "calls": row["calls"] if row else 0,
            "cost_usd": row["cost_usd"] if row else 0.0,
            "current_task": _task_label(workflow),
            "workflow": workflow or "—",
            "kind": _agent_kind(agent_id),
        }
        if stop:
            budget_pct = None
            if stop.budget_limit and stop.budget_limit > 0:
                budget_pct = min(100.0, round(stop.cost_at_stop / stop.budget_limit * 100, 1))
            card["stop"] = {
                "reason": stop.reason,
                "detail": stop.detail,
                "message": _format_stop_message(stop),
                "budget_limit": stop.budget_limit,
                "cost_at_stop": round(stop.cost_at_stop, 6),
                "budget_pct": budget_pct if stop.reason == "budget" else budget_pct,
            }
            if stop.reason == "budget" and budget_pct is None:
                card["stop"]["budget_pct"] = 100.0
        cards.append(card)

    for row in by_agent:
        _append_card(row["group"], row)

    for agent_id in stop_by_agent:
        _append_card(agent_id, None)

    cards.sort(key=lambda c: (-{"blocked": 2, "warning": 1, "ok": 0}[c["status"]], c["agent_id"]))
    return cards


def collect_dashboard_data(db_path: str | Path) -> dict:
    Ledger.reset()
    ledger = Ledger.get(db_path)
    recent = ledger.recent(limit=500)
    guardrails = ledger.guardrail_summary()
    stopped_agents = {s.agent_id for s in guardrails.stops}
    warned_agents = {
        c.agent_id for c in recent if (c.metadata.get("drift_score") or 0) >= 0.5
    }
    by_agent = _serialize_report(ledger.report(group_by="agent"))
    for row in by_agent:
        agent = row["group"]
        if agent in stopped_agents:
            row["status"] = "blocked"
        elif agent in warned_agents:
            row["status"] = "warning"
        else:
            row["status"] = "ok"

    agent_cards = _build_agent_cards(by_agent, recent, guardrails.stops)

    return {
        "db_path": str(Path(db_path).resolve()),
        "total_spend": round(ledger.total_spend(), 6),
        "total_calls": len(recent),
        "by_agent": by_agent,
        "by_workflow": _serialize_report(ledger.report(group_by="workflow")),
        "by_model": _serialize_report(ledger.report(group_by="model")),
        "agent_cards": agent_cards,
        "calls": _serialize_calls(recent),
        "guardrails": {
            "stopped_workflows": guardrails.stopped_workflows,
            "stop_reasons": guardrails.stop_reasons,
            "average_drift_score": guardrails.average_drift_score,
            "estimated_saved_usd": guardrails.estimated_saved_usd,
            "estimated_cost_saved": guardrails.estimated_cost_saved,
            "stops": [
                {
                    "id": s.id,
                    "agent_id": s.agent_id,
                    "workflow": s.workflow or "—",
                    "reason": s.reason,
                    "detail": s.detail,
                    "calls_at_stop": s.calls_at_stop,
                    "cost_at_stop": round(s.cost_at_stop, 6),
                    "estimated_saved_usd": round(s.estimated_saved_usd, 6),
                    "estimated_cost_saved": round(s.estimated_cost_saved, 6),
                    "drift_score": s.drift_score,
                    "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for s in guardrails.stops
            ],
        },
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            copilot: {{
              border: '#E5E7EB',
              muted: '#6B7280',
              accent: '#107C10',
              warn: '#CA5010',
              danger: '#D13438',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;500;600;700&display=swap');
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }}
  </style>
</head>
<body class="bg-white text-gray-900 min-h-screen antialiased">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

    <header class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 pb-6 border-b border-[#E5E7EB]">
      <div>
        <p class="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-1">AgentLedger</p>
        <h1 class="text-2xl sm:text-3xl font-semibold text-gray-900 tracking-tight">Tableau de bord des agents</h1>
      </div>
      <p class="text-xs text-gray-400 break-all max-w-md" id="db-path"></p>
    </header>

    <!-- Étape 3 : Widgets résumé & graphique -->
    <section class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div class="bg-white border border-[#E5E7EB] rounded-lg p-6 flex flex-col justify-between min-h-[220px]">
        <div>
          <p class="text-sm font-medium text-gray-500">Consommation totale</p>
          <p class="text-3xl font-semibold text-gray-900 mt-2 tabular-nums" id="total-spend">$0.0000</p>
          <p class="text-sm text-gray-400 mt-1"><span id="total-calls">0</span> appels · <span id="agent-count">0</span> agents</p>
        </div>
        <div class="mt-6 pt-6 border-t border-[#E5E7EB]">
          <p class="text-xs font-semibold uppercase tracking-wider text-[#107C10]">Saved by Guardrails</p>
          <p class="text-4xl sm:text-5xl font-bold text-[#107C10] mt-1 tabular-nums" id="saved-total">$0.0000</p>
          <p class="text-xs text-gray-400 mt-1">Coût estimé évité par les hard stops</p>
        </div>
      </div>

      <div class="bg-white border border-[#E5E7EB] rounded-lg p-6 md:col-span-1 lg:col-span-2 min-h-[220px]">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-sm font-semibold text-gray-700">Répartition des coûts par agent</h2>
          <span class="text-xs text-gray-400">Pie chart</span>
        </div>
        <div class="h-52 sm:h-56 flex items-center justify-center">
          <canvas id="chart-pie-agents"></canvas>
        </div>
      </div>
    </section>

    <!-- Étape 2 : Cartes agents style Copilot Task -->
    <section>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">Agents actifs</h2>
        <span class="text-xs text-gray-400" id="cards-count"></span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="agent-cards"></div>
    </section>

    <!-- Activité récente (compacte) -->
    <section class="pb-8">
      <h2 class="text-sm font-semibold text-gray-700 mb-3">Activité récente</h2>
      <div class="bg-white border border-[#E5E7EB] rounded-lg divide-y divide-[#E5E7EB]" id="recent-activity"></div>
    </section>
  </div>

  <script>
    const DATA = {payload};
    const palette = ["#0078D4","#107C10","#CA5010","#8764B8","#038387","#E3008C","#FFB900"];
    const gr = DATA.guardrails || {{}};

    document.getElementById("db-path").textContent = DATA.db_path;
    document.getElementById("total-spend").textContent = "$" + DATA.total_spend.toFixed(4);
    document.getElementById("total-calls").textContent = DATA.total_calls;
    document.getElementById("agent-count").textContent = DATA.by_agent.length;
    document.getElementById("saved-total").textContent =
      "$" + (gr.estimated_cost_saved || 0).toFixed(4);

    const ICONS = {{
      research: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>`,
      orchestrator: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.2 7.5l3.6 8M15.8 7.5l-3.6 8M8.5 6h7"/></svg>`,
      support: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M12 3c-4 0-7 2.5-7 6v3a2 2 0 002 2h1v-4H5c0-2.5 2.5-4.5 7-4.5s7 2 7 4.5h-3v4h1a2 2 0 002-2V9c0-3.5-3-6-7-6z"/><path d="M10 21h4"/></svg>`,
      loop: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>`,
      budget: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/><path d="M6 15h2"/></svg>`,
      bot: `<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M9 8V5a3 3 0 016 0v3"/><circle cx="9" cy="14" r="1" fill="currentColor"/><circle cx="15" cy="14" r="1" fill="currentColor"/><path d="M9 18h6"/></svg>`,
    }};

    const MENU_ICON = `<svg class="w-4 h-4 text-gray-400 hover:text-gray-600 cursor-pointer" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>`;

    function statusBadge(status) {{
      if (status === "blocked") {{
        return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-[#D13438] border border-red-100">Stopped</span>`;
      }}
      if (status === "warning") {{
        return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-50 text-[#CA5010] border border-orange-100">Warning</span>`;
      }}
      return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-50 text-[#107C10] border border-green-100">Running</span>`;
    }}

    function budgetBar(pct, reason) {{
      if (pct == null) return "";
      const color = reason === "budget" ? "bg-[#D13438]" : pct >= 90 ? "bg-[#CA5010]" : "bg-[#107C10]";
      return `
        <div class="mt-3">
          <div class="flex justify-between text-xs text-gray-500 mb-1">
            <span>Budget</span>
            <span>${{pct}}%</span>
          </div>
          <div class="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
            <div class="${{color}} h-1.5 rounded-full transition-all" style="width: ${{Math.min(pct, 100)}}%"></div>
          </div>
        </div>`;
    }}

    function renderAgentCard(card) {{
      const icon = ICONS[card.kind] || ICONS.bot;
      const iconBg = {{
        research: "bg-blue-50 text-[#0078D4]",
        orchestrator: "bg-purple-50 text-[#8764B8]",
        support: "bg-teal-50 text-[#038387]",
        loop: "bg-orange-50 text-[#CA5010]",
        budget: "bg-red-50 text-[#D13438]",
        bot: "bg-gray-50 text-gray-600",
      }}[card.kind] || "bg-gray-50 text-gray-600";

      let guardrailHtml = "";
      if (card.stop) {{
        guardrailHtml = budgetBar(card.stop.budget_pct, card.stop.reason);
        guardrailHtml += `<p class="mt-2 text-xs font-medium text-[#D13438] leading-relaxed">${{card.stop.message}}</p>`;
      }} else if (card.status === "warning") {{
        guardrailHtml = `<p class="mt-2 text-xs font-medium text-[#CA5010]">Dérive détectée — surveillance active</p>`;
      }} else {{
        guardrailHtml = `<p class="mt-2 text-xs text-gray-400">Guardrails actifs · aucun arrêt</p>`;
      }}

      return `
        <article class="bg-white border border-[#E5E7EB] rounded-lg p-5 hover:shadow-sm transition-shadow flex flex-col">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0">
              <div class="flex-shrink-0 w-9 h-9 rounded-lg ${{iconBg}} flex items-center justify-center">${{icon}}</div>
              <div class="min-w-0">
                <h3 class="text-sm font-semibold text-gray-900 truncate">${{card.agent_id}}</h3>
                <p class="text-xs text-gray-400 truncate">${{card.workflow}}</p>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              ${{statusBadge(card.status)}}
              <button type="button" title="Détails" aria-label="Détails">${{MENU_ICON}}</button>
            </div>
          </div>

          <div class="mt-4 flex-1">
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Tâche actuelle</p>
            <p class="text-sm text-gray-800 leading-snug">${{card.current_task}}</p>

            <div class="mt-4 flex items-end justify-between">
              <div>
                <p class="text-xs text-gray-400">${{card.calls}} appel${{card.calls > 1 ? "s" : ""}}</p>
              </div>
              <p class="text-xl font-semibold text-gray-900 tabular-nums">$${{card.cost_usd.toFixed(4)}}</p>
            </div>

            <div class="mt-4 pt-4 border-t border-[#E5E7EB]">
              <p class="text-xs font-medium text-gray-500 mb-1">Guardrails</p>
              ${{guardrailHtml}}
            </div>
          </div>
        </article>`;
    }}

    const cards = DATA.agent_cards || [];
    document.getElementById("cards-count").textContent = cards.length + " agent" + (cards.length > 1 ? "s" : "");
    document.getElementById("agent-cards").innerHTML = cards.length
      ? cards.map(renderAgentCard).join("")
      : `<p class="text-sm text-gray-400 col-span-full py-8 text-center">Aucun agent enregistré.</p>`;

    const agentLabels = DATA.by_agent.map(r => r.group);
    const agentCosts = DATA.by_agent.map(r => r.cost_usd);
    if (agentLabels.length) {{
      new Chart(document.getElementById("chart-pie-agents"), {{
        type: "pie",
        data: {{
          labels: agentLabels,
          datasets: [{{
            data: agentCosts,
            backgroundColor: palette.slice(0, agentLabels.length),
            borderWidth: 2,
            borderColor: "#FFFFFF",
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              position: "right",
              labels: {{
                color: "#374151",
                font: {{ size: 12, family: "'Segoe UI', system-ui, sans-serif" }},
                padding: 14,
                usePointStyle: true,
                pointStyle: "circle",
              }}
            }},
            tooltip: {{
              callbacks: {{
                label: (ctx) => ` ${{ctx.label}}: $${{ctx.parsed.toFixed(4)}}`
              }}
            }}
          }}
        }}
      }});
    }}

    const recent = (DATA.calls || []).slice(0, 8);
    document.getElementById("recent-activity").innerHTML = recent.length
      ? recent.map(c => `
          <div class="flex items-center justify-between px-4 py-3 text-sm hover:bg-gray-50 transition-colors">
            <div class="flex items-center gap-3 min-w-0">
              <span class="text-xs text-gray-400 tabular-nums flex-shrink-0">${{c.created_at}}</span>
              <span class="font-medium text-gray-800 truncate">${{c.agent_id}}</span>
              <span class="text-gray-400 truncate hidden sm:inline">${{c.workflow}}</span>
            </div>
            <span class="text-gray-900 font-medium tabular-nums flex-shrink-0 ml-4">$${{c.cost_usd.toFixed(4)}}</span>
          </div>`).join("")
      : `<p class="px-4 py-6 text-sm text-gray-400 text-center">Aucune activité récente.</p>`;
  </script>
</body>
</html>
"""


def build_dashboard(
    db_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    out = Path(output_path or DEFAULT_OUTPUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = collect_dashboard_data(db_path)
    out.write_text(render_html(data), encoding="utf-8")
    return out.resolve()


def open_in_browser(path: Path) -> None:
    webbrowser.open(path.as_uri())


def main(argv: list[str] | None = None) -> int:
    import argparse

    load_env()
    parser = argparse.ArgumentParser(description="Génère le dashboard HTML AgentLedger")
    parser.add_argument(
        "--db",
        default=str(resolve_database_path("data/demo_ledger.db")),
        help="Base SQLite source",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=str(DEFAULT_OUTPUT),
        help="Fichier HTML de sortie",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Ne pas ouvrir le navigateur",
    )
    args = parser.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"Base introuvable : {db}")
        print("Lancez d'abord : py -3 examples/demo.py")
        return 1

    out = build_dashboard(db, args.output)
    print(f"Dashboard généré : {out}")
    if not args.no_open:
        open_in_browser(out)
        print("Ouverture dans le navigateur…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
