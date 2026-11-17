import React, { useCallback, useRef, useState } from 'react';
import {
  Background, Controls, MiniMap, Panel, ReactFlow, ReactFlowProvider, useReactFlow,
} from '@xyflow/react';
import { Cable, Maximize2, RotateCcw, Save, Trash2, Upload, Network, Monitor, Router, Server, RadioTower, Cloud, Cable as CableIcon } from 'lucide-react';
import { nodeTypes } from './DeviceNodes.jsx';
import { useTopologyStore } from '../../store/topologyStore.js';
import { backendApi } from '../../services/backendApi.js';

const devices = [
  ['switch', 'OpenFlow Switch', Network],
  ['router', 'Router', Router],
  ['host', 'PC / Host', Monitor],
  ['server', 'Server', Server],
  ['controller', 'SDN Controller', RadioTower],
  ['cloud', 'Cloud', Cloud],
];
const cables = [
  ['ethernet', 'Ethernet', '1 Gbps', '#34d399', 'Standard host access cable'],
  ['fiber', 'Fiber optic', '10 Gbps', '#67e8f9', 'High-speed switch backbone'],
  ['openflow', 'OpenFlow control', 'Control', '#c084fc', 'Controller-to-switch control channel'],
];

function PaletteItem({ kind, label, Icon }) {
  const onDragStart = (event) => {
    event.dataTransfer.setData('application/sdn-device', kind);
    event.dataTransfer.effectAllowed = 'move';
  };
  return <div className="palette-item device-palette-item" draggable onDragStart={onDragStart}><span className="palette-glyph"><Icon size={16} /></span><span>{label}</span><span className="drag-mark">⠿</span></div>;
}

function CanvasContents() {
  const fileInputRef = useRef(null);
  const { screenToFlowPosition, fitView } = useReactFlow();
  const store = useTopologyStore();
  const { nodes, edges, selectedNode } = store;
  const [activeTab, setActiveTab] = useState('devices');
  const [selectedCable, setSelectedCable] = useState('ethernet');

  const onDrop = useCallback((event) => {
    event.preventDefault();
    const kind = event.dataTransfer.getData('application/sdn-device');
    if (!kind) return;
    store.addDevice(kind, screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  }, [screenToFlowPosition, store.addDevice]);

  const saveTopology = async () => {
    try {
      await backendApi.saveTopology(nodes, edges);
      window.alert('Topology saved to Flask backend.');
    } catch (error) {
      window.alert(`Backend save failed: ${error.message}`);
      return;
    }
    const payload = JSON.stringify({ nodes, edges }, null, 2);
    const blobUrl = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = 'sdn-topology.json';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(blobUrl);
  };

  const loadTopology = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      store.loadTopology(parsed.nodes, parsed.edges);
      window.alert('Topology loaded successfully.');
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Could not load this topology file.');
    } finally { event.target.value = ''; }
  };

  return (
    <div className="editor-layout">
      <aside className="device-palette cable-library">
        <h3>Device & Cable Library</h3>
        <p>Drag devices to the workspace. Choose a cable, then connect device ports.</p>
        <div className="library-tabs">
          <button className={activeTab === 'devices' ? 'active' : ''} onClick={() => setActiveTab('devices')} type="button">Devices ({devices.length})</button>
          <button className={activeTab === 'cables' ? 'active' : ''} onClick={() => setActiveTab('cables')} type="button">Cables ({cables.length})</button>
        </div>
        {activeTab === 'devices' ? (
          <div className="library-list">{devices.map(([kind, label, Icon]) => <PaletteItem key={kind} kind={kind} label={label} Icon={Icon} />)}</div>
        ) : (
          <div className="library-list">{cables.map(([kind, label, speed, color, description]) => (
            <button type="button" key={kind} className={`cable-choice ${selectedCable === kind ? 'selected' : ''}`} onClick={() => setSelectedCable(kind)}>
              <span className="cable-swatch" style={{ background: color }} /><span className="cable-choice-copy"><b>{label}</b><small>{speed} · {description}</small></span>{selectedCable === kind && <span className="cable-check">✓</span>}
            </button>
          ))}</div>
        )}
        <div className="selected-cable-note"><Cable size={15} /> Active cable: <b>{cables.find(([kind]) => kind === selectedCable)?.[1]}</b></div>
        <div className="palette-note">Cable workflow: choose a cable type, then drag from a small port on one device to a port on another device.</div>
      </aside>

      <div className="canvas-shell" onDrop={onDrop} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }}>
        <div className="canvas-toolbar">
          <span><b>SDN Topology Workspace</b><small>{nodes.length} devices · {edges.length} links · OpenFlow 1.3 simulation</small></span>
          <div className="toolbar-actions">
            <button type="button" onClick={() => fitView({ padding: 0.2 })}><Maximize2 size={14} /> Fit</button>
            <button type="button" onClick={saveTopology}><Save size={14} /> Save</button>
            <button type="button" onClick={() => fileInputRef.current?.click()}><Upload size={14} /> Load</button>
            <input ref={fileInputRef} hidden type="file" accept="application/json,.json" onChange={loadTopology} />
            <button type="button" onClick={() => { store.deleteSelected(); store.resetImpact(); }} disabled={!selectedNode}><Trash2 size={14} /> Delete</button>
            <button type="button" onClick={() => store.resetTopology()}><RotateCcw size={14} /> Reset</button>
          </div>
        </div>
        <div className="cable-mode-strip"><CableIcon size={15} /> <span>Connection mode:</span> <b>{cables.find(([kind]) => kind === selectedCable)?.[1]}</b> <small>— drag from a port to create a wire</small></div>
        <ReactFlow
          nodes={nodes} edges={edges} nodeTypes={nodeTypes}
          onNodesChange={store.onNodesChange} onEdgesChange={store.onEdgesChange}
          onConnect={(connection) => store.onConnect(connection, selectedCable)}
          onNodeClick={(_, node) => store.selectNode(node.id)} onPaneClick={() => store.selectNode(null)}
          fitView fitViewOptions={{ padding: 0.18 }} snapToGrid snapGrid={[15, 15]}
          deleteKeyCode={null} defaultEdgeOptions={{ type: 'smoothstep', interactionWidth: 18 }}
          connectionLineStyle={{ stroke: '#67e8f9', strokeWidth: 3 }}
        >
          <Background color="#26374c" gap={24} size={1} />
          <Controls />
          <MiniMap pannable zoomable nodeColor={(node) => node.type === 'switch' ? '#3b82f6' : node.type === 'host' ? '#10b981' : '#8b5cf6'} />
          <Panel position="bottom-left" className="canvas-tip">Select a device to edit · Select a cable to inspect · Drag devices from the library</Panel>
        </ReactFlow>
      </div>
    </div>
  );
}

export default function TopologyEditor() {
  return <ReactFlowProvider><CanvasContents /></ReactFlowProvider>;
}
