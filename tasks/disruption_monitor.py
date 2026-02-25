from __future__ import annotations

import asyncio
from typing import List

from celery import Celery

from agents.orchestrator import OrchestratorAgent
from models.schemas import ChannelType, InboundMessage
from settings import SETTINGS


celery_app = Celery("flair_agent_platform")
if SETTINGS.redis_url:
    celery_app.conf.broker_url = SETTINGS.redis_url
    celery_app.conf.result_backend = SETTINGS.redis_url
celery_app.conf.beat_schedule = {
    "monitor-disruptions-every-60s": {
        "task": "tasks.disruption_monitor.monitor_disruptions",
        "schedule": 60.0,
    }
}


class DisruptionMonitor:
    def __init__(self, orchestrator: OrchestratorAgent | None = None) -> None:
        self.orchestrator = orchestrator or OrchestratorAgent()

    async def run_once(self) -> dict:
        flights = await self.orchestrator.flight_status_tools.list_departures_next_hours(6)
        affected = [f for f in flights if f.get("status") in {"DELAYED", "CANCELLED"}]
        outreach_results: List[dict] = []

        # Dev-mode affected booking identification from mock booking client.
        mock_bookings = getattr(self.orchestrator.booking_tools, "_bookings", {})
        for flight in affected:
            flight_number = str(flight.get("flight_number"))
            impacted = [b for b in mock_bookings.values() if getattr(b, "flight_number", "") == flight_number]
            for booking in impacted:
                urgency = 5
                if flight.get("status") == "CANCELLED":
                    urgency += 3
                if flight.get("status") == "DELAYED":
                    urgency += 2
                msg = (
                    f"Proactive disruption support for flight {flight_number}: "
                    f"we detected status {flight.get('status')}. Can we help with rebooking or compensation information?"
                )
                response = await self.orchestrator.route_message(
                    InboundMessage(
                        session_id=f"proactive-{booking.pnr}",
                        customer_id=booking.customer_id,
                        channel=ChannelType.SMS,
                        content=msg,
                        metadata={"proactive": True, "urgency_seed": urgency, "booking_reference": booking.pnr},
                    )
                )
                outreach_results.append(
                    {
                        "flight_number": flight_number,
                        "pnr": booking.pnr,
                        "customer_id": booking.customer_id,
                        "agent": response.agent,
                        "state": response.state.value,
                        "response_preview": response.response_text[:140],
                    }
                )
        await self.orchestrator.analytics_tools.log_event(
            "disruption_monitor_run",
            {"flights_checked": len(flights), "affected_flights": len(affected), "proactive_outreach": len(outreach_results)},
        )
        return {"flights_checked": len(flights), "affected_flights": len(affected), "outreach": outreach_results}


@celery_app.task(name="tasks.disruption_monitor.monitor_disruptions")
def monitor_disruptions() -> dict:
    monitor = DisruptionMonitor()
    return asyncio.run(monitor.run_once())

