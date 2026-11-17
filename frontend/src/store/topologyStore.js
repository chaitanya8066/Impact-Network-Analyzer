import { create } from 'zustand';
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from '@xyflow/react';

const makeInitialNodes = () => [
  {
    id: 's1',
    type: 'switch',
    position: { x: 430, y: 70 },
    data: { label: 's1 · Core Switch', dpid: '0001', openflow: '1.3', status: 'active' },
  },
  {
    id: 's2',
    type: 'switch',
    position: { x: 180, y: 270 },
    data: { label: 's2 · Aggregation 1', dpid: '0002', openflow: '1.3', status: 'active' },
  },
  {
    id: 's3',
    type: 'switch',
    position: { x: 680, y: 270 },
    data: { label: 's3 · Aggregation 2', dpid: '0003', openflow: '1.3', status: 'active' },
  },
  ...[1, 2, 3, 4].map((number) => ({
    id: `h${number}`,
    type: 'host',
    position: { x: 70 + (number - 1) * 225, y: 520 },
    data: { label: `h${number} · Host ${number}`, ip: `10.0.0.${number}`, status: 'active' },
  })),
];

const makeInitialEdges = () => [
  {
    id: 'link-s1-s2', source: 's1', target: 's2', type: 'smoothstep',
    label: 'FIBER OPTIC · 10 Gbps', labelStyle: { fill: '#c4f1ff', fontSize: 10, fontWeight: 700 },
    labelBgStyle: { fill: '#102b42', fillOpacity: 0.95 }, labelBgPadding: [7, 4], labelBgBorderRadius: 5,
    style: { stroke: '#67e8f9', strokeWidth: 3 },
    data: { status: 'active', cableType: 'fiber', label: 'Fiber optic 10 Gbps · s1 ↔ s2' },
  },
  {
    id: 'link-s2-h1', source: 's2', target: 'h1', type: 'smoothstep',
    label: 'ETHERNET · 1 Gbps', labelStyle: { fill: '#d1fae5', fontSize: 10, fontWeight: 700 },
    labelBgStyle: { fill: '#12352e', fillOpacity: 0.95 }, labelBgPadding: [7, 4], labelBgBorderRadius: 5,
    style: { stroke: '#34d399', strokeWidth: 3 },
    data: { status: 'active', cableType: 'ethernet', label: 'Ethernet 1 Gbps · s2 ↔ h1' },
  },
  ['s1', 's3'], ['s2', 's3'], ['s2', 'h2'], ['s3', 'h3'], ['s3', 'h4'],
].map((item, index) => {
  if (!Array.isArray(item)) return item;
  const [source, target] = item;
  return {
    id: `link-${source}-${target}`, source, target, type: 'smoothstep',
    label: 'ETHERNET · 1 Gbps', labelStyle: { fill: '#cbd5e1', fontSize: 9 },
    labelBgStyle: { fill: '#172033', fillOpacity: 0.9 }, labelBgPadding: [5, 3], labelBgBorderRadius: 4,
    style: { stroke: '#94a3b8', strokeWidth: 2 },
    data: { status: 'active', cableType: 'ethernet', label: `${source} ↔ ${target}` },
  };
});

function nextDeviceId(nodes, kind) {
  const prefixByType = {
    switch: 's',
    router: 'r',
    host: 'h',
    server: 'srv',
    controller: 'c',
    cloud: 'cloud',
  };
  const prefix = prefixByType[kind] ?? 'device';
  let index = 1;
  let candidate = `${prefix}${index}`;
  while (nodes.some((node) => node.id === candidate)) {
    index += 1;
    candidate = `${prefix}${index}`;
  }
  return candidate;
}

function normalizeImportedTopology(nodes, edges) {
  if (!Array.isArray(nodes) || !Array.isArray(edges)) {
    throw new Error('Topology file must contain nodes and edges arrays.');
  }

  const validNodes = nodes.map((node, index) => {
    if (!node || typeof node.id !== 'string' || !node.id.trim()) {
      throw new Error(`Node at position ${index + 1} has no valid id.`);
    }
    if (!node.position || !Number.isFinite(node.position.x) || !Number.isFinite(node.position.y)) {
      throw new Error(`Node ${node.id} has an invalid position.`);
    }
    return {
      ...node,
      type: node.type || 'switch',
      data: { label: node.data?.label || node.id, status: 'active', ...node.data },
    };
  });

  const nodeIds = new Set(validNodes.map((node) => node.id));
  const validEdges = edges.map((edge, index) => {
    if (!edge || !nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      throw new Error(`Link at position ${index + 1} refers to a missing node.`);
    }
    return {
      ...edge,
      id: edge.id || `link-${edge.source}-${edge.target}-${index + 1}`,
      type: edge.type || 'smoothstep',
      data: { status: 'active', ...edge.data },
      animated: false,
      style: undefined,
    };
  });

  return { nodes: validNodes, edges: validEdges };
}

