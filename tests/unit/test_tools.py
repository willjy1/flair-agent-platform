from __future__ import annotations

import asyncio

from tools.booking_tools import MockFlairBookingAPIClient
from tools.compliance_tools import ComplianceTools
from tools.payment_tools import PaymentTools


def test_mock_booking_lookup_and_rebook():
    async def _run():
        booking = MockFlairBookingAPIClient()
        details = await booking.get_booking_details("AB12CD")
        assert details["pnr"] == "AB12CD"
        options = await booking.search_available_flights(details["route"], details["departure_date"])
        assert len(options) >= 1
        updated = await booking.modify_booking("AB12CD", options[0]["flight_number"], details["departure_date"])
        assert updated["status"] == "REBOOKED"

    asyncio.run(_run())


def test_compliance_and_payment_tools():
    async def _run():
        compliance = ComplianceTools()
        payment = PaymentTools()
        comp = await compliance.calculate_delay_compensation(3.5, carrier_size="small")
        assert comp["amount"] == 125
        refund = await payment.initiate_refund("AB12CD", 200)
        assert refund["status"] == "PROCESSING"

    asyncio.run(_run())

