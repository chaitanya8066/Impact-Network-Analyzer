const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
  } catch {
    throw new Error(`Cannot reach the SDN backend at ${API_BASE}. Start Flask and check VITE_API_URL.`);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Backend request failed (${response.status}).`);
  return data;
}

const post = (path, body = {}) => request(path, { method: 'POST', body: JSON.stringify(body) });

export const backendApi = {
  health: () => request('/api/health'),
  getTopology: () => request('/api/topology'),
  saveTopology: (nodes, edges) => post('/api/topology', { nodes, edges }),
  analyze: (failureType, failedElement) => post('/api/analyze', { failure_type: failureType, failed_element: failedElement }),
  reset: () => post('/api/reset'),
  runtimeStart: (nodes, edges) => post('/api/runtime/start', { nodes, edges }),
  runtimeStop: () => post('/api/runtime/stop'),
  runtimeStatus: () => request('/api/runtime/status'),
  pingAll: () => post('/api/runtime/pingall'),
  runCommand: (node, command) => post('/api/runtime/command', { node, command }),
  setFailure: (kind, element, action) => post('/api/runtime/failure', { kind, element, action }),
};

export { API_BASE };
