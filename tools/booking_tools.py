from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional


class BookingAPIError(RuntimeError):
    pass


@dataclass
class MockBooking:
    pnr: str
    customer_id: str
    flight_number: str
    route: str
    departure_date: str
    status: str = "CONFIRMED"
    fare_type: str = "ECONOMY_BASIC"
    ancillaries: Dict[str, int] = field(default_factory=lambda: {"seat": 25, "baggage": 70})
    travel_credit_balance: int = 0


class MockFlairBookingAPIClient:
    def __init__(self) -> None:
        self._bookings: Dict[str, MockBooking] = {
            "AB12CD": MockBooking("AB12CD", "cust-1", "F81234", "YYC-YVR", date.today().isoformat()),
            "ZX98YU": MockBooking("ZX98YU", "cust-2", "F84321", "YVR-YYZ", (date.today() + timedelta(days=1)).isoformat()),
        }

    async def get_booking_details(self, pnr: str) -> dict:
        booking = self._bookings.get(pnr.upper())
        if not booking:
            raise BookingAPIError("booking_not_found")
        return booking.__dict__.copy()

    async def search_available_flights(self, route: str, travel_date: str) -> List[dict]:
        base = route.replace("-", "")
        return [
            {"flight_number": f"F8{base[-2:]}01", "route": route, "date": travel_date, "fare_diff": 0},
            {"flight_number": f"F8{base[-2:]}02", "route": route, "date": travel_date, "fare_diff": 49},
            {"flight_number": f"F8{base[-2:]}03", "route": route, "date": travel_date, "fare_diff": 99},
        ]

    async def modify_booking(self, pnr: str, new_flight_number: str, new_date: str) -> dict:
        booking = self._bookings.get(pnr.upper())
        if not booking:
            raise BookingAPIError("booking_not_found")
        booking.flight_number = new_flight_number
        booking.departure_date = new_date
        booking.status = "REBOOKED"
        return {"pnr": booking.pnr, "status": booking.status, "flight_number": booking.flight_number, "departure_date": booking.departure_date}

    async def cancel_booking(self, pnr: str) -> dict:
        booking = self._bookings.get(pnr.upper())
        if not booking:
            raise BookingAPIError("booking_not_found")
        booking.status = "CANCELLED"
        return {"pnr": booking.pnr, "status": booking.status}

    async def apply_travel_credit(self, pnr: str, amount: int) -> dict:
        booking = self._bookings.get(pnr.upper())
        if not booking:
            raise BookingAPIError("booking_not_found")
        booking.travel_credit_balance += amount
        return {"pnr": booking.pnr, "travel_credit_balance": booking.travel_credit_balance}
