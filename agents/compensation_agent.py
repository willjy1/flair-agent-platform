from __future__ import annotations

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tenants.registry import TenantProfile
from tools.compliance_tools import ComplianceTools


class CompensationAgent(BaseAgent):
    def __init__(
        self,
        compliance_tools: ComplianceTools,
        tenant_slug: str = "flair",
        tenant_profile: TenantProfile | None = None,
    ) -> None:
        super().__init__(name="compensation_agent")
        self.compliance_tools = compliance_tools
        self.tenant_slug = (tenant_slug or "flair").lower()
        self.tenant_profile = tenant_profile

    async def process(self, message: AgentMessage) -> AgentResponse:
        if not self._supports_appr():
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "Compensation and reimbursement rules depend on the service type, route, and local regulations. "
                    "I can help gather the details and point you to the correct official claim or support channel."
                ),
                agent=self.name,
                next_actions=["share_booking_or_transaction_details", "continue_current_request", "human_agent_if_urgent"],
                metadata={"compensation_framework": "tenant_specific_or_unknown"},
            )
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

    def _supports_appr(self) -> bool:
        if self.tenant_slug == "flair":
            return True
        md = dict(getattr(self.tenant_profile, "metadata", {}) or {})
        if bool(md.get("supports_appr")):
            return True
        if str(getattr(self.tenant_profile, "locale", "") or "").lower().endswith("ca"):
            return True
        if str(md.get("country_focus") or "").lower() == "canada":
            return True
        return False
