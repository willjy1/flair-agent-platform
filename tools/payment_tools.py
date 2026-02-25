from __future__ import annotations

from typing import Dict


class PaymentError(RuntimeError):
    pass


class PaymentTools:
    async def initiate_refund(self, booking_id: str, amount_cad: int, payment_method: str = "card") -> Dict[str, object]:
        if amount_cad < 0:
            raise PaymentError("invalid_amount")
        return {
            "booking_id": booking_id,
            "amount_cad": amount_cad,
            "payment_method": payment_method,
            "refund_id": f"RF-{booking_id[-4:]}-{amount_cad}",
            "status": "PROCESSING",
        }

    async def issue_voucher(self, customer_id: str, amount_cad: int, bonus_percent: int = 15) -> Dict[str, object]:
        bonus = round(amount_cad * (bonus_percent / 100))
        total = amount_cad + bonus
        return {"customer_id": customer_id, "voucher_value_cad": total, "base_amount_cad": amount_cad, "bonus_cad": bonus, "status": "ISSUED"}
