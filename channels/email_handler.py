from __future__ import annotations

from email.message import EmailMessage
from typing import Dict

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


class EmailHandler:
    def __init__(self, orchestrator: OrchestratorAgent) -> None:
        self.orchestrator = orchestrator

    async def handle_inbound_email(
        self,
        message_id: str,
        sender: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
    ) -> dict:
        combined = f"Subject: {subject}\n\n{body}".strip()
        response = await self.orchestrator.route_message(
            InboundMessage(
                session_id=message_id,
                customer_id=sender,
                channel=ChannelType.EMAIL,
                content=combined,
                attachments=attachments or [],
                metadata={"email_subject": subject},
            )
        )
        outbound = EmailMessage()
        outbound["Subject"] = f"Re: {subject}"
        outbound["To"] = sender
        outbound.set_content(response.response_text)
        return {
            "outbound_email": outbound.as_string(),
            "agent": response.agent,
            "state": response.state.value,
            "escalate": response.escalate,
        }

