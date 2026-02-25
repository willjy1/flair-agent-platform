from __future__ import annotations

from datetime import datetime
from typing import Dict


class FlightStatusTools:
    def __init__(self) -> None:
        self._statuses = {
            "F81234": {"status": "DELAYED", "delay_minutes": 47, "departure_gate": "B12"},
            "F84321": {"status": "ON_TIME", "delay_minutes": 0, "departure_gate": "A03"},
        }

    async def get_realtime_status(self, flight_number: str) -> Dict[str, object]:
        base = self._statuses.get(flight_number.upper(), {"status": "SCHEDULED", "delay_minutes": 0, "departure_gate": "TBD"})
        return {"flight_number": flight_number.upper(), "timestamp": datetime.utcnow().isoformat(), **base}

    async def list_departures_next_hours(self, hours: int = 6) -> list[dict]:
        return [
            {"flight_number": "F81234", "departure_iso": datetime.utcnow().isoformat(), "route": "YYC-YVR", "status": "DELAYED"},
            {"flight_number": "F84321", "departure_iso": datetime.utcnow().isoformat(), "route": "YVR-YYZ", "status": "ON_TIME"},
        ]
