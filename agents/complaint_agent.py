from __future__ import annotations

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.crm_tools import CRMTools


class ComplaintAgent(BaseAgent):
    def __init__(self, crm_tools: CRMTools) -> None:
        super().__init__(name="complaint_agent")
        self.crm_tools = crm_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        case = await self.crm_tools.create_case(
            customer_id=message.inbound.customer_id,
            subject="Customer complaint",
            summary=message.inbound.content[:1000],
            metadata={"channel": message.inbound.channel.value},
        )
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.CONFIRMING,
            response_text="I’m sorry about your experience. I’ve documented your complaint and can continue gathering details so the support team has the full context.",
            agent=self.name,
            tool_calls=[ToolCallRecord(tool_name="create_case", args={"subject": "Customer complaint"}, result_summary=case["case_id"])],
            next_actions=["collect_complaint_details"],
            metadata={"crm_case_id": case["case_id"]},
        )

