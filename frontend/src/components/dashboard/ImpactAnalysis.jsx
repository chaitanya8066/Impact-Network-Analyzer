import React, { useEffect, useMemo, useState } from 'react';
import { backendApi } from '../../services/backendApi.js';
import { useTopologyStore } from '../../store/topologyStore.js';

const conditionsByComponent = {
  Switch: ['Switch Failure'],
  Host: ['Node Failure'],
  Router: ['Node Failure'],
  Server: ['Node Failure'],
  Link: ['Link Failure'],
};

function ImpactResult({ result }) {
  return (
    <div className="results-output-state">
      <span className={`summary-level-tag ${String(result.severity).toLowerCase()}`}>{result.severity} IMPACT</span>
      <h4>{result.failure_type === 'link' ? 'Link Failure' : 'Node Failure'} · {result.failed_element}</h4>
      <p>Impact score: <b>{result.impact_score}/100</b></p>
      <p>{result.disconnected_pairs} of {result.total_pairs} device pairs became disconnected.</p>
      <h4>Affected devices</h4>
      <p>{result.affected_nodes?.length ? result.affected_nodes.join(', ') : 'None'}</p>
      <h4>Affected paths</h4>
      {result.affected_paths?.length ? (
        <ul>{result.affected_paths.map((path, index) => (
          <li key={`${path.source}-${path.destination}-${index}`}>
            {path.source} → {path.destination}: {path.status}
            {path.new_path ? ` (${path.new_path.join(' → ')})` : ''}
          </li>
        ))}</ul>
      ) : <p>No additional paths affected.</p>}
      <h4>Alternate paths</h4>
      <pre>{JSON.stringify(result.alternate_paths || {}, null, 2)}</pre>
      <p className="simulation-disclaimer">Analysis returned by the Flask + NetworkX backend. Live Mininet/Ryu operation requires the SDN environment to be running.</p>
    </div>
  );
}

function toUiImpact(result, edges, failureType, failedElement) {
  const affectedNodes = new Set((result.affected_nodes || []).map(String));
  const affectedEdgeIds = new Set();
  const addPathEdges = (path) => {
    for (let i = 0; i < path.length - 1; i += 1) {
      const match = edges.find((edge) =>
        (edge.source === path[i] && edge.target === path[i + 1]) ||
        (edge.source === path[i + 1] && edge.target === path[i])
      );
      if (match) affectedEdgeIds.add(match.id);
    }
  };
  (result.affected_paths || []).forEach((path) => {
    if (path.original_path) addPathEdges(path.original_path);
    if (path.new_path) addPathEdges(path.new_path);
  });
  if (failureType === 'link') {
    const failed = edges.find((edge) => edge.id === failedElement);
    if (failed) affectedEdgeIds.add(failed.id);
  }
  return {
    ...result,
    affectedNodeIds: [...affectedNodes],
    affectedEdgeIds: [...affectedEdgeIds],
    congestedNodeIds: [],
    congestedEdgeIds: [],
  };
}

export default function ImpactAnalysis() {
  const { nodes, edges, selectedNode, impact, setImpact, addHistory, resetImpact } = useTopologyStore();
  const [component, setComponent] = useState('Switch');
  const [target, setTarget] = useState('s1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [backendStatus, setBackendStatus] = useState('checking');

  useEffect(() => {
    backendApi.health()
      .then(() => setBackendStatus('connected'))
      .catch(() => setBackendStatus('offline'));
  }, []);

  const targets = useMemo(() => {
    if (component === 'Link') return edges.map((edge) => edge.id);
    const type = component.toLowerCase();
    return nodes.filter((node) => node.type === type).map((node) => node.id);
  }, [component, nodes, edges]);

  useEffect(() => {
    if (!targets.includes(target)) setTarget(targets[0] || '');
  }, [targets, target]);

  useEffect(() => {
    if (!selectedNode) return;
    const selected = nodes.find((node) => node.id === selectedNode);
    if (!selected) return;
    const componentByType = { switch: 'Switch', host: 'Host', router: 'Router', server: 'Server' };
    const next = componentByType[selected.type];
    if (next) {
      setComponent(next);
      setTarget(selected.id);
    }
  }, [selectedNode, nodes]);

  const runAnalysis = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      // Keep backend graph synchronized with the editable React Flow topology.
      await backendApi.saveTopology(nodes, edges);
      const failureType = component === 'Link' ? 'link' : 'node';
      let failedElement = target;
      if (failureType === 'link') {
        const edge = edges.find((item) => item.id === target);
        if (!edge) throw new Error('Select a valid link in the topology.');
        failedElement = { source: edge.source, target: edge.target };
      }
      const backendResult = await backendApi.analyze(failureType, failedElement);
      const uiImpact = toUiImpact(backendResult, edges, failureType, target);
      setImpact(uiImpact);
      addHistory({
        time: new Date().toLocaleString(),
        component,
        target,
        condition: failureType === 'link' ? 'Link Failure' : 'Node Failure',
        impactLevel: backendResult.severity,
        statusText: `${backendResult.impact_score}/100 · ${backendResult.disconnected_pairs} disconnected pairs`,
        failoverDesc: Object.keys(backendResult.alternate_paths || {}).length
          ? 'Alternate paths were found by the NetworkX analyzer.'
          : 'No alternate path was found for the affected pairs.',
      });
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : 'Backend analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleComponentChange = (value) => {
    setComponent(value);
    const next = value === 'Link'
      ? edges[0]?.id
      : nodes.find((node) => node.type === value.toLowerCase())?.id;
    setTarget(next || '');
    setError('');
  };

  return (
    <div className="analysis-wrapper">
      <form className="card analysis-form-card" onSubmit={runAnalysis}>
        <h3 className="card-title">Backend Failure Analysis</h3>
        <p className="form-instructions">The React topology is sent to Flask; NetworkX calculates connectivity impact.</p>
        <p className={`backend-connection-state ${backendStatus}`}>
          Backend: {backendStatus === 'connected' ? 'Connected · Flask API' : backendStatus === 'checking' ? 'Checking…' : 'Offline · start backend'}
        </p>
        <label>
          Component type
          <select className="form-control" value={component} onChange={(event) => handleComponentChange(event.target.value)}>
            <option value="Switch">OpenFlow Switch</option>
            <option value="Host">Host</option>
            <option value="Router">Linux Router</option>
            <option value="Server">Server</option>
            <option value="Link">Network Link</option>
          </select>
        </label>
        <label>
          Failure scenario
          <select className="form-control" value={component === 'Link' ? 'Link Failure' : 'Node Failure'} disabled>
            <option>{component === 'Link' ? 'Link Failure' : 'Node Failure'}</option>
          </select>
        </label>
        <label>
          Target
          <select className="form-control" required value={target} onChange={(event) => setTarget(event.target.value)}>
            {targets.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="form-actions">
          <button className="btn btn-primary" type="submit" disabled={loading || !target || !targets.length || backendStatus === 'offline'}>
            {loading ? 'Contacting backend…' : '⚡ Analyze with SDN Backend'}
          </button>
          <button className="btn btn-secondary" type="button" onClick={() => { resetImpact(); setError(''); }}>
            Reset Result
          </button>
        </div>
      </form>
      <div className="card analysis-results-card" aria-live="polite">
        <h3 className="card-title">NetworkX Analysis Results</h3>
        {loading ? <p>Sending topology to Flask and analyzing failure…</p>
          : impact ? <ImpactResult result={impact} />
            : <p className="muted">No active backend analysis. Start Flask, then select a failure scenario.</p>}
      </div>
    </div>
  );
}
