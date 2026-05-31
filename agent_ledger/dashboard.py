from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from agent_ledger.ledger import Ledger
from agent_ledger.settings import load_env, resolve_database_path

DEFAULT_OUTPUT = Path("data") / "dashboard.html"


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


def collect_dashboard_data(db_path: str | Path) -> dict:
    Ledger.reset()
    ledger = Ledger.get(db_path)
    recent = ledger.recent(limit=500)
    guardrails = ledger.guardrail_summary()
    stopped_agents = {s.agent_id for s in guardrails.stops}
    warned_agents = {
        c["agent_id"]
        for c in _serialize_calls(recent)
        if (c.get("drift_score") or 0) >= 0.5
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
    return {
        "db_path": str(Path(db_path).resolve()),
        "total_spend": round(ledger.total_spend(), 6),
        "total_calls": len(recent),
        "by_agent": by_agent,
        "by_workflow": _serialize_report(ledger.report(group_by="workflow")),
        "by_model": _serialize_report(ledger.report(group_by="model")),
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
<html lang="fr" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            slate: {{ 850: '#1a2332', 950: '#0f1419' }}
          }}
        }}
      }}
    }}
  </script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  <div class="max-w-7xl mx-auto p-6 space-y-8">
    <header class="border-b border-slate-800 pb-6">
      <h1 class="text-3xl font-bold tracking-tight">AgentLedger</h1>
      <p class="text-slate-400 text-sm mt-1 break-all" id="db-path"></p>
    </header>

    <div class="text-center py-10 rounded-2xl border border-emerald-500/30 bg-emerald-950/30 shadow-lg shadow-emerald-900/20">
      <div class="text-sm uppercase tracking-[0.2em] text-emerald-400/90 font-semibold">Saved by Guardrails</div>
      <div class="text-5xl md:text-6xl font-bold text-emerald-400 mt-3 tabular-nums" id="saved-total">$0.0000</div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4" id="kpis"></div>

    <div class="grid lg:grid-cols-2 gap-6">
      <div class="bg-slate-850 border border-slate-800 rounded-xl p-5 shadow-lg">
        <h2 class="text-slate-400 text-sm font-semibold mb-4">Répartition des coûts par agent (Pie)</h2>
        <div class="h-72"><canvas id="chart-pie-agents"></canvas></div>
      </div>
      <div class="bg-slate-850 border border-slate-800 rounded-xl p-5 shadow-lg">
        <h2 class="text-slate-400 text-sm font-semibold mb-4">Coût par agent (barres)</h2>
        <div class="h-72"><canvas id="chart-agent-cost"></canvas></div>
      </div>
      <div class="bg-slate-850 border border-slate-800 rounded-xl p-5 shadow-lg">
        <h2 class="text-slate-400 text-sm font-semibold mb-4">Coût par workflow</h2>
        <div class="h-72"><canvas id="chart-workflow-cost"></canvas></div>
      </div>
      <div class="bg-slate-850 border border-slate-800 rounded-xl p-5 shadow-lg">
        <h2 class="text-slate-400 text-sm font-semibold mb-4">Raisons d'arrêt guardrails</h2>
        <div class="h-72"><canvas id="chart-stop-reasons"></canvas></div>
      </div>
    </div>

    <section>
      <h2 class="text-lg font-semibold text-slate-300 mb-3">Agents — statut & coûts</h2>
      <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-850">
        <table class="w-full text-sm" id="table-agent"></table>
      </div>
    </section>

    <section>
      <h2 class="text-lg font-semibold text-slate-300 mb-3">Guardrails — arrêts récents</h2>
      <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-850">
        <table class="w-full text-sm" id="table-stops"></table>
      </div>
    </section>

    <section>
      <h2 class="text-lg font-semibold text-slate-300 mb-3">Détail des appels</h2>
      <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-850">
        <table class="w-full text-sm" id="table-calls"></table>
      </div>
    </section>
  </div>

  <script>
    const DATA = {payload};
    const palette = ["#3b82f6","#22c55e","#f59e0b","#a855f7","#ec4899","#14b8a6","#ef4444"];

    document.getElementById("db-path").textContent = DATA.db_path;
    const gr = DATA.guardrails || {{}};
    document.getElementById("saved-total").textContent =
      "$" + (gr.estimated_cost_saved || 0).toFixed(4);

    const kpis = [
      ["Dépense totale", "$" + DATA.total_spend.toFixed(4), "text-emerald-400"],
      ["Appels", DATA.total_calls, "text-white"],
      ["Agents", DATA.by_agent.length, "text-white"],
      ["Workflows", DATA.by_workflow.length, "text-white"],
      ["Stoppés", gr.stopped_workflows || 0, "text-red-400"],
      ["Économisé (legacy)", "$" + (gr.estimated_saved_usd || 0).toFixed(4), "text-slate-400"],
      ["Drift moy.", (gr.average_drift_score || 0).toFixed(3), "text-amber-400"],
    ];
    document.getElementById("kpis").innerHTML = kpis.map(([l,v,c]) =>
      `<div class="bg-slate-850 border border-slate-800 rounded-xl p-4"><div class="text-xs uppercase text-slate-500">${{l}}</div><div class="text-2xl font-bold mt-1 ${{c}}">${{v}}</div></div>`
    ).join("");

    const badge = (status) => {{
      if (status === "blocked") return '<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30">Bloqué</span>';
      if (status === "warning") return '<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30">Warning</span>';
      return '<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">Actif</span>';
    }};

    const chartText = "#94a3b8";
    const gridColor = "#334155";

    const agentLabels = DATA.by_agent.map(r => r.group);
    const agentCosts = DATA.by_agent.map(r => r.cost_usd);

    new Chart(document.getElementById("chart-pie-agents"), {{
      type: "pie",
      data: {{
        labels: agentLabels,
        datasets: [{{ data: agentCosts, backgroundColor: palette, borderWidth: 0 }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: "right", labels: {{ color: chartText }} }} }}
      }}
    }});

    function barChart(id, labels, values) {{
      new Chart(document.getElementById(id), {{
        type: "bar",
        data: {{
          labels,
          datasets: [{{ label: "USD", data: values, backgroundColor: palette.slice(0, labels.length), borderRadius: 6 }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ ticks: {{ color: chartText }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: chartText }}, grid: {{ color: gridColor }} }}
          }}
        }}
      }});
    }}

    barChart("chart-agent-cost", agentLabels, agentCosts);
    barChart("chart-workflow-cost", DATA.by_workflow.map(r => r.group), DATA.by_workflow.map(r => r.cost_usd));

    const stopReasons = gr.stop_reasons || {{}};
    const reasonLabels = Object.keys(stopReasons);
    if (reasonLabels.length) {{
      new Chart(document.getElementById("chart-stop-reasons"), {{
        type: "bar",
        data: {{
          labels: reasonLabels,
          datasets: [{{ data: reasonLabels.map(k => stopReasons[k]), backgroundColor: "#ef4444", borderRadius: 6 }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ ticks: {{ color: chartText }}, grid: {{ color: gridColor }} }},
            y: {{ ticks: {{ color: chartText }}, grid: {{ color: gridColor }} }}
          }}
        }}
      }});
    }}

    function tableHtml(elId, columns, rows) {{
      const el = document.getElementById(elId);
      const head = "<thead class='bg-slate-900/80'><tr>" + columns.map(c =>
        `<th class="px-4 py-3 text-left text-xs uppercase text-slate-500 font-semibold ${{c.numeric ? 'text-right' : ''}}">${{c.label}}</th>`
      ).join("") + "</tr></thead>";
      const body = "<tbody class='divide-y divide-slate-800'>" + rows.map(row =>
        "<tr class='hover:bg-slate-800/40'>" + columns.map(c =>
          `<td class="px-4 py-3 ${{c.numeric ? 'text-right tabular-nums' : ''}} ${{c.money ? 'text-emerald-400' : ''}}">${{c.fmt ? c.fmt(row) : (row[c.key] ?? '—')}}</td>`
        ).join("") + "</tr>"
      ).join("") + "</tbody>";
      el.innerHTML = head + body;
    }}

    tableHtml("table-agent", [
      {{ key: "group", label: "Agent" }},
      {{ key: "status", label: "Statut", fmt: r => badge(r.status) }},
      {{ key: "calls", label: "Appels", numeric: true }},
      {{ key: "input_tokens", label: "Tokens in", numeric: true }},
      {{ key: "output_tokens", label: "Tokens out", numeric: true }},
      {{ key: "cost_usd", label: "USD", numeric: true, money: true, fmt: r => r.cost_usd.toFixed(4) }},
    ], DATA.by_agent);

    tableHtml("table-stops", [
      {{ key: "created_at", label: "Date" }},
      {{ key: "agent_id", label: "Agent" }},
      {{ key: "workflow", label: "Workflow" }},
      {{ key: "reason", label: "Raison" }},
      {{ key: "detail", label: "Détail" }},
      {{ key: "estimated_cost_saved", label: "Économisé", numeric: true, money: true, fmt: r => r.estimated_cost_saved.toFixed(4) }},
    ], gr.stops || []);

    tableHtml("table-calls", [
      {{ key: "id", label: "#", numeric: true }},
      {{ key: "created_at", label: "Date" }},
      {{ key: "agent_id", label: "Agent" }},
      {{ key: "workflow", label: "Workflow" }},
      {{ key: "model", label: "Modèle" }},
      {{ key: "cost_usd", label: "USD", numeric: true, money: true, fmt: r => r.cost_usd.toFixed(6) }},
    ], DATA.calls);
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
