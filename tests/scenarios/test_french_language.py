from __future__ import annotations

import asyncio

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage


def test_french_message_sets_french_language():
    async def _run():
        orchestrator = OrchestratorAgent()
        response = await orchestrator.route_message(
            InboundMessage(
                session_id="scenario-fr",
                customer_id="cust-fr",
                channel=ChannelType.WEB,
                content="Bonjour, je veux un remboursement pour la reservation AB12CD.",
            )
        )
        assert response.language == "fr"
        assert response.intent is not None

    asyncio.run(_run())

