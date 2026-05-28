from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from agent_ledger.ledger import Ledger

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
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in records
    ]


def collect_dashboard_data(db_path: str | Path) -> dict:
    Ledger.reset()
    ledger = Ledger.get(db_path)
    recent = ledger.recent(limit=500)
    return {
        "db_path": str(Path(db_path).resolve()),
        "total_spend": round(ledger.total_spend(), 6),
        "total_calls": len(recent),
        "by_agent": _serialize_report(ledger.report(group_by="agent")),
        "by_workflow": _serialize_report(ledger.report(group_by="workflow")),
        "by_model": _serialize_report(ledger.report(group_by="model")),
        "calls": _serialize_calls(recent),
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #1a2332;
      --border: #2d3a4f;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #3b82f6;
      --green: #22c55e;
      --orange: #f59e0b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1.5rem;
    }}
    header {{
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
    }}
    h1 {{ font-size: 1.75rem; font-weight: 600; }}
    .subtitle {{ color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; word-break: break-all; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .kpi {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.25rem;
    }}
    .kpi-label {{ color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .kpi-value {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
    .kpi-value.money {{ color: var(--green); }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .chart-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem;
    }}
    .chart-card h2 {{
      font-size: 0.95rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
      color: var(--muted);
    }}
    .chart-wrap {{ position: relative; height: 260px; }}
    section {{ margin-bottom: 1.5rem; }}
    section h2 {{
      font-size: 1rem;
      margin-bottom: 0.75rem;
      color: var(--muted);
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--card);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}
    th, td {{
      padding: 0.65rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      background: #243044;
      color: var(--muted);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(59, 130, 246, 0.06); }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .money {{ color: var(--green); }}
  </style>
</head>
<body>
  <header>
    <h1>AgentLedger</h1>
    <p class="subtitle" id="db-path"></p>
  </header>

  <div class="kpis">
    <div class="kpi">
      <div class="kpi-label">Dépense totale</div>
      <div class="kpi-value money" id="kpi-spend">—</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Appels enregistrés</div>
      <div class="kpi-value" id="kpi-calls">—</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Agents actifs</div>
      <div class="kpi-value" id="kpi-agents">—</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Workflows</div>
      <div class="kpi-value" id="kpi-workflows">—</div>
    </div>
  </div>

  <div class="charts">
    <div class="chart-card">
      <h2>Coût par agent (USD)</h2>
      <div class="chart-wrap"><canvas id="chart-agent-cost"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Coût par workflow (USD)</h2>
      <div class="chart-wrap"><canvas id="chart-workflow-cost"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Répartition des coûts</h2>
      <div class="chart-wrap"><canvas id="chart-share"></canvas></div>
    </div>
    <div class="chart-card">
      <h2>Tokens par agent</h2>
      <div class="chart-wrap"><canvas id="chart-tokens"></canvas></div>
    </div>
  </div>

  <section>
    <h2>Rapport par agent</h2>
    <div class="table-wrap">
      <table id="table-agent"></table>
    </div>
  </section>

  <section>
    <h2>Rapport par workflow</h2>
    <div class="table-wrap">
      <table id="table-workflow"></table>
    </div>
  </section>

  <section>
    <h2>Détail des appels</h2>
    <div class="table-wrap">
      <table id="table-calls"></table>
    </div>
  </section>

  <script>
    const DATA = {payload};

    document.getElementById("db-path").textContent = DATA.db_path;
    document.getElementById("kpi-spend").textContent = "$" + DATA.total_spend.toFixed(4);
    document.getElementById("kpi-calls").textContent = DATA.total_calls;
    document.getElementById("kpi-agents").textContent = DATA.by_agent.length;
    document.getElementById("kpi-workflows").textContent = DATA.by_workflow.length;

    const palette = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#ec4899", "#14b8a6"];
    const chartDefaults = {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color: "#8b9cb3" }} }} }},
      scales: {{
        x: {{ ticks: {{ color: "#8b9cb3" }}, grid: {{ color: "#2d3a4f" }} }},
        y: {{ ticks: {{ color: "#8b9cb3" }}, grid: {{ color: "#2d3a4f" }} }},
      }},
    }};

    function barChart(id, labels, values, label) {{
      new Chart(document.getElementById(id), {{
        type: "bar",
        data: {{
          labels,
          datasets: [{{
            label,
            data: values,
            backgroundColor: palette.slice(0, labels.length),
            borderRadius: 6,
          }}],
        }},
        options: chartDefaults,
      }});
    }}

    const agentLabels = DATA.by_agent.map(r => r.group);
    const agentCosts = DATA.by_agent.map(r => r.cost_usd);
    barChart("chart-agent-cost", agentLabels, agentCosts, "USD");
    barChart(
      "chart-workflow-cost",
      DATA.by_workflow.map(r => r.group),
      DATA.by_workflow.map(r => r.cost_usd),
      "USD"
    );

    new Chart(document.getElementById("chart-share"), {{
      type: "doughnut",
      data: {{
        labels: agentLabels,
        datasets: [{{
          data: agentCosts,
          backgroundColor: palette,
          borderWidth: 0,
        }}],
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: "right", labels: {{ color: "#8b9cb3" }} }} }},
      }},
    }});

    new Chart(document.getElementById("chart-tokens"), {{
      type: "bar",
      data: {{
        labels: agentLabels,
        datasets: [
          {{
            label: "Tokens entrée",
            data: DATA.by_agent.map(r => r.input_tokens),
            backgroundColor: "#3b82f6",
            borderRadius: 4,
          }},
          {{
            label: "Tokens sortie",
            data: DATA.by_agent.map(r => r.output_tokens),
            backgroundColor: "#f59e0b",
            borderRadius: 4,
          }},
        ],
      }},
      options: {{ ...chartDefaults, scales: {{ ...chartDefaults.scales, x: {{ stacked: true, ...chartDefaults.scales.x }}, y: {{ stacked: true, ...chartDefaults.scales.y }} }} }},
    }});

    function buildTable(elId, columns, rows) {{
      const el = document.getElementById(elId);
      const head = "<thead><tr>" + columns.map(c => `<th class="${{c.numeric ? "num" : ""}}">${{c.label}}</th>`).join("") + "</tr></thead>";
      const body = "<tbody>" + rows.map(row =>
        "<tr>" + columns.map(c => `<td class="${{c.numeric ? "num" : ""}}${{c.money ? " money" : ""}}">${{c.fmt ? c.fmt(row) : row[c.key]}}</td>`).join("") + "</tr>"
      ).join("") + "</tbody>";
      el.innerHTML = head + body;
    }}

    const reportCols = [
      {{ key: "group", label: "Groupe" }},
      {{ key: "calls", label: "Appels", numeric: true }},
      {{ key: "input_tokens", label: "Tokens in", numeric: true }},
      {{ key: "output_tokens", label: "Tokens out", numeric: true }},
      {{ key: "cost_usd", label: "USD", numeric: true, money: true, fmt: r => r.cost_usd.toFixed(4) }},
    ];
    buildTable("table-agent", reportCols, DATA.by_agent);
    buildTable("table-workflow", reportCols, DATA.by_workflow);

    buildTable("table-calls", [
      {{ key: "id", label: "#", numeric: true }},
      {{ key: "created_at", label: "Date" }},
      {{ key: "agent_id", label: "Agent" }},
      {{ key: "workflow", label: "Workflow" }},
      {{ key: "model", label: "Modèle" }},
      {{ key: "input_tokens", label: "In", numeric: true }},
      {{ key: "output_tokens", label: "Out", numeric: true }},
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
    import os

    parser = argparse.ArgumentParser(description="Génère le dashboard HTML AgentLedger")
    parser.add_argument(
        "--db",
        default=os.environ.get("AGENT_LEDGER_DB", "data/demo_ledger.db"),
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
