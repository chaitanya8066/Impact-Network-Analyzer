import React from 'react';
import { useTopologyStore } from '../../store/topologyStore.js';

export default function PropertiesPanel() {
  const { nodes, selectedNode, updateNodeData } = useTopologyStore();
  const node = nodes.find((item) => item.id === selectedNode);

  if (!node) {
    return (
      <aside className="properties-panel">
        <h3>Device Properties</h3>
        <p className="muted">Select a device on the canvas to inspect and configure it.</p>
      </aside>
    );
  }

  const update = (key, value) => updateNodeData(node.id, { [key]: value });

  return (
    <aside className="properties-panel">
      <h3>Device Properties</h3>
      <div className="property-id">{node.id}</div>
      <label>
        Device label
        <input value={node.data.label ?? ''} onChange={(event) => update('label', event.target.value)} />
      </label>
      <label>
        Status
        <select value={node.data.status ?? 'active'} onChange={(event) => update('status', event.target.value)}>
          <option value="active">Active</option>
          <option value="down">Down</option>
          <option value="congested">Congested</option>
        </select>
      </label>
      {node.type === 'host' && (
        <label>
          IP address
          <input value={node.data.ip ?? ''} onChange={(event) => update('ip', event.target.value)} />
        </label>
      )}
      {node.type === 'switch' && (
        <>
          <label>
            Datapath ID
            <input value={node.data.dpid ?? ''} onChange={(event) => update('dpid', event.target.value)} />
          </label>
          <label>
            OpenFlow version
            <select value={node.data.openflow ?? '1.3'} onChange={(event) => update('openflow', event.target.value)}>
              <option value="1.0">1.0</option>
              <option value="1.3">1.3</option>
              <option value="1.4">1.4</option>
            </select>
          </label>
        </>
      )}
    </aside>
  );
}
