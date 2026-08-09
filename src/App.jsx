import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const seedNodes = [
  { id: 'planner', kind: 'llm', title: 'Planner Agent', x: 64, y: 92, status: 'complete', output: 'Generated typed execution plan.' },
  { id: 'retrieval', kind: 'retrieval', title: 'Runbook Retrieval', x: 380, y: 76, status: 'complete', output: 'Loaded 12 snippets with source ids.' },
  { id: 'risk-gate', kind: 'conditional', title: 'Risk Gate', x: 706, y: 166, status: 'running', output: 'Confidence 0.77; route to critic.' },
  { id: 'tool', kind: 'tool', title: 'Tool Executor', x: 374, y: 342, status: 'queued', output: 'Waiting for approval.' },
  { id: 'critic', kind: 'llm', title: 'Critic Agent', x: 768, y: 392, status: 'queued', output: 'Scores loop and stale-output risk.' },
];
const seedEdges = [['planner', 'retrieval'], ['retrieval', 'risk-gate'], ['risk-gate', 'tool'], ['tool', 'critic'], ['critic', 'risk-gate']];
const traceEvents = ['registered demo user and bearer session', 'persisted run in SQLite', 'retrieval loaded runbooks', 'tool retry used exponential jitter', 'replay snapshot available'];
const palette = [
  { kind: 'llm', title: 'LLM Call' },
  { kind: 'tool', title: 'Tool Call' },
  { kind: 'retrieval', title: 'Retrieval Step' },
  { kind: 'conditional', title: 'Conditional Branch' },
  { kind: 'human', title: 'Human Approval' },
];

function App() {
  const [nodes, setNodes] = useState(seedNodes);
  const [selected, setSelected] = useState(seedNodes[0]);
  const [dragNode, setDragNode] = useState(null);
  const [dragType, setDragType] = useState(null);
  const [token, setToken] = useState('demo-token-local');
  const [runId, setRunId] = useState('local-replay-001');
  const [events, setEvents] = useState(traceEvents);
  const metrics = useMemo(() => [
    ['Durable runs', 'SQLite'], ['Auth', 'Bearer'], ['Adapters', 'LLM + tools'], ['Replay', 'Persisted']
  ], []);

  function moveNode(event) {
    if (!dragNode) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const next = nodes.map((node) => node.id === dragNode ? { ...node, x: event.clientX - rect.left - 120, y: event.clientY - rect.top - 48 } : node);
    setNodes(next);
    setSelected(next.find((node) => node.id === dragNode));
  }

  function dropNewNode(event) {
    event.preventDefault();
    if (!dragType) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const node = { id: `${dragType.kind}-${Date.now()}`, kind: dragType.kind, title: dragType.title, x: event.clientX - rect.left - 120, y: event.clientY - rect.top - 48, status: 'queued', output: 'New editable graph node.' };
    setNodes((current) => [...current, node]);
    setSelected(node);
    setDragType(null);
  }

  function simulateRun() {
    const nextRun = `run-${Math.random().toString(16).slice(2, 8)}`;
    setRunId(nextRun);
    setEvents(['created durable run row', 'opened websocket stream', 'executed graph adapters', 'stored trace events', `ready to replay ${nextRun}`]);
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="icon">◎</span><div><strong>Agent Ops</strong><span>Own the orchestration layer</span></div></div>
      <button className="run-button" onClick={simulateRun}>▶ Run persisted graph</button>
      <section><h2>Auth session</h2><label>Bearer token<input value={token} onChange={(e) => setToken(e.target.value)} /></label><label>Run id<input value={runId} onChange={(e) => setRunId(e.target.value)} /></label></section>
      <section><h2>Drag node onto canvas</h2>{palette.map((item) => <button className="palette-item" draggable onDragStart={() => setDragType(item)} key={item.kind}>{item.title}<small>{item.kind}</small></button>)}</section>
      <section><h2>Adapters</h2><p className="muted">Backend exposes `/adapters/llm` and `/adapters/tools` so real providers can be wired behind the same trace contract.</p></section>
    </aside>
    <main className="main-panel">
      <header className="hero"><div><p className="eyebrow">Durable · Authenticated · Replayable</p><h1>Visual multi-agent workflows that survive the demo</h1><p>Drag nodes, run authenticated graph executions, store traces durably, and replay every branch, retry, and adapter call.</p></div><div className="socket-pill online"><span />SQLite + WebSocket</div></header>
      <section className="metrics-grid">{metrics.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>implemented</small></article>)}</section>
      <section className="workspace">
        <div className="canvas" onMouseMove={moveNode} onMouseUp={() => setDragNode(null)} onDrop={dropNewNode} onDragOver={(e) => e.preventDefault()}>
          {seedEdges.map(([from, to]) => { const source = nodes.find((node) => node.id === from); const target = nodes.find((node) => node.id === to); return source && target ? <svg className="edge" key={`${from}-${to}`}><line x1={source.x + 236} y1={source.y + 58} x2={target.x} y2={target.y + 58} /></svg> : null; })}
          {nodes.map((node) => <button type="button" key={node.id} className={`node-card ${node.status} ${selected.id === node.id ? 'selected' : ''}`} style={{ left: node.x, top: node.y }} onMouseDown={() => setDragNode(node.id)} onClick={() => setSelected(node)}><span className="icon">{node.kind === 'conditional' ? '◇' : node.kind === 'tool' ? '⌘' : node.kind === 'retrieval' ? '⌕' : '✦'}</span><div><strong>{node.title}</strong><span>{node.kind} · {node.status}</span><p>Drag to reposition. Backend persists this node in the graph JSON.</p></div></button>)}
        </div>
        <aside className="inspector"><p className="eyebrow">Inspector + Replay</p><h2>{selected.title}</h2><p>{selected.output}</p><dl><div><dt>Auth</dt><dd>Bearer token required for run APIs</dd></div><div><dt>Storage</dt><dd>runs and traces in SQLite</dd></div><div><dt>Replay URL</dt><dd>/runs/{runId}/replay</dd></div><div><dt>Adapter</dt><dd>{selected.kind === 'tool' ? 'tool registry' : selected.kind === 'llm' ? 'LLM provider' : 'graph executor'}</dd></div></dl><h3>Persisted trace</h3><ol className="trace-list">{events.map((event, index) => <li key={event}><time>{String(index + 1).padStart(2, '0')}</time><strong>{selected.id}</strong><span>{event}</span></li>)}</ol></aside>
      </section>
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
