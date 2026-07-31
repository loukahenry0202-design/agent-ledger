# AgentLedger

**Agent P&L** is a lightweight Python middleware for **LLM cost observability, cost attribution, and budget enforcement** in multi-agent AI systems.

It provides fine-grained tracking of API expenditures across agents, workflows, tools, and projects, enabling transparent financial monitoring of AI infrastructures.

The middleware also includes built-in runtime safeguards designed to reduce unnecessary operational costs:

* **Drift Detection** — detects abnormal increases in token consumption and API spending.
* **Infinite Loop Prevention** — identifies and interrupts recursive agent execution.
* **Budget Enforcement** — automatically blocks requests that exceed predefined spending limits.
* **Cost Attribution** — allocates every API call to its originating agent, workflow, or project.
* **Real-Time Monitoring** — exposes live metrics for performance optimization and FinOps analysis.

Agent P&L is designed as a modular middleware that can be integrated into existing Python-based AI applications with minimal overhead, providing production-ready cost governance for Large Language Model (LLM) workloads.

## Quick Start

```bash
cd locales
python examples/demo.py
python -m agent_ledger.cli report --db data/demo_ledger.db
python -m agent_ledger.cli report --group-by workflow --db data/demo_ledger.db
py -3 -m agent_ledger.cli dashboard --db data/demo_ledger.db
```

## Usage in your code

```python
from agent_ledger import Ledger, agent_session, track_agent

# Initialize or retrieve the global ledger instance (default storage: ~/.agent_ledger/ledger.db)
ledger = Ledger.get()

# Track costs automatically for a specific agent and workflow using a decorator
@track_agent("sales-bot", workflow="qualification")
def handle_lead():
    # Record explicit token usage and associated model architecture costs
    ledger.record(
        model="gpt-4o-mini",
        input_tokens=500,
        output_tokens=120
    )

    # Track nested sub-tasks within a specific execution context
    with agent_session("orchestrator"):
        ledger.record(
            model="gpt-4o",
            input_tokens=2000,
            output_tokens=400
        )
```

## OpenAI Integration (Optional)

```python
from openai import OpenAI
from agent_ledger.openai_hook import TrackedOpenAI
from agent_ledger import agent_session

# Wrap the standard OpenAI client with AgentLedger instrumentation hooks
client = TrackedOpenAI(OpenAI())

# Automatically monitor and attribute API consumption within the session context
with agent_session("my-agent"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[...]
    )
```
