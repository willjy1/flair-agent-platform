from __future__ import annotations

from typing import List

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


class SMSHandler:
    def __init__(self, orchestrator: OrchestratorAgent, segment_size: int = 160) -> None:
        self.orchestrator = orchestrator
        self.segment_size = segment_size

    def split_message(self, text: str) -> List[str]:
        text = text.strip()
        if len(text) <= self.segment_size:
            return [text]
        parts: List[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.segment_size:
                parts.append(remaining)
                break
            cut = remaining.rfind(". ", 0, self.segment_size)
            if cut <= 0:
                cut = remaining.rfind(" ", 0, self.segment_size)
            if cut <= 0:
                cut = self.segment_size
            parts.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        return [p for p in parts if p]

    async def handle_inbound_sms(self, from_number: str, body: str, message_sid: str, media_urls: list[str] | None = None) -> dict:
        response = await self.orchestrator.route_message(
            InboundMessage(
                session_id=message_sid,
                customer_id=from_number,
                channel=ChannelType.SMS,
                content=body,
                attachments=media_urls or [],
            )
        )
        return {
            "session_id": message_sid,
            "segments": self.split_message(response.response_text),
            "agent": response.agent,
            "state": response.state.value,
            "metadata": response.metadata,
        }

