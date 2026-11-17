import json
import networkx as nx
import dashboard


def test_api_health_and_topology(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "DESIGN_STATE_FILE", tmp_path / "designer.json")
    monkeypatch.setattr(dashboard, "LIVE_STATE_FILE", tmp_path / "missing.json")
    client = dashboard.app.test_client()
    assert client.get("/api/health").status_code == 200
    payload = {
        "nodes": [
            {"id": "h1", "type": "host", "data": {"label": "Host 1"}},
            {"id": "s1", "type": "switch", "data": {"label": "Switch 1"}},
            {"id": "srv1", "type": "server", "data": {"label": "Server"}},
        ],
        "edges": [
            {"id": "e1", "source": "h1", "target": "s1", "data": {"cableType": "ethernet"}},
            {"id": "e2", "source": "s1", "target": "srv1", "data": {"cableType": "fiber"}},
        ],
    }
    saved = client.post("/api/topology", json=payload)
    assert saved.status_code == 200
    assert saved.get_json()["counts"] == {"devices": 3, "links": 2}
    assert client.get("/api/topology").get_json()["counts"]["links"] == 2
    result = client.post("/api/analyze", json={"failure_type": "link", "failed_element": {"source": "h1", "target": "s1"}})
    assert result.status_code == 200
    assert result.get_json()["disconnected_pairs"] > 0
