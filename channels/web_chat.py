from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


@dataclass
class WebChatConnectionManager:
    connections: Dict[str, Set[WebSocket]] = field(default_factory=dict)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(session_id, set()).add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.connections:
            self.connections[session_id].discard(websocket)
            if not self.connections[session_id]:
                self.connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: dict) -> None:
        for ws in list(self.connections.get(session_id, set())):
            await ws.send_json(payload)


async def websocket_chat_handler(
    websocket: WebSocket,
    orchestrator: OrchestratorAgent,
    manager: WebChatConnectionManager,
    session_id: str,
) -> None:
    await manager.connect(session_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "session_id": session_id})
        while True:
            inbound = await websocket.receive_json()
            customer_id = str(inbound.get("customer_id") or "web-anon")
            content = str(inbound.get("content") or "").strip()
            if not content:
                await websocket.send_json({"type": "error", "message": "content is required"})
                continue
            await manager.broadcast(session_id, {"type": "typing", "by": "agent"})
            response = await orchestrator.route_message(
                InboundMessage(
                    session_id=session_id,
                    customer_id=customer_id,
                    channel=ChannelType.WEB,
                    content=content,
                    attachments=list(inbound.get("attachments") or []),
                    metadata=dict(inbound.get("metadata") or {}),
                )
            )
            await manager.broadcast(
                session_id,
                {
                    "type": "message",
                    "message": response.model_dump(mode="json"),
                    "status": "delivered",
                    "read_receipt": True,
                },
            )
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)

