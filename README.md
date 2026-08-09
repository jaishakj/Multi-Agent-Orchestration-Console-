# Agent Ops — Multi-Agent Orchestration Console

Agent Ops is a lightweight LangGraph/n8n-style platform for visually designing, running, debugging, and replaying reliable multi-step AI agents. The project now includes the previously deferred MVP pillars: durable storage, bearer-token auth, drag-and-drop graph editing, adapter endpoints for LLM/tool calls, and persisted replay.

## What is implemented

- **React + Vite frontend:** a visual console with draggable graph nodes, a node palette, run controls, auth/session fields, metrics, inspector, and persisted trace/replay panel.
- **FastAPI backend:** typed graph contracts, authenticated run APIs, trace retrieval, replay retrieval, and WebSocket streaming.
- **Durable storage:** SQLite tables for users, sessions, runs, and trace events. Set `AGENT_OPS_DB=/path/to/file.sqlite3` to choose a database path.
- **Auth:** username/password registration, login, PBKDF2 password hashing, and bearer-token protected run, trace, replay, and adapter endpoints.
- **Adapters:** `/adapters/llm` and `/adapters/tools` endpoints provide stable adapter contracts. The LLM endpoint reports OpenAI readiness when `OPENAI_API_KEY` exists and otherwise uses a local simulator. Tool adapters include `calculator`, `echo`, and a safe planned `http_get` stub.
- **Persisted replay:** every streamed trace event is written to SQLite and can be retrieved through `GET /runs/{run_id}/replay`.

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

The API starts at <http://localhost:8000>. SQLite schema creation runs on startup.

## API flow

1. Register and log in:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"password123"}'

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"password123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

2. Create a persisted run:

```bash
curl -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "goal":"Research a customer issue, call tools, and produce a verified answer",
    "max_retries":3,
    "graph":{
      "nodes":[
        {"id":"planner","kind":"llm","label":"Planner Agent"},
        {"id":"retrieval","kind":"retrieval","label":"Runbook Retrieval"},
        {"id":"risk-gate","kind":"conditional","label":"Risk Gate"},
        {"id":"tool","kind":"tool","label":"Tool Executor"}
      ],
      "edges":[
        {"source":"planner","target":"retrieval"},
        {"source":"retrieval","target":"risk-gate"},
        {"source":"risk-gate","target":"tool","condition":"approved"}
      ]
    }
  }'
```

3. Stream and replay execution:

- `WS /runs/{run_id}/stream` executes the graph simulator and stores trace events.
- `GET /runs/{run_id}/trace` returns ordered trace events.
- `GET /runs/{run_id}/replay` returns the persisted run plus ordered events.

## Remaining production hardening

This is still an MVP, but no longer just a static mock. Production hardening would add OAuth/SAML, migrations, a real graph layout engine, tenant isolation, background workers, full OpenAI SDK integration, sandboxed network tools, and frontend API wiring to replace the local UI simulator.
