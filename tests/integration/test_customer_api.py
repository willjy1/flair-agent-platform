from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_customer_support_page_and_capabilities():
    client = TestClient(create_app())
    support = client.get("/support")
    assert support.status_code == 200
    assert "Get help with your trip in one conversation." in support.text

    caps = client.get("/api/v1/customer/capabilities")
    assert caps.status_code == 200
    data = caps.json()
    assert data["customer_facing"] is True
    assert "what_it_can_help_with" in data
    assert "official_channel_snapshot" in data


def test_customer_capabilities_supports_hidden_tenant_profile():
    client = TestClient(create_app())
    resp = client.get("/api/v1/customer/capabilities?tenant=airline_template")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant"] == "airline_template"
    assert "Airline Support Agents" in data["product_name"]


def test_customer_message_returns_citations_and_next_steps():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-1",
            "customer_id": "cust-1",
            "channel": "web",
            "content": "I need wheelchair assistance for my flight",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "accessibility_agent"
    assert len(data.get("citations", [])) >= 1
    assert len(data.get("official_next_steps", [])) >= 1
    assert isinstance(data.get("customer_plan"), dict)
    assert len(data.get("self_service_options", [])) >= 1


def test_customer_followup_clarification_uses_session_context():
    client = TestClient(create_app())
    first = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-2",
            "customer_id": "cust-2",
            "channel": "web",
            "content": "I want a human agent now",
        },
    )
    assert first.status_code == 200

    follow = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-2",
            "customer_id": "cust-2",
            "channel": "web",
            "content": "what do you mean",
        },
    )
    assert follow.status_code == 200
    data = follow.json()
    assert data["agent"] == "clarification_layer"
    assert "previous step" in data["message"].lower()


def test_continue_channel_prepares_reference():
    client = TestClient(create_app())
    client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-3",
            "customer_id": "cust-3",
            "channel": "web",
            "content": "I need a refund for booking AB12CD",
        },
    )
    cont = client.post(
        "/api/v1/customer/continue-channel",
        json={
            "session_id": "cust-int-3",
            "customer_id": "cust-3",
            "from_channel": "web_chat",
            "to_channel": "phone",
        },
    )
    assert cont.status_code == 200
    data = cont.json()
    assert data["ok"] is True
    assert data["reference"].startswith("SUP-")


def test_customer_voice_transcribe_short_audio_returns_clear_error():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/voice/transcribe",
        json={"audio_base64": "AA==", "mime_type": "audio/webm"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] in {"audio_too_short", "transcription_failed", "stt_not_configured"}


def test_customer_voice_simulate_returns_customer_payload_shape():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/voice/simulate",
        json={
            "session_id": "voice-int-1",
            "customer_id": "cust-voice-1",
            "channel": "voice",
            "content": "What is the status of flight F81234?",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "voice"
    assert "message" in data
    assert "spoken_message" in data
    assert isinstance(data.get("customer_plan"), dict)


def test_customer_rebooking_followup_option_selection_executes_change():
    client = TestClient(create_app())
    first = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-rebook-1",
            "customer_id": "cust-1",
            "channel": "web",
            "content": "I need to rebook booking AB12CD because my flight is delayed",
        },
    )
    assert first.status_code == 200
    follow = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-int-rebook-1",
            "customer_id": "cust-1",
            "channel": "web",
            "content": "option 1",
        },
    )
    assert follow.status_code == 200
    data = follow.json()
    assert data["agent"] == "booking_agent"
    assert "rebooked" in data["message"].lower()


def test_customer_session_reset_endpoint_clears_conversation():
    client = TestClient(create_app())
    client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "cust-reset-1",
            "customer_id": "cust-r1",
            "channel": "web",
            "content": "I need a refund for booking AB12CD",
        },
    )
    reset = client.post(
        "/api/v1/customer/session/reset",
        json={"session_id": "cust-reset-1", "customer_id": "cust-r1", "channel": "web"},
    )
    assert reset.status_code == 200
    assert reset.json()["ok"] is True
