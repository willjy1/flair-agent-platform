from __future__ import annotations

import re
from typing import Dict, Iterable


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")


class GDPRHandler:
    def redact_pii(self, text: str) -> str:
        text = EMAIL_RE.sub("[redacted-email]", text)
        text = PHONE_RE.sub("[redacted-phone]", text)
        return text

    def delete_customer_records(self, customer_id: str, stores: Iterable[object]) -> Dict[str, object]:
        deleted = []
        for store in stores:
            if hasattr(store, "delete_customer"):
                store.delete_customer(customer_id)
                deleted.append(store.__class__.__name__)
        return {"customer_id": customer_id, "deleted_from": deleted}

    def export_customer_records(self, customer_id: str, stores: Iterable[object]) -> Dict[str, object]:
        exported: Dict[str, object] = {"customer_id": customer_id, "records": {}}
        for store in stores:
            if hasattr(store, "export_customer"):
                exported["records"][store.__class__.__name__] = store.export_customer(customer_id)
        return exported
