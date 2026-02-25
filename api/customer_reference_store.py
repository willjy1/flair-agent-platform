from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, List

from settings import SETTINGS


@dataclass
class SupportReferenceRecord:
    reference: str
    tenant: str
    customer_id: str
    session_id: str
    status: str
    channel: str
    summary: str
    next_steps: List[str] = field(default_factory=list)
    events: List[Dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, object] = field(default_factory=dict)


class CustomerReferenceStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or SETTINGS.support_reference_store_path
        self._records: Dict[str, SupportReferenceRecord] = {}
        self._lock = Lock()
        self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            return
        for ref, raw in dict(payload.get("records", {})).items():
            try:
                self._records[str(ref).upper()] = SupportReferenceRecord(**raw)
            except Exception:
                continue

    def _persist(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "records": {ref: asdict(record) for ref, record in self._records.items()},
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True)
        os.replace(tmp, self.path)

    def upsert(self, record: SupportReferenceRecord) -> SupportReferenceRecord:
        with self._lock:
            record.reference = record.reference.upper()
            record.updated_at = datetime.utcnow().isoformat()
            self._records[record.reference] = record
            self._persist()
            return record

    def append_event(self, reference: str, event_type: str, summary: str, metadata: Dict[str, object] | None = None) -> SupportReferenceRecord | None:
        with self._lock:
            record = self._records.get(reference.upper())
            if not record:
                return None
            record.events.append(
                {
                    "type": event_type,
                    "summary": summary[:400],
                    "metadata": dict(metadata or {}),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            record.updated_at = datetime.utcnow().isoformat()
            self._persist()
            return record

    def get(self, reference: str) -> SupportReferenceRecord | None:
        with self._lock:
            return self._records.get(reference.upper())

    def list_for_customer(self, tenant: str, customer_id: str) -> List[SupportReferenceRecord]:
        with self._lock:
            items = [r for r in self._records.values() if r.customer_id == customer_id and r.tenant == tenant]
            items.sort(key=lambda r: r.updated_at, reverse=True)
            return items

    def latest_for_session(self, tenant: str, customer_id: str, session_id: str) -> SupportReferenceRecord | None:
        with self._lock:
            matches = [r for r in self._records.values() if r.tenant == tenant and r.customer_id == customer_id and r.session_id == session_id]
            if not matches:
                return None
            matches.sort(key=lambda r: r.updated_at, reverse=True)
            return matches[0]
