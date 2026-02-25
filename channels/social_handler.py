from __future__ import annotations

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


class SocialHandler:
    def __init__(self, orchestrator: OrchestratorAgent) -> None:
        self.orchestrator = orchestrator

    async def handle_post(self, user_id: str, text: str, conversation_id: str, platform: str = "x") -> dict:
        response = await self.orchestrator.route_message(
            InboundMessage(
                session_id=conversation_id,
                customer_id=user_id,
                channel=ChannelType.SOCIAL,
                content=text,
                metadata={"platform": platform},
            )
        )
        return {"reply": response.response_text, "agent": response.agent, "escalate": response.escalate}

