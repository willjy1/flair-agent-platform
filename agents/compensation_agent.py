from __future__ import annotations

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.compliance_tools import ComplianceTools


class CompensationAgent(BaseAgent):
    def __init__(self, compliance_tools: ComplianceTools) -> None:
        super().__init__(name="compensation_agent")
        self.compliance_tools = compliance_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        delay_minutes = int(message.context.get("delay_minutes") or message.extracted_entities.get("delay_minutes") or 0)
        if delay_minutes <= 0 and "delay" not in message.inbound.content.lower():
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Please share the flight number and delay details so I can check APPR compensation eligibility.",
                agent=self.name,
                next_actions=["provide_flight_number", "provide_delay_details"],
            )
        delay_hours = round(delay_minutes / 60.0, 2)
        result = await self.compliance_tools.calculate_delay_compensation(delay_hours=delay_hours, carrier_size="small")
        tool_call = ToolCallRecord(
            tool_name="calculate_delay_compensation",
            args={"delay_hours": delay_hours, "carrier_size": "small"},
            result_summary=f"{result['amount']} {result['currency']}",
        )
        if int(result.get("amount", 0)) <= 0:
            text = f"Based on a delay of about {delay_hours:.1f} hours, APPR compensation may not apply yet. I can still help with rebooking or status updates."
        else:
            text = (
                f"Based on a delay of about {delay_hours:.1f} hours, estimated APPR compensation is "
                f"${result['amount']} {result['currency']} ({result['regulation_section']}). "
                "I can also help with rebooking or start a claim intake."
            )
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.RESOLVED,
            response_text=text,
            agent=self.name,
            tool_calls=[tool_call],
            metadata={"compensation": result},
        )

