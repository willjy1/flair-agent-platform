from __future__ import annotations

from typing import Dict

from compliance.appr_rules import APPRCalculator


class ComplianceError(RuntimeError):
    pass


class ComplianceTools:
    def __init__(self) -> None:
        self.appr = APPRCalculator()

    async def calculate_delay_compensation(self, delay_hours: float, carrier_size: str = "small") -> Dict[str, object]:
        if delay_hours < 0:
            raise ComplianceError("invalid_delay")
        return self.appr.delay_compensation(delay_hours, carrier_size=carrier_size)

    async def refund_timeline(self, payment_method: str) -> Dict[str, object]:
        days = self.appr.refund_timeline_days(payment_method)
        return {"payment_method": payment_method, "timeline_days": days, "regulation_section": "APPR-refund-timeline"}

    async def denied_boarding_compensation(self, arrival_delay_hours: float) -> Dict[str, object]:
        if arrival_delay_hours < 0:
            raise ComplianceError("invalid_arrival_delay")
        return self.appr.denied_boarding_compensation(arrival_delay_hours)

    async def tarmac_delay_rules(self) -> Dict[str, object]:
        return self.appr.tarmac_delay_rules()
