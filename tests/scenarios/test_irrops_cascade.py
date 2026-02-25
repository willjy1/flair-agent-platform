from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_irrops_cascade_delay_to_compensation_guidance():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="scenario-irrops",
                customer_id="cust-1",
                channel=ChannelType.WEB,
                content="My flight F81234 is delayed and I am very frustrated. What are my options?",
            )
        )
        lower = response.response_text.lower()
        assert "flight f81234" in lower
        assert "delay" in lower
        assert "compensation" in lower or "appr" in lower
        assert response.state.value in {"CONFIRMING", "RESOLVED"}

    asyncio.run(_run())

