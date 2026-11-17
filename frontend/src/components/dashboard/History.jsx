import React from 'react';
import { useTopologyStore } from '../../store/topologyStore.js';

export default function History() {
  const { history, clearHistory } = useTopologyStore();

  const handleClear = () => {
    if (window.confirm('Clear all analysis records from this session?')) clearHistory();
  };

  return (
    <section className="content-section">
      <div className="title-with-actions">
        <div>
          <h2>Analysis History</h2>
          <span className="section-desc">Simulation runs in this browser session</span>
        </div>
        <button className="btn btn-secondary btn-sm" type="button" onClick={handleClear} disabled={history.length === 0}>
          Clear History
        </button>
      </div>
      <div className="card history-table-container">
        <table className="history-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Component</th>
              <th>Condition</th>
              <th>Impact</th>
              <th>Network status</th>
              <th>SDN action</th>
            </tr>
          </thead>
          <tbody>
            {history.length > 0 ? history.map((item, index) => (
              <tr key={`${item.time}-${item.target}-${index}`}>
                <td>{item.time}</td>
                <td>{item.component} · {item.target}</td>
                <td>{item.condition}</td>
                <td>{item.impactLevel}</td>
                <td>{item.statusText}</td>
                <td>{item.failoverDesc}</td>
              </tr>
            )) : (
              <tr><td colSpan="6">No analysis history records present.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
