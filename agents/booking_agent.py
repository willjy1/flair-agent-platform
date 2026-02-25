from __future__ import annotations

from typing import List

from agents.base import BaseAgent
from memory.customer_profile import CustomerProfileRepository
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.booking_tools import BookingAPIError, MockFlairBookingAPIClient
from tools.notification_tools import NotificationTools


class BookingAgent(BaseAgent):
    def __init__(
        self,
        booking_tools: MockFlairBookingAPIClient,
        notification_tools: NotificationTools,
        profiles: CustomerProfileRepository,
    ) -> None:
        super().__init__(name="booking_agent")
        self.booking_tools = booking_tools
        self.notification_tools = notification_tools
        self.profiles = profiles

    async def process(self, message: AgentMessage) -> AgentResponse:
        tools: List[ToolCallRecord] = []
        text = message.inbound.content.lower()
        stripped = text.strip()
        entities = dict(message.extracted_entities)
        pnr = str(entities.get("booking_reference", "")).upper()
        missed_flight = any(k in text for k in ["missed my flight", "missed flight", "no-show"])
        same_day_urgency = any(k in text for k in ["today", "tonight", "same day", "asap", "now"])

        if missed_flight and not pnr:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "I'm sorry that happened. I can help you quickly, but I need your 6-character booking reference first to check the booking. "
                    "If you still need to travel today, tell me that as well so I prioritize rebooking options. "
                    "If you want to contact Flair directly right now, Flair's published call center number is 1-403-709-0808. Wait times may vary."
                ),
                agent=self.name,
                next_actions=["provide_booking_reference", "urgent_human_help_if_needed"],
                metadata={"missed_flight_rescue": True},
            )

        if not pnr:
            if stripped in {"no", "nope", "not now"}:
                return AgentResponse(
                    session_id=message.inbound.session_id,
                    customer_id=message.inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "Understood. I cannot check or change the booking without the booking reference. If the trip is urgent, I can help you move to human support immediately."
                    ),
                    agent=self.name,
                    next_actions=["human_agent_if_urgent", "switch_to_new_request"],
                )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Please share your 6-character booking reference (PNR) so I can look up the booking and help with changes or cancellation.",
                agent=self.name,
                next_actions=["provide_booking_reference"],
            )

        try:
            details = await self.booking_tools.get_booking_details(pnr)
            tools.append(
                ToolCallRecord(
                    tool_name="get_booking_details",
                    args={"pnr": pnr},
                    result_summary=f"{details['status']} {details['flight_number']}",
                )
            )
        except BookingAPIError:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=f"I couldn't find booking {pnr}. Please check the booking reference and try again.",
                agent=self.name,
                next_actions=["verify_booking_reference"],
            )

        profile = await self.profiles.get_profile(message.inbound.customer_id)
        is_cancel = "cancel" in text
        is_rebook = any(k in text for k in ["rebook", "change flight", "modify booking", "switch flight"])
        pending_options = entities.get("_pending_rebooking_options")

        if isinstance(pending_options, list) and pending_options:
            selected_idx = self._extract_option_index(text)
            if selected_idx is not None:
                zero_idx = selected_idx - 1
                if zero_idx < 0 or zero_idx >= len(pending_options):
                    return AgentResponse(
                        session_id=message.inbound.session_id,
                        customer_id=message.inbound.customer_id,
                        state=ConversationState.CONFIRMING,
                        response_text=f"I found rebooking options, but option {selected_idx} is not available. Please choose one of the listed options.",
                        agent=self.name,
                        tool_calls=tools,
                        next_actions=["confirm_rebooking_option"],
                        metadata={"rebooking_options": pending_options},
                    )
                selected = pending_options[zero_idx]
                changed = await self.booking_tools.modify_booking(
                    pnr=pnr,
                    new_flight_number=str(selected.get("flight_number") or details.get("flight_number")),
                    new_date=str(selected.get("date") or details.get("departure_date")),
                )
                tools.append(
                    ToolCallRecord(
                        tool_name="modify_booking",
                        args={"pnr": pnr, "new_flight_number": changed["flight_number"], "new_date": changed["departure_date"]},
                        result_summary=changed["status"],
                    )
                )
                return AgentResponse(
                    session_id=message.inbound.session_id,
                    customer_id=message.inbound.customer_id,
                    state=ConversationState.RESOLVED,
                    response_text=(
                        f"You're rebooked. Booking {pnr} is now on flight {changed['flight_number']} for {changed['departure_date']}. "
                        "If you'd like, I can also help with next steps for check-in or airport timing."
                    ),
                    agent=self.name,
                    tool_calls=tools,
                    next_actions=["airport_next_steps"],
                    metadata={"booking": {**details, **changed}, "rebooking_options": []},
                )
            if text.strip() in {"yes", "do it", "go ahead", "confirm"}:
                return AgentResponse(
                    session_id=message.inbound.session_id,
                    customer_id=message.inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text="I can do that. Please tell me which option you want (for example, option 1 or option 2).",
                    agent=self.name,
                    tool_calls=tools,
                    next_actions=["confirm_rebooking_option"],
                    metadata={"rebooking_options": pending_options},
                )
            if stripped in {"no", "nope", "not now"}:
                return AgentResponse(
                    session_id=message.inbound.session_id,
                    customer_id=message.inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text="Okay. I have not changed your booking. I can keep looking at other options, or I can help you with refund or human support next.",
                    agent=self.name,
                    tool_calls=tools,
                    next_actions=["rebooking_options", "submit_refund", "human_agent_if_urgent"],
                    metadata={"rebooking_options": pending_options},
                )

        if is_cancel:
            cancelled = await self.booking_tools.cancel_booking(pnr)
            tools.append(ToolCallRecord(tool_name="cancel_booking", args={"pnr": pnr}, result_summary=cancelled["status"]))
            await self.notification_tools.dual_confirm(
                email=profile.email,
                phone=profile.phone,
                subject="Flair booking cancellation confirmation",
                body=f"Your booking {pnr} has been cancelled.",
            )
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.RESOLVED,
                response_text=f"Your booking {pnr} has been cancelled, and I have prepared confirmation notifications.",
                agent=self.name,
                tool_calls=tools,
            )

        if is_rebook:
            route = str(entities.get("route") or details.get("route") or "")
            travel_date = str(entities.get("travel_date") or details.get("departure_date"))
            options = await self.booking_tools.search_available_flights(route=route, travel_date=travel_date)
            tools.append(
                ToolCallRecord(
                    tool_name="search_available_flights",
                    args={"route": route, "travel_date": travel_date},
                    result_summary=f"{len(options)} options",
                )
            )
            preferred = profile.seat_preference or "seat preference"
            lines = [f"I found {len(options)} rebooking options for booking {pnr} ({route} on {travel_date})."]
            for idx, opt in enumerate(options[:3], start=1):
                lines.append(f"Option {idx}: {opt['flight_number']} (fare difference ${opt['fare_diff']} CAD).")
            lines.append(f"Reply with an option number to continue. I will keep your {preferred} in mind where possible.")
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=" ".join(lines),
                agent=self.name,
                tool_calls=tools,
                next_actions=["confirm_rebooking_option"],
                metadata={"rebooking_options": options},
            )

        if missed_flight:
            rescue_lines = [
                f"I'm sorry you missed your flight. I found booking {pnr} for flight {details['flight_number']} on {details['departure_date']}.",
                "I can check rebooking options now and help you move to the fastest next available option.",
            ]
            if same_day_urgency:
                rescue_lines.append("You mentioned this is urgent, so I will prioritize same-day options where possible.")
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=" ".join(rescue_lines),
                agent=self.name,
                tool_calls=tools,
                next_actions=["check_rebooking_options", "human_agent_if_urgent"],
                metadata={"booking": details, "missed_flight_rescue": True},
            )

        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.RESOLVED,
            response_text=(
                f"I found booking {pnr}: flight {details['flight_number']} on {details['departure_date']} "
                f"({details['route']}) with status {details['status']}. I can help with changes, rebooking, or cancellation."
            ),
            agent=self.name,
            tool_calls=tools,
            metadata={"booking": details},
        )

    def _extract_option_index(self, text: str) -> int | None:
        import re

        match = re.search(r"\boption\s*(\d+)\b", text)
        if match:
            return int(match.group(1))
        stripped = text.strip()
        if stripped.isdigit():
            return int(stripped)
        return None
