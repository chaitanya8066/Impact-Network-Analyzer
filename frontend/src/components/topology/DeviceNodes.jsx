import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { Cloud, Monitor, Network, RadioTower, Router, Server } from 'lucide-react';

const iconByType = {
  switch: Network,
  router: Router,
  host: Monitor,
  server: Server,
  controller: RadioTower,
  cloud: Cloud,
};

function PortHandles() {
  const sides = [
    ['top', Position.Top],
    ['right', Position.Right],
    ['bottom', Position.Bottom],
    ['left', Position.Left],
  ];
  return (
    <>
      {sides.map(([side, position]) => (
        <React.Fragment key={side}>
          <Handle id={`target-${side}`} type="target" position={position} className={`device-port port-${side}`} />
          <Handle id={`source-${side}`} type="source" position={position} className={`device-port port-${side}`} />
        </React.Fragment>
      ))}
    </>
  );
}

function DeviceNode({ data, type, selected }) {
  const Icon = iconByType[type] ?? Network;
  const isDown = data.status === 'down';
  const isCongested = data.status === 'congested';
  const statusLabel = isDown ? 'OFFLINE' : isCongested ? 'BUSY' : 'ONLINE';
  const interfaceCount = data.interfaces ?? (type === 'host' ? 2 : type === 'switch' ? 8 : 4);
  const detail = data.ip || (data.dpid ? `DPID ${data.dpid}` : data.openflow ? `OpenFlow ${data.openflow}` : data.status === 'down' ? 'Link unavailable' : 'Ready');

  return (
    <div className={`device-node device-card ${type} ${selected ? 'selected' : ''} ${isDown ? 'down' : ''} ${isCongested ? 'congested' : ''}`}>
      <PortHandles />
      <div className="device-card-top">
        <span className="device-kind"><Icon size={15} /> {type === 'host' ? (data.deviceKind || 'PC / HOST') : type.toUpperCase()}</span>
        <span className={`device-status ${isDown ? 'offline' : isCongested ? 'busy' : ''}`}>{statusLabel}</span>
      </div>
      <div className="device-card-name">{data.label || type}</div>
      <div className="device-card-detail">{detail}</div>
      <div className="device-card-footer"><span><i className={`device-dot ${isDown ? 'offline' : isCongested ? 'busy' : ''}`} /> {interfaceCount} interfaces</span><span>{data.openflow || 'Available'}</span></div>
    </div>
  );
}

export const nodeTypes = {
  switch: DeviceNode,
  router: DeviceNode,
  host: DeviceNode,
  server: DeviceNode,
  controller: DeviceNode,
  cloud: DeviceNode,
};
