"""FastAPI service for Agent Ops graph execution, persistence, auth, and replay."""

import asyncio
import hashlib
import hmac
import json
import operator
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = Path(os.getenv("AGENT_OPS_DB", "agent_ops.sqlite3"))
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=48)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class GraphNode(BaseModel):
    id: str
    kind: Literal["llm", "tool", "retrieval", "conditional", "human"]
    label: str
    config: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    condition: str | None = None


class GraphDefinition(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphRun(BaseModel):
    goal: str
    graph: GraphDefinition
    max_retries: int = Field(default=3, ge=0, le=10)


class TraceEvent(BaseModel):
    run_id: str
    sequence: int
    node_id: str
    event: str
    status: Literal["queued", "running", "retrying", "completed", "failed"]
    retry_count: int = 0
    timestamp: str
    state_delta: dict[str, Any] = Field(default_factory=dict)


class ToolInvocation(BaseModel):
    name: Literal["calculator", "http_get", "echo"]
    args: dict[str, Any] = Field(default_factory=dict)


class LlmInvocation(BaseModel):
    prompt: str
    model: str = "gpt-4.1-mini"


app = FastAPI(title="Agent Ops Orchestrator", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@contextmanager
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                graph_json TEXT NOT NULL,
                status TEXT NOT NULL,
                max_retries INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS traces (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(run_id, sequence),
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, expected = password_hash.split("$", 1)
    actual = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    with db() as conn:
        row = conn.execute("SELECT user_id FROM sessions WHERE token = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")
    return str(row["user_id"])


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "service": "agent-ops", "version": app.version}


@app.post("/auth/register", status_code=201)
def register(payload: UserCreate) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, payload.username, hash_password(payload.password), now()),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists") from exc
    return {"user_id": user_id, "username": payload.username}


@app.post("/auth/login")
def login(payload: LoginRequest) -> dict[str, str]:
    with db() as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (payload.username,)).fetchone()
        if not row or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, row["id"], now()))
    return {"access_token": token, "token_type": "bearer"}


@app.post("/runs", status_code=202)
def create_run(run: GraphRun, user_id: str = Depends(current_user)) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    ts = now()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO runs (id, user_id, goal, graph_json, status, max_retries, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, user_id, run.goal, run.graph.model_dump_json(), "queued", run.max_retries, ts, ts),
        )
    return {"run_id": run_id, "status": "queued", "goal": run.goal, "nodes": len(run.graph.nodes), "edges": len(run.graph.edges)}


