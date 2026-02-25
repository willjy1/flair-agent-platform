from __future__ import annotations

from agents.base import BaseAgent
from memory.session_memory import SessionMemoryStore
from models.schemas import AgentMessage, AgentResponse, ConversationState, ToolCallRecord
from tools.crm_tools import CRMTools


class EscalationAgent(BaseAgent):
    def __init__(self, crm_tools: CRMTools, session_memory: SessionMemoryStore) -> None:
        super().__init__(name="escalation_agent")
        self.crm_tools = crm_tools
        self.session_memory = session_memory

    async def process(self, message: AgentMessage) -> AgentResponse:
        window = await self.session_memory.get_context_window(
            channel=message.inbound.channel.value,
            customer_id=message.inbound.customer_id,
            session_id=message.inbound.session_id,
        )
        history = window.get("history", [])
        last_turns = history[-6:] if isinstance(history, list) else []
        summary = " | ".join(f"{h.get('role')}: {h.get('content')}" for h in last_turns)
        case = await self.crm_tools.create_case(
            customer_id=message.inbound.customer_id,
            subject="Human escalation requested",
            summary=summary[:1000] or message.inbound.content[:500],
            metadata={"session_id": message.inbound.session_id, "channel": message.inbound.channel.value},
        )
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.ESCALATED,
            response_text=(
                "I can connect you with a human support agent and share the conversation details so you do not need to repeat everything. "
                "Flair's published call center number is 1-403-709-0808. Wait times may vary."
            ),
            agent=self.name,
            escalate=True,
            tool_calls=[ToolCallRecord(tool_name="create_case", args={"subject": "Human escalation requested"}, result_summary=case["case_id"])],
            metadata={"crm_case_id": case["case_id"]},
        )
