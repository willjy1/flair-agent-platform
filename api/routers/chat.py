from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field

from channels.web_chat import WebChatConnectionManager, websocket_chat_handler
from models.schemas import ChannelType, InboundMessage


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    session_id: str
    customer_id: str
    channel: ChannelType = ChannelType.WEB
    content: str
    attachments: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/message")
async def post_chat_message(payload: ChatMessageRequest, request: Request):
    orchestrator = _orchestrator(request)
    response = await orchestrator.route_message(
        InboundMessage(
            session_id=payload.session_id,
            customer_id=payload.customer_id,
            channel=payload.channel,
            content=payload.content,
            attachments=payload.attachments,
            metadata=payload.metadata,
        )
    )
    return response.model_dump(mode="json")


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, request: Request):
    orchestrator = _orchestrator(request)
    ctx = await orchestrator.session_memory.get_by_session_id(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="session_not_found")
    return ctx.model_dump(mode="json")


@router.websocket("/ws/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    app = websocket.app
    manager: WebChatConnectionManager = app.state.web_chat_manager
    orchestrator = app.state.orchestrator
    await websocket_chat_handler(websocket, orchestrator=orchestrator, manager=manager, session_id=session_id)

