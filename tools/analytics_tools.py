from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from threading import Lock
from typing import Dict, List

from settings import SETTINGS


class AnalyticsTools:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or SETTINGS.analytics_log_path
        self._lock = Lock()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    async def log_event(self, event_type: str, payload: Dict[str, object]) -> dict:
        record = {"ts": datetime.utcnow().isoformat(), "event_type": event_type, "payload": payload}
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        return record

    async def dashboard_metrics(self) -> Dict[str, object]:
        rows: List[dict] = []
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        by_type = Counter(r.get("event_type", "unknown") for r in rows)
        return {"total_events": len(rows), "events_by_type": dict(by_type.most_common())}
