from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Iterable, List

from compliance.audit_logger import AuditLogger
from models.schemas import AgentDecisionLog, AgentMessage, AgentResponse, ToolCallRecord


class BaseAgent(ABC):
    def __init__(self, name: str, audit_logger: AuditLogger | None = None) -> None:
        self.name = name
        self.audit_logger = audit_logger or AuditLogger()

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentResponse:
        raise NotImplementedError

    def build_decision_log(
        self,
        session_id: str,
        action: str,
        reasoning: str,
        tool_calls: Iterable[ToolCallRecord] | None = None,
        duration_ms: int = 0,
        outcome: str = "ok",
    ) -> AgentDecisionLog:
        record = AgentDecisionLog(
            session_id=session_id,
            agent=self.name,
            action=action,
            reasoning=reasoning,
            tool_calls=list(tool_calls or []),
            duration_ms=duration_ms,
            outcome=outcome,
        )
        self.audit_logger.log_decision(record)
        return record

    async def timed(self, coro):
        start = time.perf_counter()
        result = await coro
        return result, int((time.perf_counter() - start) * 1000)
