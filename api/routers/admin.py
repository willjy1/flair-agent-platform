from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.middleware.auth import require_role


router = APIRouter(prefix="/admin", tags=["admin"])


class EscalationTakeoverRequest(BaseModel):
    session_id: str
    agent_id: str
    note: str = ""


class BroadcastRequest(BaseModel):
    message: str
    flight_numbers: List[str] = Field(default_factory=list)
    channel: str = "sms"
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/escalations")
async def take_over_escalation(payload: EscalationTakeoverRequest, request: Request, _role: str = Depends(require_role("AGENT", "SUPERVISOR", "ADMIN"))):
    orchestrator = request.app.state.orchestrator
    ctx = await orchestrator.session_memory.get_by_session_id(payload.session_id)
    if ctx:
        await orchestrator.analytics_tools.log_event(
            "human_takeover",
            {"session_id": payload.session_id, "agent_id": payload.agent_id, "note": payload.note},
        )
    return {"ok": True, "session_found": bool(ctx), "assigned_agent": payload.agent_id}


@router.post("/broadcast")
async def broadcast_message(payload: BroadcastRequest, request: Request, _role: str = Depends(require_role("SUPERVISOR", "ADMIN"))):
    orchestrator = request.app.state.orchestrator
    await orchestrator.analytics_tools.log_event(
        "broadcast",
        {"message": payload.message, "flight_numbers": payload.flight_numbers, "channel": payload.channel, "metadata": payload.metadata},
    )
    return {"ok": True, "queued": True, "targets": len(payload.flight_numbers) or "segment"}

