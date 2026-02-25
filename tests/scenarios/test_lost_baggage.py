from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_lost_baggage_flow_with_claim_number():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="scenario-bag",
                customer_id="cust-bag",
                channel=ChannelType.SMS,
                content="My bag is missing. Claim number AB1234568",
            )
        )
        assert response.agent == "baggage_agent"
        assert response.state.value in {"RESOLVED", "ESCALATED"}
        assert "bag" in response.response_text.lower() or "baggage" in response.response_text.lower()

    asyncio.run(_run())

