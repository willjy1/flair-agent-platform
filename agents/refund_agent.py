from __future__ import annotations

from typing import List

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.booking_tools import BookingAPIError, MockFlairBookingAPIClient
from tools.compliance_tools import ComplianceTools
from tools.payment_tools import PaymentTools


class RefundAgent(BaseAgent):
    def __init__(
        self,
        booking_tools: MockFlairBookingAPIClient,
        compliance_tools: ComplianceTools,
        payment_tools: PaymentTools,
    ) -> None:
        super().__init__(name="refund_agent")
        self.booking_tools = booking_tools
        self.compliance_tools = compliance_tools
        self.payment_tools = payment_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        entities = dict(message.extracted_entities)
        pnr = str(entities.get("booking_reference", "")).upper()
        text = message.inbound.content.lower()
        stripped = text.strip()
        tools: List[ToolCallRecord] = []
        pending_refund = entities.get("_pending_refund_amount_cad")
        last_next_actions = [str(x) for x in (entities.get("_last_next_actions") or [])] if isinstance(entities.get("_last_next_actions"), list) else []

        if any(k in text for k in ["charge issue", "billing issue", "payment issue"]):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "I can help with a charge issue. Is it an unauthorized charge, a duplicate charge, or an incorrect amount? "
                    "If you already have the booking reference, you can share it now and I will guide the next step."
                ),
                agent=self.name,
                next_actions=["share_booking_or_transaction_details", "human_agent_if_urgent"],
                metadata={"charge_issue_type": "general"},
            )

        if any(k in text for k in ["unauthorized charge", "fraud charge", "fraudulent charge"]):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "If you suspect an unauthorized charge, contact your bank or card issuer immediately first. "
                    "After that, I can help you gather the booking or transaction details Flair support will need for a charge investigation."
                ),
                agent=self.name,
                next_actions=["contact_bank_if_fraud", "share_booking_or_transaction_details", "human_agent_if_urgent"],
                metadata={"charge_issue_type": "unauthorized"},
            )

        if any(k in text for k in ["duplicate charge", "incorrect charge", "charged twice"]):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "I can help with that. For a duplicate or incorrect charge review, please share your booking reference or the transaction details (date, amount, and last 4 digits of the card if you have them). "
                    "I will route the case with the right details so you do not have to repeat yourself."
                ),
                agent=self.name,
                next_actions=["share_booking_or_transaction_details", "human_agent_if_urgent"],
                metadata={"charge_issue_type": "duplicate_or_incorrect"},
            )

        if not pnr:
            if stripped in {"no", "nope", "not now"}:
                return AgentResponse(
                    session_id=message.inbound.session_id,
                    customer_id=message.inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "No problem. I can explain the general refund process and timelines, but I need the booking reference to review your exact options or submit anything."
                    ),
                    agent=self.name,
                    next_actions=["provide_booking_reference", "human_agent_if_urgent", "switch_to_new_request"],
                )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Please share your booking reference so I can check the booking and review refund options.",
                agent=self.name,
                next_actions=["provide_booking_reference"],
            )

        if stripped in {"yes", "do it", "go ahead", "confirm"} and pending_refund and {"submit_refund", "choose_travel_credit"} <= set(last_next_actions):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="I can do that. Would you like me to submit the refund to your original payment method, or issue travel credit with the bonus?",
                agent=self.name,
                next_actions=["submit_refund", "choose_travel_credit"],
                metadata={"refund_amount_cad": pending_refund},
            )

        if stripped in {"no", "nope", "not now"} and pending_refund and {"submit_refund", "choose_travel_credit"} <= set(last_next_actions):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Okay, I will not submit anything. I can keep helping with questions about the refund, or you can continue later without starting over.",
                agent=self.name,
                next_actions=["continue_current_request", "switch_to_new_request", "human_agent_if_urgent"],
                metadata={"refund_amount_cad": pending_refund},
            )

        try:
            booking = await self.booking_tools.get_booking_details(pnr)
            tools.append(ToolCallRecord(tool_name="get_booking_details", args={"pnr": pnr}, result_summary="booking_found"))
        except BookingAPIError:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=f"I couldn't find booking {pnr}. Please check the reference and try again.",
                agent=self.name,
            )

        base_fare = 120
        ancillaries_total = sum(int(v) for v in booking.get("ancillaries", {}).values())
        refund_amount = base_fare + ancillaries_total
        timeline = await self.compliance_tools.refund_timeline("card")
        tools.append(ToolCallRecord(tool_name="refund_timeline", args={"payment_method": "card"}, result_summary=f"{timeline['timeline_days']} days"))

        if "credit" in text and "refund" not in text:
            voucher = await self.payment_tools.issue_voucher(
                customer_id=message.inbound.customer_id,
                amount_cad=refund_amount,
                bonus_percent=15,
            )
            tools.append(
                ToolCallRecord(
                    tool_name="issue_voucher",
                    args={"amount_cad": refund_amount, "bonus_percent": 15},
                    result_summary=f"{voucher['voucher_value_cad']} CAD",
                )
            )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.RESOLVED,
                response_text=(
                    f"I issued a travel credit worth ${voucher['voucher_value_cad']} CAD for booking {pnr} "
                    f"(${voucher['base_amount_cad']} base value plus ${voucher['bonus_cad']} bonus)."
                ),
                agent=self.name,
                tool_calls=tools,
                metadata={"voucher": voucher},
            )

        if any(k in text for k in ["submit refund", "refund now", "process refund", "yes refund"]):
            refund = await self.payment_tools.initiate_refund(booking_id=pnr, amount_cad=refund_amount, payment_method="card")
            tools.append(
                ToolCallRecord(
                    tool_name="initiate_refund",
                    args={"booking_id": pnr, "amount_cad": refund_amount},
                    result_summary=refund["status"],
                )
            )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.RESOLVED,
                response_text=(
                    f"I started a refund of ${refund_amount} CAD to the original payment method for booking {pnr}. "
                    f"Reference: {refund['refund_id']}. Card refunds can take up to {timeline['timeline_days']} days."
                ),
                agent=self.name,
                tool_calls=tools,
                metadata={"refund": refund},
            )

        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.CONFIRMING,
            response_text=(
                f"For booking {pnr}, I estimate a refund of ${refund_amount} CAD (fare plus ancillaries). "
                f"Card refunds can take up to {timeline['timeline_days']} days. "
                "I can submit the refund now, or issue travel credit with a 15% bonus."
            ),
            agent=self.name,
            tool_calls=tools,
            next_actions=["submit_refund", "choose_travel_credit"],
            metadata={"refund_amount_cad": refund_amount, "refund_timeline_days": timeline["timeline_days"]},
        )
