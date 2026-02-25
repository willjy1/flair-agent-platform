from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_repeat_complainer_generates_escalation_or_complaint_case():
    async def _run():
        orchestrator = OrchestratorAgent()
        for idx in range(3):
            await orchestrator.route_message(
                InboundMessage(
                    session_id=f"scenario-repeat-{idx}",
                    customer_id="repeat-customer",
                    channel=ChannelType.WEB,
                    content="This is unacceptable and I am very frustrated with your service!",
                )
            )
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="scenario-repeat-4",
                customer_id="repeat-customer",
                channel=ChannelType.WEB,
                content="I want a supervisor. This is ridiculous and unacceptable!",
            )
        )
        assert response.escalate or response.agent in {"complaint_agent", "escalation_agent"}

    asyncio.run(_run())

