from __future__ import annotations

import json
import os
from threading import Lock
from typing import Any, Dict

from models.schemas import AgentDecisionLog
from settings import SETTINGS


class AuditLogger:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or SETTINGS.audit_log_path
        self._lock = Lock()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def log_decision(self, record: AgentDecisionLog) -> None:
        self.log_json(record.model_dump(mode="json"))

    def log_json(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
