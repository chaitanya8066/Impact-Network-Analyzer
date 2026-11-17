
import React, { useEffect, useMemo, useState } from 'react';
import { Play, Square, RefreshCw, Activity, Terminal, Unplug, Cable } from 'lucide-react';
import { backendApi } from '../../services/backendApi.js';
import { useTopologyStore } from '../../store/topologyStore.js';

const formatOutput = (value) => {
  if (Array.isArray(value)) return value.join('\n');
  if (typeof value === 'string') return value;
  return '';
};

// Parse Linux ip addr output
const parseIpAddr = (rawOutput) => {
  const clean = rawOutput.replace(/\x1b\[[0-9;]*m/g, '');
  const lines = clean.split('\n');
  const interfaces = [];

  let current = null;

  for (const line of lines) {
    const interfaceMatch = line.match(
      /^\d+:\s+([^:]+):\s+<([^>]*)>.*?mtu\s+(\d+)/
    );

    if (interfaceMatch) {
      if (current) interfaces.push(current);

      current = {
        name: interfaceMatch[1].split('@')[0],
        flags: interfaceMatch[2],
        mtu: interfaceMatch[3],
        mac: '',
        ipv4: '',
        subnet: '',
      };

      continue;
    }

    if (!current) continue;

    const macMatch = line.match(/link\/ether\s+(\S+)/);
    if (macMatch) current.mac = macMatch[1];

    const ipv4Match = line.match(/inet\s+([\d.]+)\/(\d+)/);

    if (ipv4Match) {
      current.ipv4 = ipv4Match[1];

      const prefix = Number(ipv4Match[2]);
      const mask = prefix === 0
        ? 0
        : (0xffffffff << (32 - prefix)) >>> 0;

      current.subnet = [24, 16, 8, 0]
        .map((shift) => (mask >>> shift) & 255)
        .join('.');
    }
  }

  if (current) interfaces.push(current);

  return interfaces;
};

// Format only the required network information
const formatIpDetails = (rawOutput) => {
  const interfaces = parseIpAddr(rawOutput);

  return interfaces
    .filter((item) => item.name !== 'lo')
    .map((item) => [
      `INTERFACE NAME : ${item.name}`,
      `IP ADDRESS     : ${item.ipv4 || 'Not assigned'}`,
      `MAC ADDRESS    : ${item.mac || 'Not available'}`,
      `SUBNET MASK    : ${item.subnet || 'Not available'}`,
    ].join('\n'))
    .join('\n\n');
};

export default function NetworkRuntime() {
  const { nodes, edges } = useTopologyStore();

  const [runtime, setRuntime] = useState({
    running: false,
    nodes: [],
    links: [],
    output: [],
  });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [output, setOutput] = useState('Backend not checked yet.');

  const [kind, setKind] = useState('link');
  const [element, setElement] = useState('');
  const [action, setAction] = useState('down');
  const [commandNode, setCommandNode] = useState('h1');
  const [command, setCommand] = useState('ip addr');

  const targets = useMemo(() => kind === 'link'
    ? edges.map((edge) => ({
        value: edge.id,
        label: `${edge.source} ↔ ${edge.target}`,
      }))
    : nodes
        .filter((node) => node.type !== 'controller')
        .map((node) => ({
          value: node.id,
          label: `${node.id} (${node.type})`,
        })),
    [kind, nodes, edges]
  );

  const refresh = async () => {
    try {
      const result = await backendApi.runtimeStatus();

      setRuntime(result);

      const base = formatOutput(result.output) ||
        (result.running ? 'Mininet is running.' : 'Mininet is stopped.');

      setOutput(
        `${base}\n\nRYU CONTROLLER STATE\n${JSON.stringify(
          result.controller_state || {},
          null,
          2
        )}`
      );
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!targets.some((t) => t.value === element)) {
      setElement(targets[0]?.value || '');
    }
  }, [targets, element]);

  useEffect(() => {
    if (!nodes.some((n) => n.id === commandNode && n.type !== 'controller')) {
      setCommandNode(
        nodes.find((n) => n.type !== 'controller')?.id || ''
      );
    }
  }, [nodes, commandNode]);

  const run = async (fn, isDiagnostic = false) => {
    setBusy(true);
    setError('');

    try {
      const result = await fn();
      const live = await backendApi.runtimeStatus();

      setRuntime(live);

      const base = formatOutput(result.output) ||
        JSON.stringify(result, null, 2);

      // Show only selected fields for ip addr
      if (isDiagnostic && command.trim() === 'ip addr') {
        setOutput(
          formatIpDetails(base) ||
          'No network interface information found.'
        );
      } else {
        setOutput(
          `${base}\n\nRYU CONTROLLER STATE\n${JSON.stringify(
            live.controller_state || {},
            null,
            2
          )}`
        );
      }

    } catch (e) {
      setError(e.message);
      setOutput(`ERROR: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const start = () => run(async () => {
    const result = await backendApi.runtimeStart(nodes, edges);

    return {
      ...result,
      output: [
        'Mininet started from current React Flow topology.',
        ...(result.output || []),
      ],
    };
  });

  const fail = () => run(() =>
    backendApi.setFailure(kind, element, action)
  );

  const ping = () => run(() =>
    backendApi.pingAll()
  );

  const execute = () => run(
    () => backendApi.runCommand(commandNode, command),
    true
  );

  return (
    <section className="content-section" id="live-mininet">

      <div className="section-header">
        <h2>Live Mininet Runtime</h2>
        <span className="section-desc">
          Execute the topology currently drawn in the editor
        </span>
      </div>

      <div className="card runtime-card">

        <div className="runtime-topline">
          <div>
            <b>Network state</b>
            <p className="muted">
              {runtime.running
                ? 'A real Mininet network is running in the Ubuntu VM.'
                : 'No Mininet network is currently running.'}
            </p>
          </div>

          <span className={`runtime-pill ${
            runtime.running ? 'is-running' : 'is-stopped'
          }`}>
            {runtime.running ? '● RUNNING' : '● STOPPED'}
          </span>
        </div>

        <div className="runtime-controller-state">
          <b>Ryu controller:</b>{' '}
          {runtime.controller_state?.running
            ? 'Controller process has reported state'
            : 'No controller state received'}

          <span>
            {' '}· Connected switches:{' '}
            {runtime.controller_state?.switch_count ?? 0}
          </span>

          {runtime.controller_state?.event && (
            <small> · {runtime.controller_state.event}</small>
          )}
        </div>

        <div className="runtime-actions">

          <button
            className="btn btn-primary"
            onClick={start}
            disabled={busy || runtime.running}
          >
            <Play size={15} /> Start current topology
          </button>

          <button
            className="btn btn-secondary"
            onClick={() => run(() => backendApi.runtimeStop())}
            disabled={busy || !runtime.running}
          >
            <Square size={15} /> Stop network
          </button>

          {/* PingAll button intentionally remains disabled */}

          <button
            className="btn btn-secondary"
            onClick={refresh}
            disabled={busy}
          >
            <RefreshCw size={15} /> Refresh
          </button>

        </div>

        <div className="runtime-grid">

          <div className="runtime-control-block">

            <h3><Unplug size={15} /> Inject failure / restore</h3>

            <label>
              Element type
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="link">Link</option>
                <option value="node">Device</option>
              </select>
            </label>

            <label>
              Target
              <select
                value={element}
                onChange={(e) => setElement(e.target.value)}
              >
                {targets.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Action
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                <option value="down">Fail / bring down</option>
                <option value="up">Restore / bring up</option>
              </select>
            </label>

            <button
              className="btn btn-secondary"
              onClick={fail}
              disabled={busy || !runtime.running || !element}
            >
              <Cable size={15} /> Apply to Mininet
            </button>

          </div>

          <div className="runtime-control-block">

            <h3><Terminal size={15} /> Run diagnostic command</h3>

            <label>
              Mininet node
              <select
                value={commandNode}
                onChange={(e) => setCommandNode(e.target.value)}
              >
                {nodes
                  .filter((n) => n.type !== 'controller')
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.id}
                    </option>
                  ))}
              </select>
            </label>

            <label>
              Command
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="ip addr"
              />
            </label>

            <button
              className="btn btn-secondary"
              onClick={execute}
              disabled={busy || !runtime.running || !commandNode}
            >
              <Terminal size={15} /> Execute command
            </button>

            <small>
              Allowed commands: ping, ip addr/route/link, ifconfig,
              route, arp, ethtool.
            </small>

          </div>

        </div>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <div className="runtime-output">

          <div className="runtime-output-head">
            <b>Backend / Mininet output</b>
            <span>{busy ? 'Working…' : 'Latest response'}</span>
          </div>

          <pre>{output}</pre>

        </div>

        <div className="runtime-note">
          Switches use OpenFlow 1.3 and connect to Ryu at
          127.0.0.1:6653 by default. The Ryu app writes switch
          connection and port-statistics state for this panel.
          Start Ryu before starting Mininet. The controller palette
          item is a logical marker; Ryu itself runs as a separate
          controller process.
        </div>

      </div>
    </section>
  );
}

