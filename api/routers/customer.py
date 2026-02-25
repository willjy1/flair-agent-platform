from __future__ import annotations

import base64
import binascii
import difflib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from pydantic import BaseModel, Field

from channels.voice_handler import VoiceHandler
from models.schemas import ChannelType, InboundMessage
from api.customer_reference_store import SupportReferenceRecord
from tools.document_intake_tools import DocumentIntakeTools


router = APIRouter(prefix="/customer", tags=["customer"])
logger = logging.getLogger(__name__)


class CustomerMessageRequest(BaseModel):
    session_id: str
    customer_id: str
    channel: ChannelType = ChannelType.WEB
    content: str
    tenant: str | None = None
    attachments: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContinueChannelRequest(BaseModel):
    session_id: str
    customer_id: str
    from_channel: str
    to_channel: str
    tenant: str | None = None


class ResetSessionRequest(BaseModel):
    session_id: str
    customer_id: str
    channel: str = "web"
    tenant: str | None = None


class VoiceTranscribeRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    language: str = "en"
    session_id: str | None = None
    customer_id: str | None = None
    tenant: str | None = None


class VoiceSpeakRequest(BaseModel):
    text: str
    voice_mode: str = "support"
    tenant: str | None = None


class UploadAnalyzeRequest(BaseModel):
    file_name: str
    mime_type: str = "application/octet-stream"
    content_base64: str
    tenant: str | None = None


class FollowUpSummaryRequest(BaseModel):
    session_id: str
    customer_id: str
    channel: str = "web"
    delivery_channel: str = "sms"
    tenant: str | None = None


def _resolve_tenant_slug(request: Request, payload_tenant: str | None = None) -> str:
    query_tenant = request.query_params.get("tenant")
    header_tenant = request.headers.get("X-Tenant")
    slug = (payload_tenant or query_tenant or header_tenant or "flair").strip().lower()
    return slug or "flair"


def _orchestrator(request: Request, tenant_slug: str | None = None):
    pool = getattr(request.app.state, "tenant_pool", None)
    if pool is not None:
        return pool.get(tenant_slug or "flair")
    return request.app.state.orchestrator


def _reference_store(request: Request):
    return request.app.state.customer_reference_store


def _document_tools(request: Request) -> DocumentIntakeTools:
    tool = getattr(request.app.state, "document_intake_tools", None)
    if tool is None:
        tool = DocumentIntakeTools()
        request.app.state.document_intake_tools = tool
    return tool


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _transcript_confidence_heuristic(text: str, last_assistant: str = "") -> tuple[float, bool, str | None]:
    clean = (text or "").strip()
    if not clean:
        return 0.0, True, "no_text"
    score = 0.86
    reason = None
    if len(clean) < 5:
        score -= 0.35
        reason = reason or "too_short"
    if len(clean.split()) <= 2:
        score -= 0.12
    if clean.lower().startswith("hello, this is") or "how may i assist you today" in clean.lower():
        score -= 0.45
        reason = "likely_agent_echo"
    if last_assistant:
        sim = _similarity(clean, last_assistant[: len(clean) + 80])
        if sim > 0.65:
            score -= 0.5
            reason = "likely_agent_echo"
    score = max(0.01, min(0.99, score))
    needs_confirmation = score < 0.72 or reason is not None
    return score, needs_confirmation, reason


