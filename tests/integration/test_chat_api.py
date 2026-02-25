from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_chat_message_endpoint_end_to_end():
    app = create_app()
    client = TestClient(app)

    payload = {
        "session_id": "api-s1",
        "customer_id": "cust-1",
        "channel": "web",
        "content": "I need to rebook booking AB12CD because my flight is delayed",
    }
    resp = client.post("/api/v1/chat/message", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == "api-s1"
    assert data["agent"] in {"booking_agent", "disruption_agent"}
    assert "response_text" in data

    history = client.get("/api/v1/chat/history/api-s1")
    assert history.status_code == 200
    history_json = history.json()
    assert history_json["session_id"] == "api-s1"
    assert len(history_json["history"]) >= 2


def test_health_endpoint():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "flair-agent-platform"
    assert "stt_available" in data
    assert "tts_available" in data
