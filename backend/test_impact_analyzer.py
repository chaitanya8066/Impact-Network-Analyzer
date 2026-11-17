import networkx as nx
from impact_analyzer import ImpactAnalyzer


def test_link_failure_on_ring_reroutes():
    g = nx.cycle_graph(["1", "2", "3", "4", "5", "6"])
    result = ImpactAnalyzer(g).analyze("link", "1-2")
    assert result.severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert result.disconnected_pairs == 0
    assert result.alternate_paths


def test_node_failure_disconnects_ring_hosts():
    g = nx.cycle_graph(["1", "2", "3", "4", "5", "6"])
    result = ImpactAnalyzer(g).analyze("node", "1")
    assert result.disconnected_pairs > 0
    assert "1" in result.affected_nodes
