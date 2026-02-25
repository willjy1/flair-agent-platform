from __future__ import annotations

import re
from typing import Dict

from agents.base import BaseAgent
from agents.llm_runtime import LLMRuntime
from models.schemas import AgentMessage, AgentResponse, ConversationState, IntentType, TriageResult


class TriageAgent(BaseAgent):
    def __init__(self, llm: LLMRuntime | None = None) -> None:
        super().__init__(name="triage_agent")
        self.llm = llm or LLMRuntime()

    async def classify(self, message: AgentMessage) -> TriageResult:
        text = message.inbound.content
        tenant_slug = str(message.inbound.metadata.get("tenant", "") or "").lower()
        language = self._detect_language(text, message.inbound.metadata)
        llm_result = await self.llm.classify_intent(
            text=text,
            intents=[i.value for i in IntentType],
            context={"language": language, "channel": message.inbound.channel.value},
        )
        intent_value = str(llm_result.get("intent") or IntentType.GENERAL_INQUIRY.value)
        try:
            intent = IntentType(intent_value)
        except ValueError:
            intent = IntentType.GENERAL_INQUIRY
        entities = dict(llm_result.get("entities") or {})
        entities.update(self._extract_entities_fallback(text))
        urgency = self._score_urgency(text, intent=intent, entities=entities, metadata=message.inbound.metadata)
        # Keep escalation deterministic and conservative. LLM outputs can over-trigger escalation
        # for generic billing/refund prompts (e.g., "charge issue"), which harms UX.
        escalate = self._should_escalate(text, urgency)
        intent = self._post_process_intent(text, intent)
        intent = self._post_process_intent_for_tenant(text, intent, tenant_slug)
        # Keep routing deterministic and aligned with the final intent. This avoids LLM-suggested
        # agent mismatches (e.g., refund/charge questions incorrectly jumping to escalation).
        suggested_agent = self._suggested_agent(intent)
        return TriageResult(
            intent=intent,
            urgency_score=urgency,
            entities=entities,
            suggested_agent=suggested_agent,
            escalate_immediately=escalate,
            language=language,
            reasoning=str(llm_result.get("reasoning") or f"triaged as {intent.value}"),
        )

    async def process(self, message: AgentMessage) -> AgentResponse:
        triage = await self.classify(message)
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.TRIAGING,
            response_text=f"Classified as {triage.intent.value}",
            intent=triage.intent,
            agent=self.name,
            language=triage.language,
            metadata={"triage": triage.model_dump()},
        )

    def _detect_language(self, text: str, metadata: Dict[str, object]) -> str:
        hint = str(metadata.get("language", "")).lower()
        if hint in {"fr", "fr-ca"}:
            return "fr"
        lower = text.lower()
        french_tokens = ["bonjour", "retard", "remboursement", "vol", "bagage", "annuler", "s'il", "mon vol"]
        if re.search(r"[éèêàçùôîï]", lower) or sum(1 for t in french_tokens if t in lower) >= 2:
            return "fr"
        return "en"

    def _extract_entities_fallback(self, text: str) -> Dict[str, object]:
        entities: Dict[str, object] = {}
        upper = text.upper()
        for pnr in re.finditer(r"\b([A-Z0-9]{6})\b", upper):
            value = pnr.group(1)
            if any(ch.isdigit() for ch in value) and not re.fullmatch(r"F8\d{4,5}", value):
                entities["booking_reference"] = value
                break
        flight = re.search(r"\b(F8\d{3,4})\b", upper)
        if flight:
            entities["flight_number"] = flight.group(1)
        route = re.search(r"\b([A-Z]{3})\s*[-/]\s*([A-Z]{3})\b", upper)
        if route:
            entities["route"] = f"{route.group(1)}-{route.group(2)}"
        if "today" in text.lower():
            entities.setdefault("date_hint", "today")
        if "tomorrow" in text.lower():
            entities.setdefault("date_hint", "tomorrow")
        return entities

    def _score_urgency(self, text: str, intent: IntentType, entities: Dict[str, object], metadata: Dict[str, object]) -> int:
        score = 4
        if intent in {IntentType.IRROPS, IntentType.DELAY_INFO, IntentType.ACCESSIBILITY}:
            score += 2
        if intent in {IntentType.BOOKING_CHANGE, IntentType.CANCELLATION, IntentType.BAGGAGE}:
            score += 1
        if any(k in text.lower() for k in ["now", "asap", "urgent", "airport", "boarding", "gate"]):
            score += 2
        if "flight_number" in entities or "booking_reference" in entities:
            score += 1
        if metadata.get("customer_tier") in {"VIP", "ELITE"}:
            score += 1
        return max(1, min(10, score))

    def _suggested_agent(self, intent: IntentType) -> str:
        return {
            IntentType.BOOKING_CHANGE: "booking_agent",
            IntentType.CANCELLATION: "booking_agent",
            IntentType.REFUND: "refund_agent",
            IntentType.BAGGAGE: "baggage_agent",
            IntentType.DELAY_INFO: "disruption_agent",
            IntentType.COMPENSATION_CLAIM: "compensation_agent",
            IntentType.ACCESSIBILITY: "accessibility_agent",
            IntentType.COMPLAINT: "complaint_agent",
            IntentType.GENERAL_INQUIRY: "general_agent",
            IntentType.IRROPS: "disruption_agent",
        }[intent]

    def _should_escalate(self, text: str, urgency: int) -> bool:
        lower = text.lower()
        if (
            re.search(r"\b(lawyer|legal|sue)\b", lower)
            or "human agent now" in lower
            or "supervisor now" in lower
        ):
            return True
        return urgency >= 9 and "complaint" in lower

    def _post_process_intent(self, text: str, intent: IntentType) -> IntentType:
        lower = text.lower()
        if any(k in lower for k in ["missed my flight", "missed flight", "no-show"]) and intent == IntentType.GENERAL_INQUIRY:
            return IntentType.BOOKING_CHANGE
        if any(k in lower for k in ["duplicate charge", "unauthorized charge", "charged twice", "charge issue", "billing issue", "payment issue"]) and intent == IntentType.GENERAL_INQUIRY:
            return IntentType.REFUND
        return intent

    def _post_process_intent_for_tenant(self, text: str, intent: IntentType, tenant_slug: str) -> IntentType:
        lower = text.lower()
        non_airline = tenant_slug and tenant_slug not in {"", "flair", "frontier", "airline_template"}
        if not non_airline:
            return intent
        # Insurance/health/utility/telecom demos reuse the airline intent enum. Prevent false airline mappings.
        if intent == IntentType.COMPENSATION_CLAIM and any(
            k in lower for k in ["claim status", "status of my claim", "medical claim", "insurance claim", "claim denied", "prior authorization", "coverage"]
        ):
            return IntentType.GENERAL_INQUIRY
        if intent == IntentType.REFUND and any(
            k in lower for k in ["policy billing", "billing issue on my policy", "premium", "utility bill", "internet bill", "member billing", "coverage question"]
        ):
            return IntentType.GENERAL_INQUIRY
        if intent == IntentType.REFUND and ("billing issue" in lower or "payment issue" in lower) and any(
            k in lower for k in ["policy", "account", "member", "premium", "utility", "internet", "service"]
        ):
            return IntentType.GENERAL_INQUIRY
        return intent