export const useTopologyStore = create((set, get) => ({
  nodes: makeInitialNodes(),
  edges: makeInitialEdges(),
  selectedNode: null,
  impact: null,
  history: [],

  onNodesChange: (changes) => set((state) => ({
    nodes: applyNodeChanges(changes, state.nodes),
  })),

  onEdgesChange: (changes) => set((state) => ({
    edges: applyEdgeChanges(changes, state.edges),
  })),

  onConnect: (connection, cableType = 'ethernet') => set((state) => {
    const alreadyConnected = state.edges.some((edge) => (
      (edge.source === connection.source && edge.target === connection.target)
      || (edge.source === connection.target && edge.target === connection.source)
    ));
    if (alreadyConnected || !connection.source || !connection.target) return state;

    const id = `link-${connection.source}-${connection.target}`;
    const cable = cableType === 'fiber'
      ? { label: 'FIBER OPTIC · 10 Gbps', stroke: '#67e8f9', color: '#c4f1ff' }
      : cableType === 'openflow'
        ? { label: 'OPENFLOW · CONTROL', stroke: '#c084fc', color: '#e9d5ff' }
        : { label: 'ETHERNET · 1 Gbps', stroke: '#34d399', color: '#d1fae5' };
    return {
      edges: addEdge({
        ...connection, id, type: 'smoothstep',
        label: cable.label, labelStyle: { fill: cable.color, fontSize: 10, fontWeight: 700 },
        labelBgStyle: { fill: '#102033', fillOpacity: 0.95 }, labelBgPadding: [7, 4], labelBgBorderRadius: 5,
        style: { stroke: cable.stroke, strokeWidth: 3 },
        data: { status: 'active', cableType, label: `${cable.label} · ${connection.source} ↔ ${connection.target}` },
      }, state.edges),
    };
  }),

  addDevice: (kind, position) => set((state) => {
    const id = nextDeviceId(state.nodes, kind);
    const data = {
      label: `${id} · ${kind.charAt(0).toUpperCase()}${kind.slice(1)}`,
      status: 'active',
    };
    if (kind === 'host') data.ip = `10.0.0.${state.nodes.filter((node) => node.type === 'host').length + 10}`;
    if (kind === 'switch') {
      data.dpid = String(state.nodes.filter((node) => node.type === 'switch').length + 1).padStart(4, '0');
      data.openflow = '1.3';
    }
    return {
      nodes: [...state.nodes, { id, type: kind, position, data }],
      selectedNode: id,
    };
  }),

  selectNode: (id) => set({ selectedNode: id }),

  updateNodeData: (id, patch) => set((state) => ({
    nodes: state.nodes.map((node) => (
      node.id === id ? { ...node, data: { ...node.data, ...patch } } : node
    )),
  })),

  deleteSelected: () => set((state) => {
    if (!state.selectedNode) return state;
    return {
      nodes: state.nodes.filter((node) => node.id !== state.selectedNode),
      edges: state.edges.filter((edge) => edge.source !== state.selectedNode && edge.target !== state.selectedNode),
      selectedNode: null,
      impact: null,
    };
  }),

  setImpact: (impact) => set((state) => {
    const affectedNodeIds = new Set(impact?.affectedNodeIds ?? []);
    const affectedEdgeIds = new Set(impact?.affectedEdgeIds ?? []);
    const congestedNodeIds = new Set(impact?.congestedNodeIds ?? []);
    const congestedEdgeIds = new Set(impact?.congestedEdgeIds ?? []);

    return {
      impact,
      nodes: state.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          status: affectedNodeIds.has(node.id)
            ? 'down'
            : congestedNodeIds.has(node.id)
              ? 'congested'
              : 'active',
        },
      })),
      edges: state.edges.map((edge) => ({
        ...edge,
        data: {
          ...edge.data,
          status: affectedEdgeIds.has(edge.id) ? 'down' : congestedEdgeIds.has(edge.id) ? 'congested' : 'active',
        },
        animated: affectedEdgeIds.has(edge.id),
        style: affectedEdgeIds.has(edge.id)
          ? { stroke: '#ef4444', strokeWidth: 3 }
          : congestedEdgeIds.has(edge.id)
            ? { stroke: '#f59e0b', strokeWidth: 3 }
            : undefined,
      })),
    };
  }),

  addHistory: (record) => set((state) => ({ history: [record, ...state.history] })),
  clearHistory: () => set({ history: [] }),

  resetImpact: () => set((state) => ({
    impact: null,
    nodes: state.nodes.map((node) => ({ ...node, data: { ...node.data, status: 'active' } })),
    edges: state.edges.map((edge) => ({
      ...edge,
      data: { ...edge.data, status: 'active' },
      animated: false,
      style: undefined,
    })),
  })),

  loadTopology: (nodes, edges) => {
    const topology = normalizeImportedTopology(nodes, edges);
    set({ ...topology, selectedNode: null, impact: null });
  },

  resetTopology: () => set({
    nodes: makeInitialNodes(),
    edges: makeInitialEdges(),
    selectedNode: null,
    impact: null,
  }),
}));