def _confidence_bucket(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.72:
        return "medium"
    return "low"


def _looks_trackable_response(intent: str | None, state: str, agent: str, debug_tool_calls: List[Dict[str, Any]], payload: Dict[str, Any]) -> bool:
    if state in {"ESCALATED"}:
        return True
    if intent in {"REFUND", "BAGGAGE", "ACCESSIBILITY", "COMPLAINT", "IRROPS", "DELAY_INFO", "BOOKING_CHANGE", "CANCELLATION"}:
        if any(k in payload for k in ["support_reference"]):
            return True
        tool_names = [str(t.get("tool_name")) for t in debug_tool_calls]
        if any(name in {"initiate_refund", "issue_voucher", "create_case", "modify_booking", "cancel_booking"} for name in tool_names):
            return True
        if "get_realtime_status" in tool_names and (payload.get("next_actions") or state != "RESOLVED"):
            return True
    return False


def _build_follow_up_summary(message_text: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    next_actions = [str(x).replace("_", " ") for x in (payload.get("next_actions") or [])][:4]
    summary = (payload.get("message") or "")[:320]
    return {
        "summary": summary,
        "what_happens_next": next_actions,
        "can_reopen_with": "Continue this request" if next_actions else "Start a new request or ask a follow-up question",
        "links": [x for x in (payload.get("official_next_steps") or [])][:2],
        "self_service": [x for x in (payload.get("self_service_options") or [])][:2],
        "customer_last_message": (message_text or "")[:160],
    }


def _reference_payload(record: SupportReferenceRecord) -> Dict[str, Any]:
    intent_value = str((record.metadata or {}).get("intent") or "").replace("_", " ").strip()
    customer_label = (intent_value.title() + " request") if intent_value else "Support request"
    status_value = str(record.status or "").replace("_", " ").strip() or "update available"
    next_update_hint = None
    if str(record.status or "").upper() in {"CONFIRMING", "PROCESSING", "CONTINUE_CHANNEL"}:
        next_update_hint = "Waiting for your reply or next step."
    elif str(record.status or "").upper() in {"ESCALATED"}:
        next_update_hint = "Human support follow-up may take time depending on queue volume."
    elif str(record.status or "").upper() in {"RESOLVED"}:
        next_update_hint = "You can reopen this request if something still needs attention."
    return {
        "reference": record.reference,
        "tenant": record.tenant,
        "status": record.status,
        "status_label": status_value,
        "customer_label": customer_label,
        "next_update_hint": next_update_hint,
        "channel": record.channel,
        "summary": record.summary,
        "next_steps": record.next_steps,
        "events": record.events[-8:],
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "metadata": record.metadata,
    }


def _tenant_profile(orchestrator) -> Any:
    return getattr(orchestrator, "tenant_profile", None)


def _tenant_brand_name(orchestrator) -> str:
    profile = _tenant_profile(orchestrator)
    md = dict(getattr(profile, "metadata", {}) or {}) if profile else {}
    if md.get("company_name"):
        return str(md["company_name"])
    if profile and getattr(profile, "display_name", None):
        return str(profile.display_name).replace(" Agents", "")
    return "Support"


def _tenant_contact_context(orchestrator) -> Dict[str, Any]:
    profile = _tenant_profile(orchestrator)
    md = dict(getattr(profile, "metadata", {}) or {})
    brand = _tenant_brand_name(orchestrator)
    tenant_slug = str(getattr(orchestrator, "tenant_slug", "") or "").lower()
    contact = {
        "brand": brand,
        "call_center_phone": md.get("call_center_phone") or md.get("support_phone") or md.get("primary_support_phone"),
        "accessibility_phone": md.get("accessibility_phone") or md.get("accessibility_support_phone"),
        "contact_page_url": md.get("contact_page_url"),
        "help_center_url": md.get("help_center_url"),
        "wait_time_disclaimer": md.get("wait_time_disclaimer") or "Wait times may vary.",
    }
    if not contact["call_center_phone"] and tenant_slug == "flair":
        contact["call_center_phone"] = "1-403-709-0808"
    if not contact["accessibility_phone"] and tenant_slug == "flair":
        contact["accessibility_phone"] = "1-833-382-5421"
    if not contact["contact_page_url"] and tenant_slug == "flair":
        contact["contact_page_url"] = "https://www.flyflair.com/support/contact-info"
    if not contact["help_center_url"] and tenant_slug == "flair":
        contact["help_center_url"] = "https://flyflair.zendesk.com/hc/en-us"
    top_links = []
    if contact["contact_page_url"]:
        top_links.append({"label": "Official Contact Info", "url": str(contact["contact_page_url"])})
    if contact["help_center_url"]:
        top_links.append({"label": "Help Centre", "url": str(contact["help_center_url"])})
    contact["top_links"] = top_links[:3]
    return contact


def _tenant_branding(orchestrator, tenant_slug: str) -> Dict[str, Any]:
    profile = _tenant_profile(orchestrator)
    md = dict(getattr(profile, "metadata", {}) or {})
    brand_theme = dict(md.get("brand_theme") or {})
    return {
        "tenant": tenant_slug,
        "product_name": getattr(profile, "display_name", f"{tenant_slug.title()} Support Agents"),
        "brand_name": _tenant_brand_name(orchestrator),
        "brand_mark": str(md.get("brand_mark") or (tenant_slug[:1].upper() or "S")),
        "hero_title": str(md.get("hero_title") or "Get help with your trip in one conversation."),
        "hero_subtitle": str(
            md.get("hero_subtitle")
            or "Text or voice. Get clear next steps for status, disruptions, booking changes, refunds, baggage, accessibility, and human support without starting over."
        ),
        "top_links": _tenant_contact_context(orchestrator).get("top_links", []),
        "resource_panel_title": str(md.get("resource_panel_title") or f"Official { _tenant_brand_name(orchestrator) } support links"),
        "css_vars": {
            "accent": str(brand_theme.get("accent") or "#ff6a13"),
            "accent_2": str(brand_theme.get("accent_2") or "#0d6a6a"),
            "surface_tint": str(brand_theme.get("surface_tint") or "#fff7f0"),
            "brand_dark": str(brand_theme.get("brand_dark") or "#111827"),
        },
    }


def _response_resolution_artifacts(payload: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {}
    if isinstance(metadata.get("flight_status"), dict):
        status = dict(metadata.get("flight_status") or {})
        artifacts["flight_status"] = {
            "flight_number": status.get("flight_number"),
            "status": status.get("status"),
            "delay_minutes": status.get("delay_minutes"),
            "departure_gate": status.get("departure_gate"),
            "timestamp": status.get("timestamp"),
        }
    if isinstance(metadata.get("rebooking_options"), list):
        options = []
        for idx, opt in enumerate(list(metadata.get("rebooking_options") or [])[:3], start=1):
            if isinstance(opt, dict):
                options.append(
                    {
                        "option": idx,
                        "flight_number": opt.get("flight_number"),
                        "date": opt.get("date"),
                        "fare_diff": opt.get("fare_diff"),
                    }
                )
        if options:
            artifacts["rebooking_options"] = options
    if isinstance(metadata.get("compensation"), dict):
        comp = dict(metadata.get("compensation") or {})
        artifacts["compensation_estimate"] = {
            "amount": comp.get("amount"),
            "currency": comp.get("currency"),
            "regulation_section": comp.get("regulation_section"),
            "breakdown": comp.get("calculation_breakdown"),
        }
    if metadata.get("refund_amount_cad") is not None:
        artifacts["refund_estimate"] = {
            "amount_cad": metadata.get("refund_amount_cad"),
            "timeline_days": metadata.get("refund_timeline_days"),
        }
    if isinstance(metadata.get("refund"), dict):
        artifacts["refund_request"] = dict(metadata.get("refund") or {})
    if isinstance(metadata.get("voucher"), dict):
        artifacts["travel_credit"] = dict(metadata.get("voucher") or {})
    if metadata.get("missed_flight_rescue"):
        artifacts["missed_flight_rescue"] = True
    if metadata.get("charge_issue_type"):
        artifacts["charge_issue_type"] = metadata.get("charge_issue_type")
    if isinstance(metadata.get("grounding"), dict):
        artifacts["grounding"] = {
            "source_backed": bool(metadata["grounding"].get("source_backed")),
            "snapshot_date": metadata["grounding"].get("snapshot_date"),
        }
    if payload.get("state"):
        artifacts["state"] = payload.get("state")
    return artifacts


def _safe_customer_error_result(
    *,
    tenant_slug: str,
    session_id: str,
    customer_id: str,
    channel: str,
    mode: str,
    message_text: str,
    voice: bool = False,
    brand_name: str = "Flair",
    phone_number: str = "1-403-709-0808",
) -> Dict[str, Any]:
    base_message = (
        "I ran into a problem while handling that request. Please try again in a moment. "
        f"If this is urgent, {brand_name}'s published call center number is {phone_number} (wait times may vary)."
    )
    spoken = (
        f"I ran into a problem handling that request. Please try again, or call {brand_name} at {phone_number}. Wait times may vary."
    )
    payload = {
        "session_id": session_id,
        "customer_id": customer_id,
        "tenant": tenant_slug,
        "channel": channel,
        "mode": mode,
        "message": base_message,
        "state": "PROCESSING",
        "agent": "support_fallback",
        "intent": None,
        "next_actions": ["retry_request", "human_agent_if_urgent"],
        "escalate": False,
        "citations": [],
        "official_next_steps": [],
        "self_service_options": [],
        "customer_plan": {
            "intent": "GENERAL_INQUIRY",
            "stage": "RECOVERY",
            "what_i_can_do_now": [
                "retry your request",
                "continue with a human support handoff",
            ],
            "what_i_need_from_you": ["retry the request or choose phone support if urgent"],
            "prepared_context": [],
        },
        "support_reference": None,
        "debug": {"error": "customer_endpoint_failed"},
    }
    if voice:
        payload["spoken_message"] = spoken
    payload["follow_up_summary"] = _build_follow_up_summary(message_text, payload)
    return payload


@router.get("", response_class=HTMLResponse)
async def customer_support_page() -> HTMLResponse:
    html_path = Path(__file__).resolve().parents[2] / "web" / "customer_support.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail="customer_support_page_missing")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@router.post("/message")
async def customer_message(payload: CustomerMessageRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    contact_ctx = _tenant_contact_context(orchestrator)
    try:
        response = await orchestrator.route_message(
            InboundMessage(
                session_id=payload.session_id,
                customer_id=payload.customer_id,
                channel=payload.channel,
                content=payload.content,
                attachments=payload.attachments,
                metadata={**payload.metadata, "tenant": tenant_slug},
            )
        )
        support_reference = None
        if response.escalate:
            support_reference = f"SUP-{uuid.uuid4().hex[:8].upper()}"
            _reference_store(request).upsert(
                SupportReferenceRecord(
                    reference=support_reference,
                    tenant=tenant_slug,
                    customer_id=payload.customer_id,
                    session_id=payload.session_id,
                    status=response.state.value,
                    channel=payload.channel.value,
                    summary=response.response_text[:600],
                    next_steps=list(response.next_actions or []),
                    metadata={"agent": response.agent, "intent": response.intent.value if response.intent else None},
                )
            )
        result = {
            "session_id": response.session_id,
            "customer_id": response.customer_id,
            "tenant": tenant_slug,
            "channel": payload.channel.value,
            "mode": "voice" if payload.channel == ChannelType.VOICE else "text",
            "message": response.response_text,
            "state": response.state.value,
            "agent": response.agent,
            "intent": response.intent.value if response.intent else None,
            "next_actions": response.next_actions,
            "escalate": response.escalate,
            "citations": response.metadata.get("citations", []),
            "official_next_steps": response.metadata.get("official_next_steps", []),
            "self_service_options": response.metadata.get("self_service_options", []),
            "customer_plan": response.metadata.get("customer_plan", {}),
            "grounding": response.metadata.get("grounding", {}),
            "support_reference": support_reference,
            "debug": {
                "tool_calls": [t.model_dump(mode="json") for t in response.tool_calls],
            },
        }
        debug_tool_calls = list(result["debug"]["tool_calls"])
        if _looks_trackable_response(result.get("intent"), result.get("state", ""), result.get("agent", ""), debug_tool_calls, result):
            existing = _reference_store(request).latest_for_session(tenant_slug, payload.customer_id, payload.session_id)
            if existing and existing.status in {"CONFIRMING", "PROCESSING", "RESOLVED", "ESCALATED"}:
                existing.status = result["state"]
                existing.channel = payload.channel.value
                existing.summary = str(result.get("message") or "")[:600]
                existing.next_steps = list(result.get("next_actions") or [])
                existing.metadata = {
                    **dict(existing.metadata or {}),
                    "agent": result.get("agent"),
                    "intent": result.get("intent"),
                    "trackable": True,
                }
                _reference_store(request).upsert(existing)
                _reference_store(request).append_event(existing.reference, "agent_update", existing.summary, {"state": existing.status, "intent": result.get("intent")})
                support_reference = support_reference or existing.reference
            elif not support_reference:
                auto_ref = f"SUP-{uuid.uuid4().hex[:8].upper()}"
                _reference_store(request).upsert(
                    SupportReferenceRecord(
                        reference=auto_ref,
                        tenant=tenant_slug,
                        customer_id=payload.customer_id,
                        session_id=payload.session_id,
                        status=result["state"],
                        channel=payload.channel.value,
                        summary=str(result.get("message") or "")[:600],
                        next_steps=list(result.get("next_actions") or []),
                        metadata={"agent": result.get("agent"), "intent": result.get("intent"), "trackable": True},
                        events=[{"type": "agent_update", "summary": str(result.get("message") or "")[:400], "metadata": {"state": result["state"], "intent": result.get("intent")}, "timestamp": datetime.utcnow().isoformat()}],
                    )
                )
                support_reference = auto_ref
        if response.metadata.get("followup_choice"):
            result["citations"] = []
            result["official_next_steps"] = []
            if len(result.get("self_service_options") or []) > 1:
                result["self_service_options"] = list(result["self_service_options"][:1])
        result["support_reference"] = support_reference
        result["resolution_artifacts"] = _response_resolution_artifacts(result, response.metadata or {})
        result["follow_up_summary"] = _build_follow_up_summary(payload.content, result)
        return result
    except Exception:
        logger.exception("customer_message_endpoint_failed", extra={"tenant": tenant_slug, "session_id": payload.session_id})
        return _safe_customer_error_result(
            tenant_slug=tenant_slug,
            session_id=payload.session_id,
            customer_id=payload.customer_id,
            channel=payload.channel.value,
            mode="voice" if payload.channel == ChannelType.VOICE else "text",
            message_text=payload.content,
            brand_name=str(contact_ctx.get("brand") or "Flair"),
            phone_number=str(contact_ctx.get("call_center_phone") or "1-403-709-0808"),
        )


@router.post("/voice/simulate")
async def customer_voice_simulate(payload: CustomerMessageRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    contact_ctx = _tenant_contact_context(orchestrator)
    try:
        voice_handler = VoiceHandler(orchestrator)
        result = await voice_handler.handle_transcript(
            contact_id=payload.session_id,
            customer_id=payload.customer_id,
            transcript=payload.content,
            metadata={"channel": "customer_voice_web_sim", "tenant": tenant_slug, **payload.metadata},
        )
        support_reference = None
        if result.get("escalate"):
            support_reference = f"SUP-{uuid.uuid4().hex[:8].upper()}"
            _reference_store(request).upsert(
                SupportReferenceRecord(
                    reference=support_reference,
                    tenant=tenant_slug,
                    customer_id=payload.customer_id,
                    session_id=payload.session_id,
                    status=str(result.get("state") or "ESCALATED"),
                    channel="voice",
                    summary=str(result.get("full_text") or result.get("say_text") or "")[:600],
                    next_steps=list(result.get("next_actions") or []),
                    metadata={"agent": result.get("agent"), "intent": result.get("metadata", {}).get("triage", {}).get("intent") if isinstance(result.get("metadata"), dict) else None},
                )
            )
        response_payload = {
            "session_id": payload.session_id,
            "customer_id": payload.customer_id,
            "tenant": tenant_slug,
            "channel": "voice",
            "mode": "voice",
            "message": result.get("full_text") or result.get("say_text") or "",
            "spoken_message": result.get("say_text") or result.get("full_text") or "",
            "state": result.get("state"),
            "agent": result.get("agent"),
            "intent": (
                (result.get("metadata") or {}).get("triage", {}).get("intent")
                if isinstance(result.get("metadata"), dict)
                else None
            ),
            "next_actions": result.get("next_actions", []),
            "escalate": bool(result.get("escalate")),
            "citations": result.get("citations", []),
            "official_next_steps": result.get("official_next_steps", []),
            "self_service_options": result.get("self_service_options", []),
            "customer_plan": result.get("customer_plan", {}),
            "grounding": ((result.get("metadata") or {}).get("grounding") if isinstance(result.get("metadata"), dict) else {}),
            "support_reference": support_reference,
            "debug": {
                "voice_simulation": {
                    "agent": result.get("agent"),
                    "state": result.get("state"),
                    "next_actions": result.get("next_actions", []),
                    "escalate": bool(result.get("escalate")),
                    "metadata": result.get("metadata", {}),
                }
            }
        }
        response_payload["resolution_artifacts"] = _response_resolution_artifacts(response_payload, (result.get("metadata") or {}) if isinstance(result.get("metadata"), dict) else {})
        # Render/FastAPI version differences can surface nested serialization issues;
        # force JSON-safe encoding here so the voice endpoint does not fail after successful transcription.
        return jsonable_encoder(response_payload)
    except Exception:
        logger.exception("customer_voice_simulate_failed", extra={"tenant": tenant_slug, "session_id": payload.session_id})
        return jsonable_encoder(
            _safe_customer_error_result(
                tenant_slug=tenant_slug,
                session_id=payload.session_id,
                customer_id=payload.customer_id,
                channel="voice",
                mode="voice",
                message_text=payload.content,
                voice=True,
                brand_name=str(contact_ctx.get("brand") or "Flair"),
                phone_number=str(contact_ctx.get("call_center_phone") or "1-403-709-0808"),
            )
        )


@router.post("/voice/transcribe")
async def customer_voice_transcribe(payload: VoiceTranscribeRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    raw = payload.audio_base64.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        audio_bytes = base64.b64decode(raw, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail=f"invalid_audio_base64:{exc}") from exc

    if len(audio_bytes) < 400:
        return {"ok": False, "error": "audio_too_short", "message": "I couldn't hear enough audio. Please try again and speak for a little longer."}
    result = await orchestrator.llm.transcribe_audio(audio_bytes=audio_bytes, mime_type=payload.mime_type, language=payload.language)
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "transcription_failed"),
            "provider": result.get("provider", "unknown"),
            "message": "Voice transcription is not available right now. You can still type your question.",
        }
    text = str(result.get("text") or "").strip()
    if not text:
        return {
            "ok": False,
            "error": "no_text",
            "provider": result.get("provider", "unknown"),
            "message": "I couldn't make out the words clearly. Please try again or type your question.",
        }
    last_assistant = ""
    if payload.session_id and payload.customer_id:
        try:
            ctx = await orchestrator.session_memory.get_by_session_id(payload.session_id)
            if ctx and ctx.customer_id == payload.customer_id:
                for item in reversed(ctx.history):
                    if item.get("role") == "assistant":
                        last_assistant = str(item.get("content") or "")
                        break
        except Exception:
            last_assistant = ""
    confidence, needs_confirmation, reason = _transcript_confidence_heuristic(text, last_assistant)
    response_payload = {
        "ok": True,
        "tenant": tenant_slug,
        "text": text,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "confidence": confidence,
        "confidence_bucket": _confidence_bucket(confidence),
        "needs_confirmation": needs_confirmation,
        "reason": reason,
        "auto_send_recommended": not needs_confirmation,
    }
    if needs_confirmation:
        if reason == "likely_agent_echo":
            response_payload["message"] = "I may have picked up my own voice output. Please try again after the audio finishes, or type your question."
        elif reason == "too_short":
            response_payload["message"] = "That was a short recording. Please try again and speak a little longer, or type your question."
        else:
            response_payload["message"] = "Please check the transcript before sending. I may have misheard part of it."
    return response_payload


@router.post("/voice/speak")
async def customer_voice_speak(payload: VoiceSpeakRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    result = await orchestrator.llm.synthesize_speech(payload.text, voice_mode=payload.voice_mode)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "tts_unavailable"))
    audio_b64 = str(result.get("audio_bytes_b64") or "")
    audio = base64.b64decode(audio_b64) if audio_b64 else b""
    return Response(content=audio, media_type=str(result.get("mime_type") or "audio/mpeg"), headers={"X-TTS-Provider": str(result.get("provider") or "")})


@router.get("/capabilities")
async def customer_capabilities(request: Request):
    tenant_slug = _resolve_tenant_slug(request)
    orchestrator = _orchestrator(request, tenant_slug)
    tenant_profile = getattr(orchestrator, "tenant_profile", None)
    branding = _tenant_branding(orchestrator, tenant_slug)
    contact_ctx = _tenant_contact_context(orchestrator)
    return {
        "product_name": getattr(tenant_profile, "display_name", "Flair Support Agents"),
        "tenant": tenant_slug,
        "customer_facing": True,
        "branding": branding,
        "support_contact": {
            "brand": contact_ctx.get("brand"),
            "call_center_phone": contact_ctx.get("call_center_phone"),
            "accessibility_phone": contact_ctx.get("accessibility_phone"),
            "contact_page_url": contact_ctx.get("contact_page_url"),
            "help_center_url": contact_ctx.get("help_center_url"),
            "wait_time_disclaimer": contact_ctx.get("wait_time_disclaimer"),
        },
        "what_it_can_help_with": getattr(tenant_profile, "customer_capabilities", []) or [
            "status updates and disruptions",
            "booking changes and cancellations",
            "refund guidance",
            "baggage and accessibility support intake",
            "human handoff with context",
        ],
        "channels": getattr(tenant_profile, "channels", []) or ["web chat", "voice", "sms", "email", "social"],
        "support_commitments": getattr(tenant_profile, "support_commitments", []),
        "capabilities": orchestrator.platform_capabilities_matrix(),
        "official_channel_snapshot": orchestrator.knowledge_tools.official_channel_summary(),
        "current_limitations": [
            "Real booking and CRM APIs are not connected in this local build",
            "Flight status and booking actions use mock tools in development mode",
            "Voice quality depends on browser audio capture and configured TTS provider",
        ],
        "differentiators": [
            "One support conversation across text and voice with context continuity",
            "Trackable request updates and follow-up summaries",
            "Guided next steps with official source-backed links",
            "Proactive trip alert and recovery preview (demo mode)",
        ],
        "suggested_starters": [
            "What's the status of flight F81234?",
            "I missed my flight and still need to travel today.",
            "I need a refund for booking AB12CD.",
            "I was charged twice. What should I do?",
            "I need wheelchair assistance for my flight.",
        ],
    }


@router.post("/continue-channel")
async def continue_channel(payload: ContinueChannelRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    contact_ctx = _tenant_contact_context(orchestrator)
    ctx = await orchestrator.session_memory.get_by_session_id(payload.session_id)
    # For phone/SMS continuation, always return something useful even if the session is new or expired.
    to_channel = payload.to_channel.lower()
    if (not ctx or ctx.customer_id != payload.customer_id) and to_channel not in {"phone", "sms"}:
        raise HTTPException(status_code=404, detail="session_not_found")
    reference = f"SUP-{uuid.uuid4().hex[:8].upper()}"
    recent = ctx.history[-6:] if ctx and ctx.customer_id == payload.customer_id else []
    summary = " ".join([f"{m.get('role')}: {m.get('content')}" for m in recent])[:600]
    if not summary:
        summary = f"Customer requested continuation to {to_channel} support."
    _reference_store(request).upsert(
        SupportReferenceRecord(
            reference=reference,
            tenant=tenant_slug,
            customer_id=payload.customer_id,
            session_id=payload.session_id,
            status="CONTINUE_CHANNEL",
            channel=payload.from_channel,
            summary=summary,
            next_steps=[f"continue_via_{payload.to_channel}"],
            metadata={"from_channel": payload.from_channel, "to_channel": payload.to_channel},
        )
    )
    await orchestrator.analytics_tools.log_event(
        "customer_channel_continue",
        {
            "session_id": payload.session_id,
            "customer_id": payload.customer_id,
            "from_channel": payload.from_channel,
            "to_channel": payload.to_channel,
            "reference": reference,
            "tenant": tenant_slug,
        },
    )
    brand = str(contact_ctx.get("brand") or "Support")
    official_phone_number = str(contact_ctx.get("call_center_phone")) if to_channel == "phone" and contact_ctx.get("call_center_phone") else None
    if to_channel == "phone":
        customer_message = (
            "You can continue by phone. "
            f"{brand}'s published call center number is {official_phone_number or 'the official support number'}. "
            f"{str(contact_ctx.get('wait_time_disclaimer') or 'Wait times may vary.')} "
            "I prepared your recent conversation details so you do not need to start over."
        )
    elif to_channel == "sms":
        customer_message = (
            "I prepared an SMS-ready continuation summary so you can continue by text without starting over."
        )
    else:
        customer_message = (
            f"You can continue on {to_channel}. Your support reference is {reference}. "
            "I've prepared your recent conversation details so you do not need to start over."
        )
    return {
        "ok": True,
        "tenant": tenant_slug,
        "reference": reference,
        "from_channel": payload.from_channel,
        "to_channel": to_channel,
        "phone_number": official_phone_number,
        "sms_ready": to_channel == "sms",
        "sms_preview": summary[:280] if to_channel == "sms" else None,
        "customer_message": customer_message,
        "handoff_summary_preview": summary,
    }


@router.post("/session/reset")
async def reset_customer_session(payload: ResetSessionRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    await orchestrator.session_memory.delete_session(
        channel=payload.channel,
        customer_id=payload.customer_id,
        session_id=payload.session_id,
    )
    return {
        "ok": True,
        "tenant": tenant_slug,
        "session_id": payload.session_id,
        "customer_id": payload.customer_id,
        "message": "Conversation cleared. You can start a new request now.",
    }


@router.get("/reference/{reference}")
async def get_support_reference(reference: str, request: Request):
    store = _reference_store(request)
    record = store.get(reference.upper())
    if not record:
        raise HTTPException(status_code=404, detail="reference_not_found")
    return _reference_payload(record)


@router.get("/references")
async def list_support_references(customer_id: str, request: Request, tenant: str | None = None):
    tenant_slug = _resolve_tenant_slug(request, tenant)
    records = _reference_store(request).list_for_customer(tenant_slug, customer_id)
    return {"tenant": tenant_slug, "customer_id": customer_id, "references": [_reference_payload(r) for r in records[:20]]}


@router.post("/follow-up-summary")
async def create_follow_up_summary(payload: FollowUpSummaryRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    ctx = await orchestrator.session_memory.get_by_session_id(payload.session_id)
    if not ctx or ctx.customer_id != payload.customer_id:
        return {
            "ok": False,
            "tenant": tenant_slug,
            "error": "session_not_found",
            "message": "Ask a question first, then I can generate a summary you can keep or send.",
        }
    recent = ctx.history[-8:]
    last_agent = next((str(m.get("content") or "") for m in reversed(recent) if m.get("role") == "assistant"), "")
    last_user = next((str(m.get("content") or "") for m in reversed(recent) if m.get("role") == "user"), "")
    next_steps = list(ctx.extracted_entities.get("_last_next_actions") or []) if isinstance(ctx.extracted_entities.get("_last_next_actions"), list) else []
    reference = _reference_store(request).latest_for_session(tenant_slug, payload.customer_id, payload.session_id)
    summary = {
        "summary": last_agent[:320] if last_agent else "Support request summary prepared.",
        "customer_last_message": last_user[:180],
        "next_steps": [str(x).replace("_", " ") for x in next_steps[:5]],
        "support_reference": reference.reference if reference else None,
        "delivery_channel": payload.delivery_channel,
        "status": "prepared_local_demo",
    }
    if reference:
        _reference_store(request).append_event(reference.reference, "follow_up_summary_prepared", summary["summary"], {"delivery_channel": payload.delivery_channel})
    return {"ok": True, "tenant": tenant_slug, "delivery": payload.delivery_channel, "payload": summary}


@router.get("/alerts")
async def customer_trip_alerts(session_id: str, customer_id: str, request: Request, tenant: str | None = None):
    tenant_slug = _resolve_tenant_slug(request, tenant)
    orchestrator = _orchestrator(request, tenant_slug)
    ctx = await orchestrator.session_memory.get_by_session_id(session_id)
    if not ctx or ctx.customer_id != customer_id:
        return {"ok": True, "tenant": tenant_slug, "alerts": []}

    entities = dict(ctx.extracted_entities or {})
    booking = None
    flight_number = str(entities.get("flight_number") or "").upper()
    pnr = str(entities.get("booking_reference") or "").upper()
    if not flight_number and pnr:
        try:
            booking = await orchestrator.booking_tools.get_booking_details(pnr)
            flight_number = str(booking.get("flight_number") or "").upper()
        except Exception:
            booking = None
    if not flight_number:
        return {"ok": True, "tenant": tenant_slug, "alerts": []}
    try:
        status = await orchestrator.flight_status_tools.get_realtime_status(flight_number)
    except Exception:
        return {"ok": True, "tenant": tenant_slug, "alerts": []}

    alerts: List[Dict[str, Any]] = []
    delay = int(status.get("delay_minutes") or 0)
    status_value = str(status.get("status") or "").upper()
    if status_value in {"DELAYED", "CANCELLED"}:
        severity = "high" if status_value == "CANCELLED" or delay >= 180 else "medium"
        summary = f"Flight {flight_number} is {status_value.lower()}."
        if delay > 0:
            summary += f" Current delay: {delay} minutes."
        actions = [
            {"label": "Check status again", "prompt": f"What is the status of flight {flight_number}?"},
            {"label": "Rebooking options", "prompt": f"I need to rebook booking {pnr} because my flight is delayed." if pnr else f"I need rebooking options for flight {flight_number}."},
        ]
        if delay >= 180:
            actions.append({"label": "Compensation check", "prompt": f"Please check APPR compensation for flight {flight_number}."})
        if pnr:
            actions.append({"label": "Refund options", "prompt": f"I need a refund for booking {pnr}."})
        alerts.append(
            {
                "type": "trip_disruption",
                "severity": severity,
                "title": "Trip update available",
                "summary": summary,
                "flight_number": flight_number,
                "delay_minutes": delay,
                "recommended_actions": actions[:4],
                "source": "flight_status_tool_demo",
            }
        )
    return {"ok": True, "tenant": tenant_slug, "alerts": alerts}


@router.post("/upload/analyze")
async def customer_upload_analyze(payload: UploadAnalyzeRequest, request: Request):
    tenant_slug = _resolve_tenant_slug(request, payload.tenant)
    raw = payload.content_base64.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(raw, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail=f"invalid_upload_base64:{exc}") from exc
    if not content:
        raise HTTPException(status_code=400, detail="empty_upload")
    analyzed = _document_tools(request).analyze_upload(payload.file_name, payload.mime_type, content)
    analyzed["tenant"] = tenant_slug
    return analyzed


@router.get("/benchmark")
async def benchmark_vs_current_support(request: Request):
    tenant_slug = _resolve_tenant_slug(request)
    orchestrator = _orchestrator(request, tenant_slug)
    return orchestrator.knowledge_tools.benchmark_vs_platform(orchestrator.platform_capabilities_matrix())
