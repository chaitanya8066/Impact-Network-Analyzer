"""Impact analysis engine for the Impact Network Analyzer.

Pure NetworkX logic so it can be used by the Ryu controller, Flask dashboard,
or standalone tests.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Tuple, Any
import networkx as nx


@dataclass
class ImpactResult:
    failure_type: str
    failed_element: str
    total_nodes: int
    affected_nodes: List[str]
    affected_paths: List[Dict[str, Any]]
    disconnected_pairs: int
    total_pairs: int
    impact_score: float
    severity: str
    alternate_paths: Dict[str, List[str]]

    def to_dict(self):
        return asdict(self)


class ImpactAnalyzer:
    """Analyze the effect of a simulated or observed network failure."""

    def __init__(self, graph: nx.Graph):
        self.graph = nx.Graph(graph)

    @staticmethod
    def _pairs(nodes: Iterable[Any]):
        nodes = list(nodes)
        for i, src in enumerate(nodes):
            for dst in nodes[i + 1:]:
                yield src, dst

    def analyze(self, failure_type: str, failed_element: Any) -> ImpactResult:
        original = self.graph.copy()
        failed = original.copy()

        if failure_type == "link":
            if isinstance(failed_element, (list, tuple)) and len(failed_element) == 2:
                u, v = failed_element
            else:
                u, v = str(failed_element).split("-")
            u = self._resolve_node(u, original)
            v = self._resolve_node(v, original)
            failed_element_name = f"{u}-{v}"
            if failed.has_edge(u, v):
                failed.remove_edge(u, v)
        elif failure_type == "node":
            node = self._resolve_node(failed_element, original)
            failed_element_name = str(node)
            if failed.has_node(node):
                failed.remove_node(node)
        else:
            raise ValueError("failure_type must be 'link' or 'node'")

        nodes = list(original.nodes())
        affected = set()
        affected_paths = []
        disconnected = 0
        total_pairs = 0
        alternates = {}

        for src, dst in self._pairs(nodes):
            total_pairs += 1
            before = nx.has_path(original, src, dst)
            after = src in failed and dst in failed and nx.has_path(failed, src, dst)
            if before and not after:
                disconnected += 1
                affected.update((src, dst))
                affected_paths.append({"source": str(src), "destination": str(dst), "status": "disconnected"})
            elif before and after:
                try:
                    old_path = nx.shortest_path(original, src, dst)
                    new_path = nx.shortest_path(failed, src, dst)
                    if old_path != new_path:
                        affected.update((src, dst))
                        affected_paths.append({
                            "source": str(src), "destination": str(dst),
                            "status": "rerouted", "original_path": list(map(str, old_path)),
                            "new_path": list(map(str, new_path)),
                        })
                        alternates[f"{src}->{dst}"] = list(map(str, new_path))
                except nx.NetworkXNoPath:
                    pass

        if failure_type == "node" and failed_element_name in map(str, original.nodes()):
            affected.add(str(failed_element_name))

        # 70% connectivity impact + 30% affected-node ratio.
        pair_ratio = disconnected / total_pairs if total_pairs else 0.0
        node_ratio = len(affected) / len(nodes) if nodes else 0.0
        score = round((pair_ratio * 70 + node_ratio * 30), 2)
        if score >= 70:
            severity = "CRITICAL"
        elif score >= 40:
            severity = "HIGH"
        elif score >= 15:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        return ImpactResult(
            failure_type=failure_type,
            failed_element=failed_element_name,
            total_nodes=len(nodes),
            affected_nodes=sorted(map(str, affected)),
            affected_paths=affected_paths,
            disconnected_pairs=disconnected,
            total_pairs=total_pairs,
            impact_score=score,
            severity=severity,
            alternate_paths=alternates,
        )

    @staticmethod
    def _resolve_node(value, graph):
        if value in graph.nodes:
            return value
        text = str(value)
        if text in graph.nodes:
            return text
        try:
            numeric = int(text)
            if numeric in graph.nodes:
                return numeric
        except (ValueError, TypeError):
            pass
        return value


def analyze_edge_list(edges: List[Tuple[Any, Any]], failure_type: str, failed_element: Any):
    graph = nx.Graph()
    graph.add_edges_from(edges)
    return ImpactAnalyzer(graph).analyze(failure_type, failed_element).to_dict()
