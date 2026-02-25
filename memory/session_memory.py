from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, Optional

from models.schemas import ConversationState, SessionContext
from settings import SETTINGS


class SessionMemoryStore:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60, path: str | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.path = path or SETTINGS.session_store_path
        self._sessions: Dict[str, SessionContext] = {}
        self._touch: Dict[str, datetime] = {}
        self._summaries: Dict[str, str] = defaultdict(str)
        self._lock = Lock()
        self._load()

    def _key(self, channel: str, customer_id: str, session_id: str) -> str:
        return f"session:{channel}:{customer_id}:{session_id}"

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            return
        raw_sessions = payload.get("sessions", {})
        raw_touch = payload.get("touch", {})
        for key, raw in raw_sessions.items():
            try:
                ctx = SessionContext.model_validate(raw)
                self._sessions[str(key)] = ctx
            except Exception:
                continue
        for key, raw in raw_touch.items():
            try:
                self._touch[str(key)] = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue

    def _persist(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "sessions": {k: v.model_dump(mode="json") for k, v in self._sessions.items()},
            "touch": {k: ts.isoformat() for k, ts in self._touch.items()},
        }
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True)
        os.replace(tmp, self.path)

    def _expire_if_needed(self, key: str) -> None:
        last_touch = self._touch.get(key)
        if last_touch and datetime.utcnow() - last_touch > timedelta(seconds=self.ttl_seconds):
            self._sessions.pop(key, None)
            self._touch.pop(key, None)

    def _entity_freshness_for_context(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        raw_ts = entities.get("_entity_timestamps")
        if not isinstance(raw_ts, dict):
            return {"seconds": {}, "labels": {}}
        now = datetime.utcnow()
        seconds: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for key, raw in raw_ts.items():
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
                age = max(0, int((now - dt).total_seconds()))
                seconds[str(key)] = age
                if age < 15 * 60:
                    labels[str(key)] = "fresh"
                elif age < 2 * 60 * 60:
                    labels[str(key)] = "recent"
                elif age < 24 * 60 * 60:
                    labels[str(key)] = "stale"
                else:
                    labels[str(key)] = "old"
            except Exception:
                continue
        return {"seconds": seconds, "labels": labels}

    async def get_or_create(self, channel: str, customer_id: str, session_id: str) -> SessionContext:
        key = self._key(channel, customer_id, session_id)
        with self._lock:
            self._expire_if_needed(key)
            if key not in self._sessions:
                self._sessions[key] = SessionContext(session_id=session_id, customer_id=customer_id, channel=channel)  # type: ignore[arg-type]
            self._touch[key] = datetime.utcnow()
            self._persist()
            return self._sessions[key]

    async def update_state(self, channel: str, customer_id: str, session_id: str, state: ConversationState) -> SessionContext:
        ctx = await self.get_or_create(channel, customer_id, session_id)
        with self._lock:
            ctx.state = state
            ctx.updated_at = datetime.utcnow()
            self._touch[self._key(channel, customer_id, session_id)] = datetime.utcnow()
            self._persist()
        return ctx

    async def append_history(self, channel: str, customer_id: str, session_id: str, role: str, content: str) -> SessionContext:
        ctx = await self.get_or_create(channel, customer_id, session_id)
        with self._lock:
            ctx.history.append({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
            if len(ctx.history) > 20:
                old = ctx.history[:-20]
                ctx.history = ctx.history[-20:]
                snippet = " ".join(item["content"] for item in old[-4:] if item.get("content"))
                ctx.summary = (ctx.summary + " " + snippet).strip()[:1200]
            ctx.updated_at = datetime.utcnow()
            self._touch[self._key(channel, customer_id, session_id)] = datetime.utcnow()
            self._persist()
        return ctx

    async def set_entities(self, channel: str, customer_id: str, session_id: str, entities: Dict[str, object]) -> SessionContext:
        ctx = await self.get_or_create(channel, customer_id, session_id)
        with self._lock:
            ts_map = dict(ctx.extracted_entities.get("_entity_timestamps") or {}) if isinstance(ctx.extracted_entities.get("_entity_timestamps"), dict) else {}
            now_iso = datetime.utcnow().isoformat()
            for key, value in (entities or {}).items():
                if str(key).startswith("_"):
                    continue
                if value in (None, "", [], {}):
                    ts_map.pop(str(key), None)
                    continue
                ts_map[str(key)] = now_iso
            ctx.extracted_entities.update(entities)
            if ts_map:
                ctx.extracted_entities["_entity_timestamps"] = ts_map
            else:
                ctx.extracted_entities.pop("_entity_timestamps", None)
            ctx.updated_at = datetime.utcnow()
            self._touch[self._key(channel, customer_id, session_id)] = datetime.utcnow()
            self._persist()
        return ctx

    async def add_agent_chain(self, channel: str, customer_id: str, session_id: str, agent_name: str) -> SessionContext:
        ctx = await self.get_or_create(channel, customer_id, session_id)
        with self._lock:
            ctx.agent_chain_history.append(agent_name)
            ctx.updated_at = datetime.utcnow()
            self._touch[self._key(channel, customer_id, session_id)] = datetime.utcnow()
            self._persist()
        return ctx

    async def get_context_window(self, channel: str, customer_id: str, session_id: str) -> Dict[str, object]:
        ctx = await self.get_or_create(channel, customer_id, session_id)
        freshness = self._entity_freshness_for_context(ctx.extracted_entities)
        return {
            "summary": ctx.summary,
            "history": ctx.history,
            "entities": ctx.extracted_entities,
            "state": ctx.state.value,
            "updated_at": ctx.updated_at.isoformat(),
            "entity_freshness_seconds": freshness.get("seconds", {}),
            "entity_freshness_labels": freshness.get("labels", {}),
        }

    async def delete_session(self, channel: str, customer_id: str, session_id: str) -> None:
        key = self._key(channel, customer_id, session_id)
        with self._lock:
            self._sessions.pop(key, None)
            self._touch.pop(key, None)
            self._persist()

    async def get_by_session_id(self, session_id: str) -> Optional[SessionContext]:
        now = datetime.utcnow()
        with self._lock:
            dirty = False
            for key, ctx in list(self._sessions.items()):
                touched = self._touch.get(key, now)
                if now - touched > timedelta(seconds=self.ttl_seconds):
                    self._sessions.pop(key, None)
                    self._touch.pop(key, None)
                    dirty = True
                    continue
                if ctx.session_id == session_id:
                    if dirty:
                        self._persist()
                    return ctx
            if dirty:
                self._persist()
        return None