@app.get("/runs")
def list_runs(user_id: str = Depends(current_user)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, goal, status, created_at, updated_at FROM runs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return {"runs": [dict(row) for row in rows]}


@app.get("/runs/{run_id}/trace")
def get_trace(run_id: str, user_id: str = Depends(current_user)) -> dict[str, Any]:
    ensure_run_owner(run_id, user_id)
    return {"run_id": run_id, "events": load_trace(run_id)}


@app.get("/runs/{run_id}/replay")
def replay_run(run_id: str, user_id: str = Depends(current_user)) -> dict[str, Any]:
    run = ensure_run_owner(run_id, user_id)
    return {"run": run, "events": load_trace(run_id)}


@app.post("/adapters/llm")
def invoke_llm(invocation: LlmInvocation, _: str = Depends(current_user)) -> dict[str, Any]:
    if os.getenv("OPENAI_API_KEY"):
        return {"provider": "openai", "model": invocation.model, "status": "configured", "message": "OpenAI adapter is ready for SDK wiring."}
    return {"provider": "local-sim", "model": invocation.model, "text": f"Simulated answer for: {invocation.prompt[:120]}"}


@app.post("/adapters/tools")
def invoke_tool(invocation: ToolInvocation, _: str = Depends(current_user)) -> dict[str, Any]:
    if invocation.name == "calculator":
        expression = str(invocation.args.get("expression", ""))
        allowed = set("0123456789+-*/(). ")
        if not expression or any(char not in allowed for char in expression):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Calculator expression contains unsupported characters")
        return {"name": invocation.name, "result": safe_calculate(expression)}
    if invocation.name == "http_get":
        return {"name": invocation.name, "status": "planned", "url": invocation.args.get("url"), "note": "Network tool is defined but disabled by default for safe local runs."}
    return {"name": invocation.name, "result": invocation.args}


@app.websocket("/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    run = load_run(run_id) or demo_run_record(run_id)
    graph_run = GraphRun(goal=run["goal"], graph=GraphDefinition.model_validate_json(run["graph_json"]), max_retries=run["max_retries"])
    try:
        for sequence, event in enumerate(simulate_execution(run_id, graph_run), start=1):
            event.sequence = sequence
            save_trace(event)
            mark_run_status(run_id, "running")
            await websocket.send_text(json.dumps(event.model_dump()))
            await asyncio.sleep(0.3)
        mark_run_status(run_id, "completed")
        await websocket.send_text(json.dumps({"run_id": run_id, "status": "completed"}))
    except WebSocketDisconnect:
        mark_run_status(run_id, "disconnected")


def ensure_run_owner(run_id: str, user_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?", (run_id, user_id)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return dict(row)


def load_run(run_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def load_trace(run_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT event_json FROM traces WHERE run_id = ? ORDER BY sequence", (run_id,)).fetchall()
    return [json.loads(row["event_json"]) for row in rows]


def save_trace(event: TraceEvent) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO traces (run_id, sequence, event_json, created_at) VALUES (?, ?, ?, ?)",
            (event.run_id, event.sequence, event.model_dump_json(), now()),
        )


def mark_run_status(run_id: str, run_status: str) -> None:
    with db() as conn:
        conn.execute("UPDATE runs SET status = ?, updated_at = ? WHERE id = ?", (run_status, now(), run_id))


def simulate_execution(run_id: str, run: GraphRun) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for node in run.graph.nodes:
        events.append(trace(run_id, node.id, f"{node.label} started", "running", {"active_node": node.id}))
        if node.kind == "retrieval":
            events.append(trace(run_id, node.id, "retrieved runbooks and prior failures", "completed", {"documents": 12}))
        elif node.kind == "conditional":
            events.append(trace(run_id, node.id, "branch evaluated below confidence threshold", "completed", {"confidence": 0.77, "branch": "critic"}))
        elif node.kind == "tool":
            events.append(trace(run_id, node.id, "tool timeout detected; retry scheduled", "retrying", {"retry_policy": "exponential_jitter"}, retry_count=1))
            events.append(trace(run_id, node.id, "tool completed with idempotency key", "completed", {"idempotency_key": str(uuid.uuid4())}))
        else:
            events.append(trace(run_id, node.id, f"{node.label} completed", "completed", {"completed_node": node.id}))
    return events


def safe_calculate(expression: str) -> float:
    """Evaluate a simple arithmetic expression without exposing Python builtins."""

    import ast

    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -evaluate(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported calculator expression")

    return evaluate(ast.parse(expression, mode="eval"))


def trace(run_id: str, node_id: str, event: str, status_value: Literal["queued", "running", "retrying", "completed", "failed"], state_delta: dict[str, Any], retry_count: int = 0) -> TraceEvent:
    return TraceEvent(run_id=run_id, sequence=0, node_id=node_id, event=event, status=status_value, retry_count=retry_count, timestamp=now(), state_delta=state_delta)


def demo_run_record(run_id: str) -> dict[str, Any]:
    graph = GraphDefinition(
        nodes=[
            GraphNode(id="planner", kind="llm", label="Planner Agent"),
            GraphNode(id="retrieval", kind="retrieval", label="Runbook Retrieval"),
            GraphNode(id="risk-gate", kind="conditional", label="Risk Gate"),
            GraphNode(id="tool", kind="tool", label="Tool Executor"),
            GraphNode(id="critic", kind="llm", label="Critic Agent"),
        ],
        edges=[GraphEdge(source="planner", target="retrieval"), GraphEdge(source="retrieval", target="risk-gate"), GraphEdge(source="risk-gate", target="tool"), GraphEdge(source="tool", target="critic")],
    )
    return {"id": run_id, "goal": "Demo reliable agent workflow", "graph_json": graph.model_dump_json(), "max_retries": 3}
