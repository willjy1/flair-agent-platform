from __future__ import annotations

import json
import os
from threading import Lock
from typing import Dict, List

from models.schemas import CustomerProfile
from settings import SETTINGS


class CustomerProfileRepository:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or SETTINGS.customer_profile_store_path
        self._profiles: Dict[str, CustomerProfile] = {}
        self._interaction_history: Dict[str, List[dict]] = {}
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
        for customer_id, raw in dict(payload.get("profiles", {})).items():
            try:
                self._profiles[str(customer_id)] = CustomerProfile.model_validate(raw)
            except Exception:
                continue
        for customer_id, rows in dict(payload.get("interaction_history", {})).items():
            if isinstance(rows, list):
                self._interaction_history[str(customer_id)] = list(rows)

    def _persist(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "profiles": {cid: profile.model_dump(mode="json") for cid, profile in self._profiles.items()},
            "interaction_history": self._interaction_history,
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True)
        os.replace(tmp, self.path)

    async def get_profile(self, customer_id: str) -> CustomerProfile:
        with self._lock:
            if customer_id not in self._profiles:
                self._profiles[customer_id] = CustomerProfile(customer_id=customer_id)
                self._interaction_history.setdefault(customer_id, [])
                self._persist()
            return self._profiles[customer_id]

    async def upsert_profile(self, profile: CustomerProfile) -> CustomerProfile:
        with self._lock:
            self._profiles[profile.customer_id] = profile
            self._interaction_history.setdefault(profile.customer_id, [])
            self._persist()
            return profile

    async def record_interaction(self, customer_id: str, record: dict) -> None:
        with self._lock:
            self._interaction_history.setdefault(customer_id, []).append(record)
            self._persist()

    async def get_interactions(self, customer_id: str) -> List[dict]:
        with self._lock:
            return list(self._interaction_history.get(customer_id, []))

    def delete_customer(self, customer_id: str) -> None:
        with self._lock:
            self._profiles.pop(customer_id, None)
            self._interaction_history.pop(customer_id, None)
            self._persist()

    def export_customer(self, customer_id: str) -> dict:
        with self._lock:
            profile = self._profiles.get(customer_id)
            return {
                "profile": profile.model_dump(mode="json") if profile else None,
                "interactions": list(self._interaction_history.get(customer_id, [])),
            }

