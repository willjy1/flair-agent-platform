from __future__ import annotations

import re
from typing import Dict

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


class VoiceHandler:
    """Voice-channel orchestration wrapper (Amazon Connect / telephony friendly)."""

    def __init__(self, orchestrator: OrchestratorAgent) -> None:
        self.orchestrator = orchestrator

    async def handle_transcript(self, contact_id: str, customer_id: str, transcript: str, metadata: Dict[str, object] | None = None) -> dict:
        response = await self.orchestrator.route_message(
            InboundMessage(
                session_id=contact_id,
                customer_id=customer_id,
                channel=ChannelType.VOICE,
                content=transcript,
                metadata=metadata or {},
            )
        )
        # Telephony-friendly concise version
        spoken = self._voice_safe_text(response.response_text)
        if len(spoken) > 420:
            spoken = spoken[:417].rsplit(" ", 1)[0] + "..."
        return {
            "contact_id": contact_id,
            "agent": response.agent,
            "state": response.state.value,
            "say_text": spoken,
            "full_text": response.response_text,
            "next_actions": response.next_actions,
            "escalate": response.escalate,
            "transfer_recommended": response.escalate,
            "citations": response.metadata.get("citations", []),
            "official_next_steps": response.metadata.get("official_next_steps", []),
            "self_service_options": response.metadata.get("self_service_options", []),
            "customer_plan": response.metadata.get("customer_plan", {}),
            "metadata": response.metadata,
        }

    def _voice_safe_text(self, text: str) -> str:
        spoken = (text or "").strip()
        if not spoken:
            return ""
        spoken = re.sub(r"https?://\S+", "", spoken)
        spoken = re.sub(r"\bSUP-[A-Z0-9]+\b", "your support reference", spoken)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        spoken = spoken.replace("APPR", "A P P R")
        spoken = spoken.replace("PNR", "booking reference")
        spoken = re.sub(r"Next step options:\s*[^.]+\.?", "", spoken, flags=re.IGNORECASE)
        spoken = re.sub(r"\s{2,}", " ", spoken).strip()
        # Keep the voice response concise and avoid reading every chained detail.
        parts = re.split(r"(?<=[.!?])\s+", spoken)
        if len(parts) > 2:
            spoken = " ".join(parts[:2]).strip()
        return spoken
