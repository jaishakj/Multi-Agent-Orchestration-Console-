import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const initialNodes = [
  {
    id: 'planner',
    kind: 'LLM',
    title: 'Planner Agent',
    x: 64,
    y: 92,
    status: 'complete',
    prompt: 'Break the user goal into typed, auditable steps.',
    output: 'Generated a five-step plan with explicit success criteria.',
  },
  {
    id: 'retrieval',
    kind: 'RAG',
    title: 'Runbook Retrieval',
    x: 380,
    y: 76,
    status: 'complete',
    prompt: 'Load policy, tool schemas, and historical failure examples.',
    output: 'Retrieved 12 snippets and attached source ids to state.context.',
  },
  {
    id: 'risk-gate',
    kind: 'IF',
    title: 'Risk Gate',
    x: 706,
    y: 166,
    status: 'running',
    prompt: 'If confidence < 0.82 or tool risk is high, branch to critic.',
    output: 'Confidence is 0.77, so the graph enters verification mode.',
  },
  {
    id: 'tool',
    kind: 'TOOL',
    title: 'Tool Executor',
    x: 374,
    y: 342,
    status: 'queued',
    prompt: 'Execute deterministic tools with timeouts and idempotency keys.',
    output: 'Waiting for risk-gate approval before invocation.',
  },
  {
    id: 'critic',
    kind: 'LLM',
    title: 'Critic Agent',
    x: 768,
    y: 392,
    status: 'queued',
    prompt: 'Detect loops, stale tool output, and unsupported claims.',
    output: 'Will score the final answer before completion.',
  },
];

const edges = [
  ['planner', 'retrieval'],
  ['retrieval', 'risk-gate'],
  ['risk-gate', 'tool'],
  ['tool', 'critic'],
  ['critic', 'risk-gate'],
];

const traceEvents = [
  { time: '00:00.000', node: 'planner', event: 'goal decomposed into a typed plan' },
  { time: '00:00.421', node: 'retrieval', event: 'loaded policy context and tool schemas' },
  { time: '00:01.104', node: 'risk-gate', event: 'confidence below threshold; branch selected' },
  { time: '00:01.668', node: 'tool', event: 'retry scheduled with exponential jitter' },
  { time: '00:02.210', node: 'critic', event: 'loop detector score: low risk' },
];

const palette = ['LLM Call', 'Tool Call', 'Retrieval Step', 'Conditional Branch', 'Human Approval'];

function Icon({ children }) {
  return <span className="icon" aria-hidden="true">{children}</span>;
}

function NodeCard({ node, selected, onSelect }) {
  return (
    <button
      className={`node-card ${node.status} ${selected ? 'selected' : ''}`}
      onClick={() => onSelect(node)}
      style={{ left: node.x, top: node.y }}
      type="button"
    >
      <Icon>{node.kind === 'IF' ? '◇' : node.kind === 'TOOL' ? '⌘' : node.kind === 'RAG' ? '⌕' : '✦'}</Icon>
      <div>
        <strong>{node.title}</strong>
        <span>{node.kind} · {node.status}</span>
        <p>{node.prompt}</p>
      </div>
    </button>
  );
}

function App() {
  const [isRunning, setIsRunning] = useState(false);
  const [selectedNode, setSelectedNode] = useState(initialNodes[0]);

  const metrics = useMemo(() => [
    { label: 'Reliability', value: '97.8%', change: '+4.2%' },
    { label: 'Average retries', value: '1.3', change: '-0.6' },
    { label: 'Trace events', value: '248', change: 'live' },
    { label: 'Run cost', value: '$0.18', change: 'budgeted' },
  ], []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Icon>◎</Icon>
          <div>
            <strong>Agent Ops</strong>
            <span>Orchestration Console</span>
          </div>
        </div>

        <button className="run-button" type="button" onClick={() => setIsRunning((value) => !value)}>
          {isRunning ? '↻ Streaming run' : '▶ Run graph'}
        </button>

        <section>
          <h2>Node palette</h2>
          {palette.map((item, index) => (
            <div className="palette-item" key={item}>
              <span>{item}</span>
              <small>{String(index + 1).padStart(2, '0')}</small>
            </div>
          ))}
        </section>

        <section>
          <h2>Run controls</h2>
          <label>Max retries<input defaultValue="3" /></label>
          <label>Timeout<input defaultValue="45s" /></label>
          <label>Budget cap<input defaultValue="$1.00" /></label>
        </section>
      </aside>

      <main className="main-panel">
        <header className="hero">
          <div>
            <p className="eyebrow">Build · Run · Debug</p>
            <h1>Visual workflows for reliable AI agents</h1>
            <p>
              Design stateful agent graphs, execute them through FastAPI, and inspect every prompt,
              branch, retry, tool call, and state mutation from one trace-first console.
            </p>
          </div>
          <div className={`socket-pill ${isRunning ? 'online' : ''}`}>
            <span />
            {isRunning ? 'WebSocket streaming' : 'Ready to run'}
          </div>
        </header>

        <section className="metrics-grid" aria-label="Run reliability metrics">
          {metrics.map((metric) => (
            <article className="metric-card" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.change}</small>
            </article>
          ))}
        </section>

        <section className="workspace">
          <div className="canvas" aria-label="Agent graph canvas">
            {edges.map(([from, to]) => {
              const source = initialNodes.find((node) => node.id === from);
              const target = initialNodes.find((node) => node.id === to);
              return (
                <svg className="edge" key={`${from}-${to}`}>
                  <line x1={source.x + 236} y1={source.y + 58} x2={target.x} y2={target.y + 58} />
                </svg>
              );
            })}
            {initialNodes.map((node) => (
              <NodeCard
                key={node.id}
                node={node}
                selected={selectedNode.id === node.id}
                onSelect={setSelectedNode}
              />
            ))}
          </div>

          <aside className="inspector">
            <p className="eyebrow">Inspector</p>
            <h2>{selectedNode.title}</h2>
            <p>{selectedNode.prompt}</p>

            <dl>
              <div><dt>Retry policy</dt><dd>exponential jitter</dd></div>
              <div><dt>State keys</dt><dd>goal, context, risk, result</dd></div>
              <div><dt>Failure mode</dt><dd>loop + stale tool output</dd></div>
              <div><dt>Last output</dt><dd>{selectedNode.output}</dd></div>
            </dl>

            <h3>Live trace</h3>
            <ol className="trace-list">
              {traceEvents.map((trace) => (
                <li key={`${trace.time}-${trace.node}`}>
                  <time>{trace.time}</time>
                  <strong>{trace.node}</strong>
                  <span>{trace.event}</span>
                </li>
              ))}
            </ol>
          </aside>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
