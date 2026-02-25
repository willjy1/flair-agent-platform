from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class APPRThreshold:
    min_hours: float
    max_hours: float | None
    amount_cad: int
    regulation_section: str


class APPRCalculator:
    def __init__(self) -> None:
        self.small_carrier_delay_thresholds = [
            APPRThreshold(3.0, 6.0, 125, "APPR-19(1)(a)"),
            APPRThreshold(6.0, 9.0, 250, "APPR-19(1)(b)"),
            APPRThreshold(9.0, None, 500, "APPR-19(1)(c)"),
        ]

    def delay_compensation(self, delay_hours: float, carrier_size: str = "small") -> Dict[str, object]:
        thresholds = self.small_carrier_delay_thresholds
        if carrier_size.lower() != "small":
            thresholds = [
                APPRThreshold(3.0, 6.0, 400, "APPR-19(2)(a)"),
                APPRThreshold(6.0, 9.0, 700, "APPR-19(2)(b)"),
                APPRThreshold(9.0, None, 1000, "APPR-19(2)(c)"),
            ]
        for rule in thresholds:
            if delay_hours >= rule.min_hours and (rule.max_hours is None or delay_hours < rule.max_hours):
                return {
                    "amount": rule.amount_cad,
                    "currency": "CAD",
                    "regulation_section": rule.regulation_section,
                    "calculation_breakdown": f"{carrier_size} carrier delay {delay_hours:.1f}h",
                    "payment_method_options": ["cash", "bank_transfer", "travel_credit"],
                }
        return {
            "amount": 0,
            "currency": "CAD",
            "regulation_section": "APPR-not-eligible",
            "calculation_breakdown": f"Delay {delay_hours:.1f}h is below threshold",
            "payment_method_options": [],
        }

    def refund_timeline_days(self, payment_method: str) -> int:
        method = payment_method.lower()
        if method in {"cash", "debit_cash"}:
            return 0
        return 30

    def denied_boarding_compensation(self, arrival_delay_hours: float) -> Dict[str, object]:
        if arrival_delay_hours < 0:
            arrival_delay_hours = 0
        if arrival_delay_hours < 6:
            amount = 900
            section = "APPR-denied-boarding-1"
        elif arrival_delay_hours < 9:
            amount = 1800
            section = "APPR-denied-boarding-2"
        else:
            amount = 2400
            section = "APPR-denied-boarding-3"
        return {
            "amount": amount,
            "currency": "CAD",
            "regulation_section": section,
            "calculation_breakdown": f"Denied boarding arrival delay {arrival_delay_hours:.1f}h",
            "payment_method_options": ["cash", "bank_transfer", "travel_credit"],
        }

    def tarmac_delay_rules(self) -> Dict[str, object]:
        return {
            "max_tarmac_hours_default": 3,
            "extension_conditions": ["takeoff imminent", "safety/security reasons", "ATC control constraints"],
            "carrier_obligations": ["ventilation", "food_and_water", "communication", "lavatory_access", "medical_assistance_if_needed"],
            "regulation_section": "APPR-tarmac-delay",
        }
