# AgentLedger

MVP de **Agent P&L** : middleware Python pour tracer et attribuer les coûts API d'une flotte d'agents IA.

## Démarrage rapide

```bash
cd locales
python examples/demo.py
python -m agent_ledger.cli report --db data/demo_ledger.db
python -m agent_ledger.cli report --group-by workflow --db data/demo_ledger.db
py -3 -m agent_ledger.cli dashboard --db data/demo_ledger.db
```

## Usage dans votre code

```python
from agent_ledger import Ledger, agent_session, track_agent

ledger = Ledger.get()  # ~/.agent_ledger/ledger.db

@track_agent("sales-bot", workflow="qualification")
def handle_lead():
    ledger.record(model="gpt-4o-mini", input_tokens=500, output_tokens=120)

with agent_session("orchestrator"):
  ledger.record(model="gpt-4o", input_tokens=2000, output_tokens=400)
```

## OpenAI (optionnel)

```python
from openai import OpenAI
from agent_ledger.openai_hook import TrackedOpenAI
from agent_ledger import agent_session

client = TrackedOpenAI(OpenAI())
with agent_session("my-agent"):
    client.chat.completions.create(model="gpt-4o-mini", messages=[...])
```
