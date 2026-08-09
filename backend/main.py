"""FastAPI execution skeleton for Agent Ops graph runs.

The service intentionally keeps execution deterministic and inspectable: every
node transition emits a trace event that a UI can consume over WebSockets.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A single executable graph node supplied by the visual editor."""

    id: str
    kind: Literal["llm", "tool", "retrieval", "conditional", "human"]
    label: str
    config: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed transition between two graph nodes."""

    source: str
    target: str
    condition: str | None = None


class GraphDefinition(BaseModel):
    """Serializable graph contract shared by the React canvas and executor."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphRun(BaseModel):
    """Request body for creating a graph run."""

    goal: str
    graph: GraphDefinition
    max_retries: int = Field(default=3, ge=0, le=10)


class TraceEvent(BaseModel):
    """Auditable state patch emitted during execution."""

    run_id: str
    sequence: int
    node_id: str
    event: str
    status: Literal["queued", "running", "retrying", "completed", "failed"]
    retry_count: int = 0
    timestamp: str
    state_delta: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="Agent Ops Orchestrator", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, GraphRun] = {}
TRACES: dict[str, list[TraceEvent]] = {}


@app.get("/health")
def health() -> dict[str, str | bool]:
    """Return service readiness for local development and uptime checks."""

    return {"ok": True, "service": "agent-ops", "version": app.version}


@app.post("/runs", status_code=202)
def create_run(run: GraphRun) -> dict[str, Any]:
    """Persist a submitted graph and return a run id for WebSocket streaming."""

    run_id = str(uuid.uuid4())
    RUNS[run_id] = run
    TRACES[run_id] = []
    return {
        "run_id": run_id,
        "status": "queued",
        "goal": run.goal,
        "nodes": len(run.graph.nodes),
        "edges": len(run.graph.edges),
    }


@app.get("/runs/{run_id}/trace")
def get_trace(run_id: str) -> dict[str, Any]:
    """Return the trace captured so far for post-run debugging."""

    return {"run_id": run_id, "events": [event.model_dump() for event in TRACES.get(run_id, [])]}


@app.websocket("/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    """Execute a deterministic graph simulation and stream trace events."""

    await websocket.accept()
    run = RUNS.get(run_id) or _demo_run()

    try:
        for sequence, event in enumerate(_simulate_execution(run_id, run), start=1):
            event.sequence = sequence
            TRACES.setdefault(run_id, []).append(event)
            await websocket.send_text(json.dumps(event.model_dump()))
            await asyncio.sleep(0.35)

        await websocket.send_text(json.dumps({"run_id": run_id, "status": "completed"}))
    except WebSocketDisconnect:
        return


def _simulate_execution(run_id: str, run: GraphRun) -> list[TraceEvent]:
    """Build trace events that expose branch decisions, tool calls, and retries."""

    now = lambda: datetime.now(timezone.utc).isoformat()
    events: list[TraceEvent] = []

    for node in run.graph.nodes:
        events.append(
            TraceEvent(
                run_id=run_id,
                sequence=0,
                node_id=node.id,
                event=f"{node.label} started",
                status="running",
                timestamp=now(),
                state_delta={"active_node": node.id},
            )
        )

        if node.kind == "tool":
            events.append(
                TraceEvent(
                    run_id=run_id,
                    sequence=0,
                    node_id=node.id,
                    event="tool timeout detected; retry scheduled with exponential jitter",
                    status="retrying",
                    retry_count=1,
                    timestamp=now(),
                    state_delta={"retry_policy": "exponential_jitter", "last_error": "timeout"},
                )
            )

        if node.kind == "conditional":
            events.append(
                TraceEvent(
                    run_id=run_id,
                    sequence=0,
                    node_id=node.id,
                    event="branch evaluated: confidence below threshold, route to critic",
                    status="completed",
                    timestamp=now(),
                    state_delta={"confidence": 0.77, "branch": "critic"},
                )
            )
        else:
            events.append(
                TraceEvent(
                    run_id=run_id,
                    sequence=0,
                    node_id=node.id,
                    event=f"{node.label} completed",
                    status="completed",
                    timestamp=now(),
                    state_delta={"completed_node": node.id},
                )
            )

    return events


def _demo_run() -> GraphRun:
    """Fallback graph used when the UI opens a WebSocket before creating a run."""

    return GraphRun(
        goal="Demo reliable agent workflow",
        graph=GraphDefinition(
            nodes=[
                GraphNode(id="planner", kind="llm", label="Planner Agent"),
                GraphNode(id="retrieval", kind="retrieval", label="Runbook Retrieval"),
                GraphNode(id="risk-gate", kind="conditional", label="Risk Gate"),
                GraphNode(id="tool", kind="tool", label="Tool Executor"),
                GraphNode(id="critic", kind="llm", label="Critic Agent"),
            ],
            edges=[
                GraphEdge(source="planner", target="retrieval"),
                GraphEdge(source="retrieval", target="risk-gate"),
                GraphEdge(source="risk-gate", target="tool", condition="approved"),
                GraphEdge(source="tool", target="critic"),
            ],
        ),
    )
