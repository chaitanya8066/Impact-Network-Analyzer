function getOtherEnd(edge, nodeId) {
  if (edge.source === nodeId) return edge.target;
  if (edge.target === nodeId) return edge.source;
  return null;
}

function reachableFrom(startId, nodes, edges, excludedNodeId = null, excludedEdgeId = null) {
  if (!startId || startId === excludedNodeId) return new Set();
  const allowedNodeIds = new Set(nodes.map((node) => node.id).filter((id) => id !== excludedNodeId));
  if (!allowedNodeIds.has(startId)) return new Set();

  const visited = new Set([startId]);
  const queue = [startId];

  while (queue.length > 0) {
    const currentId = queue.shift();
    for (const edge of edges) {
      if (edge.id === excludedEdgeId || edge.data?.status === 'down') continue;
      const neighborId = getOtherEnd(edge, currentId);
      if (neighborId && allowedNodeIds.has(neighborId) && !visited.has(neighborId)) {
        visited.add(neighborId);
        queue.push(neighborId);
      }
    }
  }

  return visited;
}

function getSeverity(affectedCount, totalCount, component, condition) {
  if (condition === 'High Traffic') return 'Moderate';
  if (component === 'Host') return affectedCount > 1 ? 'High' : 'Low';
  if (affectedCount >= Math.max(3, Math.ceil(totalCount * 0.5))) return 'Critical';
  if (affectedCount >= 2) return 'High';
  if (affectedCount === 1) return 'Moderate';
  return 'Low';
}

/**
 * Rule-based graph simulation. This is a frontend prototype, not a live
 * Mininet/Ryu measurement. It works with any nodes and links in the editor.
 */
export function calculateImpact({ nodes, edges, component, condition, target }) {
  const targetNode = nodes.find((node) => node.id === target);
  const targetEdge = edges.find((edge) => edge.id === target);

  if (component === 'Link' && !targetEdge) {
    throw new Error('Select a valid link before running the analysis.');
  }
  if (component !== 'Link' && !targetNode) {
    throw new Error('Select a valid device before running the analysis.');
  }

  const switches = nodes.filter((node) => node.type === 'switch');
  const preferredRoot = switches.find((node) => node.id !== (component === 'Switch' ? target : null))
    ?? nodes.find((node) => node.id !== (component === 'Switch' ? target : null));

  let affectedNodeIds = [];
  let affectedEdgeIds = [];
  let congestedNodeIds = [];
  let congestedEdgeIds = [];
  let scenarioDesc = '';
  let failoverDesc = '';
  let affectedLinks = [];

  if (condition === 'High Traffic') {
    congestedNodeIds = [target];
    congestedEdgeIds = edges
      .filter((edge) => edge.source === target || edge.target === target)
      .map((edge) => edge.id);
    affectedLinks = edges
      .filter((edge) => congestedEdgeIds.includes(edge.id))
      .map((edge) => `${edge.source} ↔ ${edge.target}`);
    scenarioDesc = `Device ${target} is generating unusually high traffic. Adjacent links are marked for monitoring.`;
    failoverDesc = 'Prototype response: apply an OpenFlow meter or QoS rate limit to the selected device. No live controller command is sent.';
  } else if (component === 'Link') {
    const reachable = reachableFrom(preferredRoot?.id, nodes, edges, null, target);
    affectedEdgeIds = [target];
    affectedNodeIds = nodes
      .filter((node) => !reachable.has(node.id))
      .map((node) => node.id);
    affectedLinks = [targetEdge.data?.label || `${targetEdge.source} ↔ ${targetEdge.target}`];
    scenarioDesc = `Link ${targetEdge.source} ↔ ${targetEdge.target} is removed from the graph. The analyzer checks which devices are no longer reachable from ${preferredRoot?.id ?? 'the selected root'}.`;
    failoverDesc = affectedNodeIds.length
      ? `No alternate path was found for ${affectedNodeIds.join(', ')} in the current topology.`
      : 'The remaining graph stays connected from the selected root. Traffic can use the remaining paths.';
  } else if (component === 'Switch' || condition === 'Node Down') {
    const reachable = reachableFrom(preferredRoot?.id, nodes, edges, target, null);
    affectedNodeIds = [target, ...nodes
      .filter((node) => node.id !== target && !reachable.has(node.id))
      .map((node) => node.id)];
    affectedEdgeIds = edges
      .filter((edge) => edge.source === target || edge.target === target
        || affectedNodeIds.includes(edge.source) || affectedNodeIds.includes(edge.target))
      .map((edge) => edge.id);
    affectedLinks = edges
      .filter((edge) => affectedEdgeIds.includes(edge.id))
      .map((edge) => edge.data?.label || `${edge.source} ↔ ${edge.target}`);
    scenarioDesc = `Device ${target} is treated as offline. The graph traversal identifies devices that cannot be reached from ${preferredRoot?.id ?? 'the remaining network'}.`;
    failoverDesc = affectedNodeIds.length > 1
      ? `The current topology has no alternate path for: ${affectedNodeIds.filter((id) => id !== target).join(', ')}.`
      : 'No additional devices become isolated in this topology.';
  } else {
    affectedNodeIds = [target];
    congestedEdgeIds = edges
      .filter((edge) => edge.source === target || edge.target === target)
      .map((edge) => edge.id);
    affectedLinks = edges
      .filter((edge) => congestedEdgeIds.includes(edge.id))
      .map((edge) => edge.data?.label || `${edge.source} ↔ ${edge.target}`);
    scenarioDesc = `Host ${target} is treated as offline. Other connected devices remain available unless the topology indicates otherwise.`;
    failoverDesc = 'No controller rerouting is performed by this frontend-only simulation.';
  }

  const uniqueAffectedNodes = [...new Set(affectedNodeIds)];
  const impactLevel = getSeverity(uniqueAffectedNodes.length, nodes.length, component, condition);
  const levelClass = `tag-${impactLevel.toLowerCase()}`;
  const statusText = impactLevel === 'Critical' || impactLevel === 'High'
    ? 'Critical'
    : impactLevel === 'Moderate'
      ? 'Warning'
      : 'Degraded';

  return {
    component,
    condition,
    target,
    impactLevel,
    levelClass,
    affectedNodeIds: uniqueAffectedNodes,
    affectedNodes: uniqueAffectedNodes,
    affectedEdgeIds: [...new Set(affectedEdgeIds)],
    affectedLinks,
    congestedNodeIds,
    congestedEdgeIds,
    scenarioDesc,
    failoverDesc,
    statusText,
    postStatusLabel: condition === 'High Traffic'
      ? 'Warning - Traffic Monitoring Active'
      : `${statusText} - Simulated Impact`,
    statusPillClass: impactLevel === 'Critical' || impactLevel === 'High'
      ? 'status-red'
      : impactLevel === 'Moderate'
        ? 'status-yellow'
        : 'status-green',
    postBadge: impactLevel === 'Critical' || impactLevel === 'High'
      ? 'danger-badge'
      : impactLevel === 'Moderate'
        ? 'warning-badge'
        : 'low-badge',
  };
}
