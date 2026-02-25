from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_orchestrator_routes_refund_flow():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="sess-1",
                customer_id="cust-1",
                channel=ChannelType.WEB,
                content="I need a refund for booking AB12CD",
            )
        )
        assert response.agent == "refund_agent"
        assert response.intent is not None
        assert "refund" in response.response_text.lower()

    asyncio.run(_run())


def test_orchestrator_chains_delay_to_compensation():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="sess-2",
                customer_id="cust-1",
                channel=ChannelType.WEB,
                content="What is the flight status for F81234?",
            )
        )
        assert response.agent == "disruption_agent"
        assert "Flight F81234" in response.response_text
        assert "APPR" in response.response_text or "compensation" in response.response_text.lower()

    asyncio.run(_run())

