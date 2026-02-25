from __future__ import annotations

from typing import Dict, List


class NotificationTools:
    def __init__(self) -> None:
        self.sent: List[dict] = []

    async def send_sms(self, phone: str, message: str) -> Dict[str, object]:
        payload = {"channel": "sms", "to": phone, "message": message, "status": "SENT"}
        self.sent.append(payload)
        return payload

    async def send_email(self, email: str, subject: str, body: str) -> Dict[str, object]:
        payload = {"channel": "email", "to": email, "subject": subject, "body": body, "status": "SENT"}
        self.sent.append(payload)
        return payload

    async def send_push(self, customer_id: str, title: str, body: str) -> Dict[str, object]:
        payload = {"channel": "push", "customer_id": customer_id, "title": title, "body": body, "status": "SENT"}
        self.sent.append(payload)
        return payload

    async def dual_confirm(self, email: str | None, phone: str | None, subject: str, body: str) -> List[dict]:
        outputs: List[dict] = []
        if email:
            outputs.append(await self.send_email(email, subject, body))
        if phone:
            outputs.append(await self.send_sms(phone, body))
        return outputs
