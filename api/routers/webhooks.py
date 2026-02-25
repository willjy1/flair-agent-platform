from __future__ import annotations

from fastapi import APIRouter, Request

from models.schemas import ChannelType, InboundMessage


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio")
async def twilio_sms_webhook(request: Request):
    data = await request.form()
    orchestrator = request.app.state.orchestrator
    body = str(data.get("Body") or "")
    from_number = str(data.get("From") or "twilio-anon")
    session_id = str(data.get("MessageSid") or f"sms-{from_number}")
    response = await orchestrator.route_message(
        InboundMessage(session_id=session_id, customer_id=from_number, channel=ChannelType.SMS, content=body)
    )
    return {"ok": True, "reply": response.response_text, "agent": response.agent}


@router.post("/twitter")
async def twitter_webhook(request: Request):
    payload = await request.json()
    orchestrator = request.app.state.orchestrator
    content = str(payload.get("text") or "")
    user_id = str(payload.get("user_id") or "twitter-user")
    session_id = str(payload.get("conversation_id") or f"x-{user_id}")
    response = await orchestrator.route_message(
        InboundMessage(session_id=session_id, customer_id=user_id, channel=ChannelType.SOCIAL, content=content, metadata=payload)
    )
    return {"ok": True, "reply": response.model_dump(mode="json")}


@router.post("/amazon-connect")
async def amazon_connect_webhook(request: Request):
    payload = await request.json()
    orchestrator = request.app.state.orchestrator
    transcript = str(payload.get("transcript") or payload.get("inputTranscript") or "")
    contact_id = str(payload.get("contact_id") or payload.get("ContactId") or "voice-contact")
    customer_id = str(payload.get("customer_id") or payload.get("CustomerEndpoint") or contact_id)
    response = await orchestrator.route_message(
        InboundMessage(session_id=contact_id, customer_id=customer_id, channel=ChannelType.VOICE, content=transcript, metadata=payload)
    )
    return {"ok": True, "response_text": response.response_text, "state": response.state.value}

