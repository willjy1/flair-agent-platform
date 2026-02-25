from __future__ import annotations

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.crm_tools import CRMTools


class AccessibilityAgent(BaseAgent):
    def __init__(self, crm_tools: CRMTools) -> None:
        super().__init__(name="accessibility_agent")
        self.crm_tools = crm_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        text = message.inbound.content.lower()
        if any(k in text for k in ["wheelchair", "mobility", "special assistance", "accessible"]):
            case = await self.crm_tools.create_case(
                customer_id=message.inbound.customer_id,
                subject="Accessibility support request",
                summary=message.inbound.content[:500],
                metadata={"channel": message.inbound.channel.value},
            )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "I can help document your accessibility request and route it as a priority support request. "
                    "For urgent assistance, Flair's published accessibility line is 1-833-382-5421. "
                    "Please tell me the type of assistance you need and, if available, your flight number or booking reference."
                ),
                agent=self.name,
                tool_calls=[ToolCallRecord(tool_name="create_case", args={"subject": "Accessibility support request"}, result_summary=case["case_id"])],
                next_actions=["confirm_assistance_details", "provide_flight_number_or_booking_reference", "human_agent_if_urgent"],
                metadata={"crm_case_id": case["case_id"], "priority_lane": "accessibility"},
            )
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.CONFIRMING,
            response_text="Please tell me what assistance you need (for example wheelchair support, mobility devices, or airport assistance) and your flight details if available. I will keep it in this conversation so you do not need to repeat it.",
            agent=self.name,
            next_actions=["confirm_assistance_details", "provide_flight_number_or_booking_reference"],
        )
