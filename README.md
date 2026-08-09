# Agent Ops — Multi-Agent Orchestration Console

Agent Ops is a lightweight LangGraph/n8n-style platform for visually designing, running, and debugging reliable multi-step AI agents. The goal is not to hide orchestration behind a framework; it is to make graph execution, retries, branch decisions, state changes, and failure modes visible enough to debug.

## App shape

- **Frontend:** React + Vite console with a node palette, graph canvas, selected-node inspector, reliability metrics, run controls, and live trace timeline.
- **Backend:** Python/FastAPI executor API that accepts typed graph runs, exposes trace history, and streams state patches over WebSockets.
- **Reliability focus:** The mock workflow explicitly surfaces retries, timeout handling, low-confidence branch routing, stale-output detection, and loop-risk checks.

## Run the frontend

```bash
npm install
npm run dev
```

The Vite app starts on the port printed by Vite, usually <http://localhost:5173>.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API starts at <http://localhost:8000>.

## API sketch

- `GET /health` returns service status and version metadata.
- `POST /runs` accepts a graph definition and returns a `run_id`.
- `GET /runs/{run_id}/trace` returns captured trace events for a run.
- `WS /runs/{run_id}/stream` emits ordered state patches for the UI trace.

Example run payload:

```json
{
  "goal": "Research a customer issue, call tools, and produce a verified answer",
  "max_retries": 3,
  "graph": {
    "nodes": [
      { "id": "planner", "kind": "llm", "label": "Planner Agent" },
      { "id": "retrieval", "kind": "retrieval", "label": "Runbook Retrieval" },
      { "id": "risk-gate", "kind": "conditional", "label": "Risk Gate" },
      { "id": "tool", "kind": "tool", "label": "Tool Executor" }
    ],
    "edges": [
      { "source": "planner", "target": "retrieval" },
      { "source": "retrieval", "target": "risk-gate" },
      { "source": "risk-gate", "target": "tool", "condition": "approved" }
    ]
  }
}
```

## Current limitations

This is an MVP scaffold, not the whole production app. It has a runnable UI shell and a runnable backend simulator, but durable storage, authentication, drag-and-drop graph editing, real LLM/tool adapters, and persisted run replay are intentionally left as next milestones.
