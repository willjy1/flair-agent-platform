from __future__ import annotations

from agents.base import BaseAgent
from agents.llm_runtime import LLMRuntime
from memory.vector_store import PolicyVectorStore
from models.schemas import AgentMessage, AgentResponse, ConversationState
from tenants.registry import TenantProfile


class GeneralAgent(BaseAgent):
    def __init__(
        self,
        vector_store: PolicyVectorStore,
        llm: LLMRuntime,
        tenant_slug: str = "flair",
        tenant_profile: TenantProfile | None = None,
    ) -> None:
        super().__init__(name="general_agent")
        self.vector_store = vector_store
        self.llm = llm
        self.tenant_slug = (tenant_slug or "flair").lower()
        self.tenant_profile = tenant_profile
        self.tenant_name = (tenant_profile.display_name if tenant_profile else "Support").replace(" Agents", "")

    async def process(self, message: AgentMessage) -> AgentResponse:
        user_text = message.inbound.content
        lower = user_text.lower()
        hits = self.vector_store.query(user_text, top_k=3)
        if lower.strip() in {"no", "nope", "not now"}:
            return AgentResponse(
                session_id=message.inbound.session_id,
                customer_id=message.inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text="No problem. Tell me what you want to do next and I will keep it simple.",
                agent=self.name,
                language=message.language,
                next_actions=["continue_current_request", "switch_to_new_request", "human_agent_if_urgent"],
                metadata={"policy_hits": hits, "llm_provider": "rule_general", "llm_model": "n/a"},
            )
        response_text = self._tenant_specific_answer(lower)
        if response_text is None:
            llm_result = await self.llm.generate(
                system_prompt=(
                    f"You are a customer-facing {self.tenant_name} support assistant. "
                    "Be clear, efficient, and kind. Answer the customer's question directly first, then ask only for the minimum details needed. "
                    "Use policy_hits as your factual source. If the needed fact is not in policy_hits, say you are not certain and point to the best official next step instead of guessing."
                ),
                user_prompt=user_text,
                context={"policy_hits": hits, "language": message.language},
            )
            response_text = llm_result.text
            llm_meta = {"llm_provider": llm_result.provider, "llm_model": llm_result.model}
        else:
            llm_meta = {"llm_provider": "rule_flair_specific", "llm_model": "n/a"}
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.RESOLVED,
            response_text=response_text,
            agent=self.name,
            language=message.language,
            metadata={"policy_hits": hits, **llm_meta},
        )

    def _flair_specific_answer(self, lower: str) -> str | None:
        if any(k in lower for k in ["unauthorized charge", "duplicate charge", "charged twice", "incorrect charge"]):
            return (
                "If you suspect an unauthorized charge, contact your bank or card issuer immediately first. "
                "For duplicate or incorrect charges, I can guide you to Flair's official support and refund investigation channels."
            )
        if "twitter" in lower or " monitor x" in lower or lower.endswith(" x") or lower.endswith(" x?") or lower.strip() == "x":
            return (
                "Flair's official contact guidance indicates that Flair no longer monitors X (Twitter). "
                "I can point you to the current official channels such as phone support, web forms, live chat, and the Help Centre."
            )
        if "app" in lower and any(k in lower for k in ["check in", "check-in", "mobile"]):
            return (
                "Flair's Help Centre guidance says the app supports booking and flight status, but direct in-app check-in is not currently supported in the referenced article. "
                "I can guide you to the current official check-in path."
            )
        if any(k in lower for k in ["official contact", "official channels", "is this official", "scam", "fraud contact"]):
            return (
                "Flair publishes official contact channel guidance in its Help Centre and advises customers to use official channels to avoid scams. "
                "I can show the official contact page and relevant Help Centre links for your issue."
            )
        return None

    def _tenant_specific_answer(self, lower: str) -> str | None:
        if self.tenant_slug != "flair":
            return None
        return self._flair_specific_answer(lower)
