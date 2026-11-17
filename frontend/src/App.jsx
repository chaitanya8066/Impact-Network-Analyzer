import React from 'react';
import {
  Activity,
  AlertTriangle,
  History as HistoryIcon,
  Info,
  LayoutDashboard,
  Network,
} from 'lucide-react';
import TopologyEditor from './components/topology/TopologyEditor.jsx';
import PropertiesPanel from './components/topology/PropertiesPanel.jsx';
import ImpactAnalysis from './components/dashboard/ImpactAnalysis.jsx';
import History from './components/dashboard/History.jsx';
import NetworkRuntime from './components/dashboard/NetworkRuntime.jsx';
import { useTopologyStore } from './store/topologyStore.js';

const navigation = [
  ['dashboard', 'Overview', LayoutDashboard],
  ['topology', 'Network Topology', Network],
  ['live-mininet', 'Live Mininet', Activity],
  ['impact-analysis', 'Impact Analysis', Activity],
  ['network-status', 'Network Health', AlertTriangle],
  ['history', 'Analysis History', HistoryIcon],
  ['project-info', 'Project Info', Info],
];

export default function App() {
  const { nodes, edges, impact } = useTopologyStore();
  const switches = nodes.filter((node) => node.type === 'switch').length;
  const hosts = nodes.filter((node) => node.type === 'host').length;
  const activeLinks = edges.filter((edge) => edge.data?.status !== 'down').length;
  const networkStatus = impact?.statusText ?? 'Normal';

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">⚡</div>
          <div className="brand-text">
            <h2>Impact Analyzer</h2>
            <span className="badge prototype-badge">SDN Prototype v2.0</span>
          </div>
        </div>
        <nav className="nav-menu" aria-label="Main navigation">
          {navigation.map(([id, label, Icon]) => (
            <a key={id} href={`#${id}`} className="nav-item">
              <Icon size={17} /> {label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="project-tag">
            <span className="tag-title">Final Year Project</span>
            <span className="tag-sub">Mininet + Ryu + OpenFlow</span>
            <span className="student-note">React + Mininet + Ryu</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="top-header">
          <div>
            <h1>SDN Impact Analyzer</h1>
            <p className="subtitle">Software Defined Networking Failure &amp; Traffic Impact Assessment System</p>
          </div>
          <div className="scope-pill">React + Mininet · Live SDN</div>
        </header>

        <div className="banner-notice">
          <strong>SDN execution mode:</strong> The Live Mininet panel sends the current React Flow topology to the Ubuntu backend, which builds the Mininet network and connects Open vSwitch devices to Ryu over OpenFlow 1.3.
        </div>

        <section id="dashboard" className="content-section">
          <div className="section-header">
            <h2>Overview Dashboard</h2>
            <span className="section-desc">Live counts from the editable topology</span>
          </div>
          <div className="metrics-grid">
            {[
              ['Total Switches', switches],
              ['Total Hosts', hosts],
              ['Active Links', activeLinks],
              ['Network Status', networkStatus],
            ].map(([label, value]) => (
              <div className="card metric-card" key={label}>
                <span className="metric-title">{label}</span>
                <div className="metric-value">{value}</div>
              </div>
            ))}
          </div>
        </section>

        <section id="topology" className="content-section">
          <div className="section-header">
            <h2>Network Topology Editor</h2>
            <span className="section-desc">Drag devices, connect ports, and configure network components.</span>
          </div>
          <div className="card topology-container">
            <div className="editor-with-inspector">
              <TopologyEditor />
              <PropertiesPanel />
            </div>
            <div className="topology-hint">Save and load your topology as JSON. Select a device to edit its properties.</div>
          </div>
        </section>

        <NetworkRuntime />

        <section id="impact-analysis" className="content-section">
          <div className="section-header">
            <h2>Impact Analysis Simulation</h2>
            <span className="section-desc">Graph-based, rule-driven simulation for the current topology.</span>
          </div>
          <ImpactAnalysis />
        </section>

        <section id="network-status" className="content-section">
          <div className="section-header"><h2>Network Health Reference</h2></div>
          <div className="status-cards-grid">
            {[
              ['Normal', 'All simulated devices and links are reachable.'],
              ['Warning', 'A moderate impact or traffic condition is present.'],
              ['Critical', 'A major failure or network partition is simulated.'],
            ].map(([name, description]) => (
              <div className="card status-tier-card" key={name}>
                <h3>{name}</h3>
                <p>{description}</p>
              </div>
            ))}
          </div>
        </section>

        <div id="history"><History /></div>

        <section id="project-info" className="content-section">
          <div className="section-header"><h2>Project Scope &amp; Architecture</h2></div>
          <div className="card info-card">
            <p>The React frontend exports its editable nodes and links as JSON. The Flask backend validates that JSON and dynamically creates the corresponding Mininet hosts, Linux routers and Open vSwitch switches.</p>
            <p><strong>Control plane:</strong> Open vSwitch connects to the separate Ryu OpenFlow 1.3 controller. The included Ryu app provides MAC-learning forwarding and reports switch/port events in its terminal.</p>
            <p><strong>Live results:</strong> Mininet command output, pingAll packet loss and injected link/device failures are returned to the Live Mininet panel. NetworkX impact analysis remains a separate graph-based analysis view.</p>
          </div>
        </section>

        <footer className="app-footer">SDN Impact Analyzer · React + Vite + React Flow</footer>
      </main>
    </div>
  );
}
