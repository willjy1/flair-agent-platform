from __future__ import annotations

import re

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.crm_tools import CRMTools


class BaggageAgent(BaseAgent):
    def __init__(self, crm_tools: CRMTools) -> None:
        super().__init__(name="baggage_agent")
        self.crm_tools = crm_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        text = message.inbound.content
        claim_match = re.search(r"\b([A-Z]{2}\d{6,10})\b", text.upper())
        if not claim_match:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Please share your baggage claim number (for example, AB1234567), and I’ll check the bag status.",
                agent=self.name,
                next_actions=["provide_baggage_claim_number"],
            )
        claim_number = claim_match.group(1)
        located = claim_number.endswith(("1", "2"))
        if located:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.RESOLVED,
                response_text=f"I located baggage claim {claim_number}. The bag is in transit and estimated to arrive on the next flight today.",
                agent=self.name,
                metadata={"claim_number": claim_number, "baggage_status": "IN_TRANSIT"},
            )
        case = await self.crm_tools.create_case(
            customer_id=message.inbound.customer_id,
            subject="Baggage tracing escalation",
            summary=f"Baggage claim {claim_number} not located in automated trace.",
            metadata={"claim_number": claim_number},
        )
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.ESCALATED,
            response_text="I couldn't confirm the baggage location yet, so I've escalated this to the baggage team for manual tracing.",
            agent=self.name,
            escalate=True,
            tool_calls=[ToolCallRecord(tool_name="create_case", args={"subject": "Baggage tracing escalation"}, result_summary=case["case_id"])],
            metadata={"crm_case_id": case["case_id"], "claim_number": claim_number},
        )

