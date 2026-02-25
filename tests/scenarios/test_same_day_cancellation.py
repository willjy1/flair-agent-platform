from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_same_day_cancellation_guidance():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="scenario-cancel",
                customer_id="cust-1",
                channel=ChannelType.WEB,
                content="I need to cancel booking AB12CD for today and want a refund",
            )
        )
        assert response.intent is not None
        assert response.intent.value in {"CANCELLATION", "REFUND"}
        assert any(word in response.response_text.lower() for word in ["cancel", "refund", "credit"])

    asyncio.run(_run())

