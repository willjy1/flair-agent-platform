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


def test_customer_capabilities_supports_frontier_tenant_profile():
    client = TestClient(create_app())
    resp = client.get("/api/v1/customer/capabilities?tenant=frontier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant"] == "frontier"
    assert "Frontier" in data["product_name"]
    assert isinstance(data.get("branding"), dict)
    assert data["branding"]["brand_name"].lower().startswith("frontier")


def test_support_frontier_route_serves_customer_page():
    client = TestClient(create_app())
    resp = client.get("/support/frontier")
    assert resp.status_code == 200
    assert "customer_support.js" in resp.text


def test_support_additional_tenants_routes_serve_customer_page():
    client = TestClient(create_app())
    for slug in ["progressive", "aetna", "dukeenergy", "xfinity"]:
        resp = client.get(f"/support/{slug}")
        assert resp.status_code == 200
        assert "customer_support.js" in resp.text


def test_support_next_wave_tenants_routes_serve_customer_page():
    client = TestClient(create_app())
    for slug in ["cigna", "unitedhealthcare", "statefarm", "libertymutual", "farmers", "fedex", "ups", "dhl"]:
        resp = client.get(f"/support/{slug}")
        assert resp.status_code == 200
        assert "customer_support.js" in resp.text


def test_demo_directory_routes_work():
    client = TestClient(create_app())
    page = client.get("/demos")
    assert page.status_code == 200
    assert "demo_directory.js" in page.text
    catalog = client.get("/api/v1/demos/catalog")
    assert catalog.status_code == 200
    data = catalog.json()
    assert data["ok"] is True
    slugs = {item["slug"] for item in data["demos"]}
    assert "flair" in slugs
    assert "frontier" in slugs
    assert "cigna" in slugs
    assert "fedex" in slugs


def test_customer_capabilities_insurance_and_health_tenants_are_verticalized():
    client = TestClient(create_app())
    insurance = client.get("/api/v1/customer/capabilities?tenant=progressive")
    health = client.get("/api/v1/customer/capabilities?tenant=aetna")
    assert insurance.status_code == 200
    assert health.status_code == 200
    ins = insurance.json()
    hp = health.json()
    assert ins["vertical"] == "insurance"
    assert hp["vertical"] == "health"
    assert "claims" in " ".join(ins.get("what_it_can_help_with", [])).lower()
    assert "prior authorization" in " ".join(hp.get("what_it_can_help_with", [])).lower()
    assert isinstance(ins.get("ui_strings"), dict)
    assert isinstance(hp.get("ui_strings"), dict)


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
    assert isinstance(data.get("promise_ledger"), list)
    assert isinstance(data.get("customer_effort"), dict)
    assert len(data.get("self_service_options", [])) >= 1


def test_insurance_claim_status_generates_workflow_artifact():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/message",
        json={
            "tenant": "progressive",
            "session_id": "ins-claim-1",
            "customer_id": "cust-ins-1",
            "channel": "web",
            "content": "What's the status of my claim?",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "general_agent"
    assert data["intent"] == "GENERAL_INQUIRY"
    artifacts = data.get("resolution_artifacts") or {}
    assert isinstance(artifacts.get("workflow_artifact"), dict)
    assert "claim" in str(artifacts["workflow_artifact"].get("title", "")).lower()


def test_health_plan_prior_auth_generates_workflow_artifact():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/message",
        json={
            "tenant": "aetna",
            "session_id": "hp-auth-1",
            "customer_id": "cust-hp-1",
            "channel": "web",
            "content": "I need help with a prior authorization.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "general_agent"
    artifacts = data.get("resolution_artifacts") or {}
    assert isinstance(artifacts.get("workflow_artifact"), dict)
    assert "authorization" in str(artifacts["workflow_artifact"].get("title", "")).lower()


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
    assert "support reference" not in data.get("customer_message", "").lower()


def test_continue_channel_sms_and_phone_work_without_existing_session():
    client = TestClient(create_app())
    for channel in ("phone", "sms"):
        cont = client.post(
            "/api/v1/customer/continue-channel",
            json={
                "session_id": "missing-session",
                "customer_id": "cust-demo",
                "from_channel": "web_chat",
                "to_channel": channel,
            },
        )
        assert cont.status_code == 200
        data = cont.json()
        assert data["ok"] is True
        assert data["reference"].startswith("SUP-")
        assert data["to_channel"] == channel
        assert "support reference" not in (data.get("customer_message") or "").lower()


def test_follow_up_summary_without_session_returns_clear_message():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/follow-up-summary",
        json={
            "session_id": "no-session-yet",
            "customer_id": "cust-no-session",
            "channel": "web",
            "delivery_channel": "sms",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "session_not_found"
    assert "Ask a question first" in data["message"]


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
    assert isinstance(data.get("resolution_artifacts"), dict)


def test_charge_issue_prompt_does_not_500_and_stays_refund_domain():
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": "charge-int-1",
            "customer_id": "cust-charge-1",
            "channel": "web",
            "content": "charge issue",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] in {"refund_agent", "support_fallback"}
    assert "charge" in data["message"].lower() or "refund" in data["message"].lower()


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


def test_customer_alerts_returns_disruption_alert_when_session_has_delayed_flight():
    client = TestClient(create_app())
    session_id = "cust-alert-1"
    customer_id = "cust-a1"
    client.post(
        "/api/v1/customer/message",
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "channel": "web",
            "content": "What is the status of flight F81234?",
        },
    )
    resp = client.get(f"/api/v1/customer/alerts?session_id={session_id}&customer_id={customer_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data.get("alerts"), list)
    if data["alerts"]:
        assert "recommended_actions" in data["alerts"][0]


def test_customer_commitments_endpoint_returns_promise_ledger():
    client = TestClient(create_app())
    session_id = "cust-commit-1"
    customer_id = "cust-commit"
    msg = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "channel": "web",
            "content": "I need a refund for booking AB12CD",
        },
    )
    assert msg.status_code == 200
    resp = client.get(f"/api/v1/customer/commitments?session_id={session_id}&customer_id={customer_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("commitments"), list)
    assert isinstance(data.get("customer_effort"), dict)
    if data["commitments"]:
        ids = {str(item.get("id")) for item in data["commitments"] if isinstance(item, dict)}
        assert "context_continuity" in ids


def test_stale_memory_confirmation_for_refund_booking_reference():
    client = TestClient(create_app())
    session_id = "cust-stale-refund-1"
    customer_id = "cust-stale"
    first = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "channel": "web",
            "content": "I need a refund for booking AB12CD",
        },
    )
    assert first.status_code == 200
    # Simulate stale memory by editing the saved entity timestamp.
    pool = getattr(client.app.state, "tenant_pool", None)
    orch = pool.get("flair") if pool is not None else client.app.state.orchestrator
    import asyncio
    ctx = asyncio.run(orch.session_memory.get_by_session_id(session_id))
    assert ctx is not None
    ts = dict(ctx.extracted_entities.get("_entity_timestamps") or {})
    ts["booking_reference"] = "2020-01-01T00:00:00"
    ctx.extracted_entities["_entity_timestamps"] = ts
    second = client.post(
        "/api/v1/customer/message",
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "channel": "web",
            "content": "can i get a refund",
        },
    )
    assert second.status_code == 200
    data = second.json()
    assert data["agent"] == "refund_agent"
    assert "still have a booking reference from earlier" in data["message"].lower()
