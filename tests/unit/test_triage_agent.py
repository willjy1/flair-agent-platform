from __future__ import annotations

import asyncio

from agents.triage_agent import TriageAgent
from models.schemas import AgentMessage, ChannelType, ConversationState, InboundMessage, IntentType


def test_triage_refund_with_entities():
    async def _run():
        triage = TriageAgent()
        msg = AgentMessage(
            inbound=InboundMessage(
                session_id="s1",
                customer_id="c1",
                channel=ChannelType.WEB,
                content="I need a refund for booking AB12CD on flight F81234",
            ),
            state=ConversationState.TRIAGING,
        )
        result = await triage.classify(msg)
        assert result.intent == IntentType.REFUND
        assert result.entities["booking_reference"] == "AB12CD"
        assert result.entities["flight_number"] == "F81234"
        assert result.suggested_agent == "refund_agent"

    asyncio.run(_run())


def test_triage_detects_french():
    async def _run():
        triage = TriageAgent()
        msg = AgentMessage(
            inbound=InboundMessage(
                session_id="s2",
                customer_id="c2",
                channel=ChannelType.WEB,
                content="Bonjour, mon vol F81234 a un retard. Je veux une compensation.",
            ),
            state=ConversationState.TRIAGING,
        )
        result = await triage.classify(msg)
        assert result.language == "fr"
        assert result.intent in {IntentType.DELAY_INFO, IntentType.COMPENSATION_CLAIM}

    asyncio.run(_run())

