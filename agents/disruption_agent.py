from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.booking_tools import BookingAPIError, MockFlairBookingAPIClient
from tools.flight_status_tools import FlightStatusTools


class DisruptionAgent(BaseAgent):
    def __init__(self, flight_status_tools: FlightStatusTools, booking_tools: MockFlairBookingAPIClient) -> None:
        super().__init__(name="disruption_agent")
        self.flight_status_tools = flight_status_tools
        self.booking_tools = booking_tools

    async def process(self, message: AgentMessage) -> AgentResponse:
        entities = dict(message.extracted_entities)
        tools: List[ToolCallRecord] = []
        text = (message.inbound.content or "").strip()
        lower = text.lower()
        flight_number = str(entities.get("flight_number") or "").upper()
        pnr = str(entities.get("booking_reference") or "").upper()
        wants_rebook = any(k in lower for k in ["rebook", "change flight", "next flight", "alternative", "options"])
        booking = None

        has_explicit_identifier = bool(re.search(r"\bF8\d{3,4}\b", text.upper())) or bool(
            re.search(r"\b[A-Z0-9]{6}\b", text.upper())
        )
        session_age_seconds = self._session_age_seconds(message.context.get("session_updated_at"))
        if (
            flight_number
            and not has_explicit_identifier
            and "status" in lower
            and session_age_seconds is not None
            and session_age_seconds > 2 * 60 * 60
        ):
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    f"I still have a recent flight in this conversation ({flight_number}), but it may be out of date. "
                    "Do you want me to check that flight, or would you like to share a different flight number or booking reference?"
                ),
                agent=self.name,
                next_actions=["confirm_saved_flight", "provide_flight_number_or_booking_reference"],
                metadata={"suggested_flight_number": flight_number},
            )

        if not flight_number and pnr:
            try:
                booking = await self.booking_tools.get_booking_details(pnr)
                tools.append(ToolCallRecord(tool_name="get_booking_details", args={"pnr": pnr}, result_summary=booking["flight_number"]))
                flight_number = str(booking.get("flight_number", "")).upper()
            except BookingAPIError:
                pass

        if not flight_number:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="Please share your flight number (for example F81234) or booking reference so I can check the latest status.",
                agent=self.name,
                next_actions=["provide_flight_number_or_booking_reference"],
            )

        status = await self.flight_status_tools.get_realtime_status(flight_number)
        tools.append(ToolCallRecord(tool_name="get_realtime_status", args={"flight_number": flight_number}, result_summary=str(status.get("status"))))

        delay_minutes = int(status.get("delay_minutes", 0))
        text_parts = [
            f"Flight {flight_number} is currently {status['status']}.",
            f"Gate {status.get('departure_gate', 'TBD')}.",
        ]
        if delay_minutes > 0:
            text_parts.append(f"Current delay: {delay_minutes} minutes.")
        else:
            text_parts.append("No delay is currently showing.")

        next_actions = []
        concierge_options = []
        if delay_minutes > 0:
            next_actions.append("rebooking_options")
        if delay_minutes >= 180:
            next_actions.append("compensation_check")
            text_parts.append("This may qualify for APPR compensation depending on the final disruption details.")
        elif delay_minutes > 0:
            text_parts.append("If you want, I can also help with rebooking options.")

        if (delay_minutes > 0 or status.get("status") == "CANCELLED" or wants_rebook) and (booking or pnr):
            if booking is None and pnr:
                try:
                    booking = await self.booking_tools.get_booking_details(pnr)
                    tools.append(ToolCallRecord(tool_name="get_booking_details", args={"pnr": pnr}, result_summary=booking["flight_number"]))
                except BookingAPIError:
                    booking = None
            if booking:
                route = str(booking.get("route") or entities.get("route") or "")
                travel_date = str(booking.get("departure_date") or entities.get("travel_date") or "")
                if route and travel_date:
                    options = await self.booking_tools.search_available_flights(route=route, travel_date=travel_date)
                    tools.append(
                        ToolCallRecord(
                            tool_name="search_available_flights",
                            args={"route": route, "travel_date": travel_date},
                            result_summary=f"{len(options)} options",
                        )
                    )
                    concierge_options = list(options[:3])
                    if concierge_options:
                        text_parts.append("I found rebooking options and can walk you through them now.")
                        for idx, opt in enumerate(concierge_options, start=1):
                            text_parts.append(
                                f"Option {idx}: {opt.get('flight_number')} with fare difference ${opt.get('fare_diff', 0)} CAD."
                            )
                        if "confirm_rebooking_option" not in next_actions:
                            next_actions.append("confirm_rebooking_option")

        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.CONFIRMING if next_actions else ConversationState.RESOLVED,
            response_text=" ".join(text_parts),
            agent=self.name,
            tool_calls=tools,
            next_actions=next_actions,
            metadata={
                "flight_status": status,
                "delay_minutes": delay_minutes,
                "rebooking_options": concierge_options,
                **({"booking": booking} if isinstance(booking, dict) else {}),
            },
        )

    def _session_age_seconds(self, updated_at: object) -> float | None:
        if not updated_at:
            return None
        try:
            raw = str(updated_at).replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        except Exception:
            return None
