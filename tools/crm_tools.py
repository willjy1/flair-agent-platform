from __future__ import annotations

import json
import logging
import os
import time
import uuid
from threading import Lock
from typing import Dict, List

from settings import SETTINGS

logger = logging.getLogger(__name__)


class CRMTools:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or SETTINGS.crm_store_path
        self._tickets: List[dict] = []
        self._lock = Lock()
        self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            rows = payload.get("tickets", [])
            if isinstance(rows, list):
                self._tickets = rows
        except Exception:
            self._tickets = []

    def _persist(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        last_err: Exception | None = None
        for attempt in range(5):
            tmp = f"{self.path}.{uuid.uuid4().hex}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump({"tickets": self._tickets}, fh, ensure_ascii=True)
                os.replace(tmp, self.path)
                return
            except PermissionError as exc:
                last_err = exc
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
                time.sleep(0.03 * (attempt + 1))
            except Exception as exc:
                last_err = exc
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass
                break
        logger.warning("crm_store_persist_failed", extra={"path": self.path, "error": repr(last_err)})

    async def create_case(self, customer_id: str, subject: str, summary: str, metadata: Dict[str, object] | None = None) -> dict:
        with self._lock:
            case_id = f"CRM-{len(self._tickets)+1:05d}"
            case = {
                "case_id": case_id,
                "customer_id": customer_id,
                "subject": subject,
                "summary": summary,
                "metadata": metadata or {},
                "status": "OPEN",
            }
            self._tickets.append(case)
            self._persist()
            return case

    async def append_case_note(self, case_id: str, note: str) -> dict:
        with self._lock:
            for case in self._tickets:
                if case["case_id"] == case_id:
                    case.setdefault("notes", []).append(note)
                    self._persist()
                    return case
        return {"case_id": case_id, "status": "NOT_FOUND"}

    async def list_open_cases(self) -> List[dict]:
        with self._lock:
            return [c for c in self._tickets if c.get("status") == "OPEN"]
