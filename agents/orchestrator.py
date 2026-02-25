from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Dict, Iterable, List

from agents.accessibility_agent import AccessibilityAgent
from agents.baggage_agent import BaggageAgent
from agents.base import BaseAgent
from agents.booking_agent import BookingAgent
from agents.complaint_agent import ComplaintAgent
from agents.compensation_agent import CompensationAgent
from agents.disruption_agent import DisruptionAgent
from agents.escalation_agent import EscalationAgent
from agents.general_agent import GeneralAgent
from agents.llm_runtime import LLMRuntime
from agents.refund_agent import RefundAgent
from agents.sentiment_agent import SentimentAgent
from agents.triage_agent import TriageAgent
from memory.customer_profile import CustomerProfileRepository
from memory.session_memory import SessionMemoryStore
from memory.vector_store import PolicyVectorStore
from models.schemas import AgentMessage, AgentResponse, ConversationState, InboundMessage, IntentType, TriageResult
from tenants.registry import TenantProfile, TenantRegistry
from tools.analytics_tools import AnalyticsTools
from tools.booking_tools import MockFlairBookingAPIClient
from tools.compliance_tools import ComplianceTools
from tools.crm_tools import CRMTools
from tools.flight_status_tools import FlightStatusTools
from tools.flair_knowledge_tools import FlairKnowledgeTools
from tools.notification_tools import NotificationTools
from tools.payment_tools import PaymentTools
from tools.tenant_knowledge_tools import TenantKnowledgeTools
from tools.weather_tools import WeatherTools


class OrchestratorAgent(BaseAgent):
    def __init__(
        self,
        llm: LLMRuntime | None = None,
        session_memory: SessionMemoryStore | None = None,
        customer_profiles: CustomerProfileRepository | None = None,
        vector_store: PolicyVectorStore | None = None,
        booking_tools: MockFlairBookingAPIClient | None = None,
        flight_status_tools: FlightStatusTools | None = None,
        compliance_tools: ComplianceTools | None = None,
        payment_tools: PaymentTools | None = None,
        notification_tools: NotificationTools | None = None,
        crm_tools: CRMTools | None = None,
        analytics_tools: AnalyticsTools | None = None,
        weather_tools: WeatherTools | None = None,
        flair_knowledge_tools: TenantKnowledgeTools | None = None,
        tenant_slug: str = "flair",
        tenant_profile: TenantProfile | None = None,
    ) -> None:
        super().__init__(name="orchestrator_agent")
        self.tenant_slug = tenant_slug or "flair"
        self.tenant_profile = tenant_profile or TenantRegistry().try_load(self.tenant_slug)
        self.llm = llm or LLMRuntime()
        self.session_memory = session_memory or SessionMemoryStore()
        self.customer_profiles = customer_profiles or CustomerProfileRepository()
        self.vector_store = vector_store or PolicyVectorStore()
        self.booking_tools = booking_tools or MockFlairBookingAPIClient()
        self.flight_status_tools = flight_status_tools or FlightStatusTools()
        self.compliance_tools = compliance_tools or ComplianceTools()
        self.payment_tools = payment_tools or PaymentTools()
        self.notification_tools = notification_tools or NotificationTools()
        self.crm_tools = crm_tools or CRMTools()
        self.analytics_tools = analytics_tools or AnalyticsTools()
        self.weather_tools = weather_tools or WeatherTools()
        self.flair_knowledge_tools = flair_knowledge_tools or FlairKnowledgeTools()
        # Backward-compatible alias while moving toward tenant-agnostic naming.
        self.knowledge_tools: TenantKnowledgeTools = self.flair_knowledge_tools

        self.sentiment_agent = SentimentAgent()
        self.triage_agent = TriageAgent(llm=self.llm)
        self.specialists: Dict[str, BaseAgent] = {
            "general_agent": GeneralAgent(
                self.vector_store,
                llm=self.llm,
                tenant_slug=self.tenant_slug,
                tenant_profile=self.tenant_profile,
            ),
            "booking_agent": BookingAgent(self.booking_tools, self.notification_tools, self.customer_profiles),
            "refund_agent": RefundAgent(self.booking_tools, self.compliance_tools, self.payment_tools),
            "baggage_agent": BaggageAgent(self.crm_tools),
            "disruption_agent": DisruptionAgent(
                self.flight_status_tools,
                self.booking_tools,
                tenant_slug=self.tenant_slug,
                tenant_profile=self.tenant_profile,
            ),
            "compensation_agent": CompensationAgent(
                self.compliance_tools,
                tenant_slug=self.tenant_slug,
                tenant_profile=self.tenant_profile,
            ),
            "accessibility_agent": AccessibilityAgent(self.crm_tools),
            "complaint_agent": ComplaintAgent(self.crm_tools),
            "escalation_agent": EscalationAgent(self.crm_tools, self.session_memory),
        }
        self._seed_policy_store()

    def _seed_policy_store(self) -> None:
        seed_probe = self.tenant_profile.display_name if self.tenant_profile else "support"
        if self.vector_store.query(seed_probe, top_k=1):
            return
        docs = []
        for entry in self.knowledge_tools.snapshot.get("entries", []):
            docs.append(
                {
                    "text": str(entry.get("text", "")),
                    "policy_type": str(entry.get("topic", "support")),
                    "effective_date": str(entry.get("effective_date", self.knowledge_tools.snapshot.get("snapshot_date") or "")),
                    "section": str(entry.get("id", "")),
                    "source_url": str(entry.get("source_url", "")),
                    "source_type": str(entry.get("source_type", "")),
                }
            )
        if not docs:
            docs = [
                {"text": "APPR compensation eligibility depends on delay duration and carrier category.", "policy_type": "compliance", "effective_date": "2026-01-01", "section": "appr-delay"},
                {"text": "Card refunds can take up to 30 days depending on the original payment method.", "policy_type": "refund", "effective_date": "2026-01-01", "section": "refund-timing"},
                {"text": "Accessibility assistance requests should be documented and routed promptly.", "policy_type": "accessibility", "effective_date": "2026-01-01", "section": "assistance"},
            ]
        self.vector_store.ingest(docs)

    async def process(self, message: AgentMessage) -> AgentResponse:
        return await self.route_message(message.inbound)

    async def route_message(self, message: InboundMessage) -> AgentResponse:
        channel = message.channel.value
        if self._is_reset_request(message.content):
            await self.session_memory.delete_session(channel, message.customer_id, message.session_id)
            return AgentResponse(
                session_id=message.session_id,
                customer_id=message.customer_id,
                state=ConversationState.RESOLVED,
                response_text="I've cleared the previous conversation context. You can start a new request now.",
                agent="session_reset",
                language="en",
                metadata={"reset": True},
            )
        await self.session_memory.get_or_create(channel, message.customer_id, message.session_id)
        await self.session_memory.append_history(channel, message.customer_id, message.session_id, "user", message.content)
        await self.handle_state_transition(message.session_id, ConversationState.TRIAGING, channel=channel, customer_id=message.customer_id)

        sentiment = self.sentiment_agent.analyze(message.session_id, message.content)
        triage_input = AgentMessage(inbound=message, state=ConversationState.TRIAGING, sentiment=sentiment)
        triage = await self.triage_agent.classify(triage_input)
        await self.session_memory.set_entities(channel, message.customer_id, message.session_id, triage.entities)
        context_window = await self.session_memory.get_context_window(channel, message.customer_id, message.session_id)
        entities = dict(context_window.get("entities", {}))
        entities.update(triage.entities)
        directive = await self.llm.conversation_directive(
            message.content,
            context={
                "channel": channel,
                "last_intent": entities.get("_last_intent"),
                "last_agent": entities.get("_last_agent"),
                "pending_actions": entities.get("_last_next_actions") or [],
                "pending_action_type": entities.get("_pending_action_type"),
                "history_tail": (context_window.get("history") or [])[-4:],
                "entities": {
                    k: entities.get(k)
                    for k in ["booking_reference", "flight_number", "route", "travel_date"]
                    if entities.get(k)
                },
            },
        )
        triage = self._apply_llm_conversation_directive(triage, directive, entities)
        triage = self._apply_followup_override(message.content, triage, entities)
        clarification = self._maybe_clarification_response(message, triage, entities, context_window)
        if clarification is not None:
            clarification.metadata.setdefault("conversation_directive", directive)
            return await self._finalize_response(message, triage, clarification, sentiment)
        choice_followup = self._maybe_choice_followup_response(message, triage, entities)
        if choice_followup is not None:
            choice_followup.metadata.setdefault("conversation_directive", directive)
            return await self._finalize_response(message, triage, choice_followup, sentiment)
        agent_message = self._build_agent_message(message, triage, sentiment, entities, context_window, directive)

        if triage.escalate_immediately or bool(sentiment.get("escalate_immediately")):
            response = await self.specialists["escalation_agent"].process(agent_message)
            response.metadata.setdefault("conversation_directive", directive)
            return await self._finalize_response(message, triage, response, sentiment)

        await self.handle_state_transition(message.session_id, ConversationState.PROCESSING, channel=channel, customer_id=message.customer_id)
        primary = self.specialists.get(triage.suggested_agent, self.specialists["general_agent"])
        secondaries = self._secondary_agents_for(triage.intent)
        if secondaries:
            response = await self.chain_agents(primary, secondaries, agent_message)
        else:
            await self.session_memory.add_agent_chain(channel, message.customer_id, message.session_id, primary.name)
            response = await primary.process(agent_message)
        response.metadata.setdefault("conversation_directive", directive)
        return await self._finalize_response(message, triage, response, sentiment)

    async def chain_agents(
        self,
        primary: BaseAgent,
        secondaries: list[BaseAgent],
        message: AgentMessage | None = None,
    ) -> AgentResponse:
        if message is None:
            raise ValueError("message is required for chain_agents in this implementation")
        return await self._chain_agents_with_message(primary, secondaries, message)

    async def _chain_agents_with_message(self, primary: BaseAgent, secondaries: list[BaseAgent], message: AgentMessage) -> AgentResponse:
        channel = message.inbound.channel.value
        responses: List[AgentResponse] = []
        await self.session_memory.add_agent_chain(channel, message.inbound.customer_id, message.inbound.session_id, primary.name)
        primary_response = await primary.process(message)
        responses.append(primary_response)

        for agent in secondaries:
            if agent.name == "compensation_agent" and not self._should_run_compensation_chain(primary_response):
                continue
            chained_context = dict(message.context)
            chained_context.update(primary_response.metadata)
            if "flight_status" in primary_response.metadata:
                status = primary_response.metadata["flight_status"]
                if isinstance(status, dict):
                    chained_context["delay_minutes"] = status.get("delay_minutes", 0)
            chained_message = message.model_copy(update={"state": primary_response.state, "context": chained_context})
            await self.session_memory.add_agent_chain(channel, message.inbound.customer_id, message.inbound.session_id, agent.name)
            responses.append(await agent.process(chained_message))

        return self._merge_chain_responses(responses)

    def _should_run_compensation_chain(self, primary_response: AgentResponse) -> bool:
        md = primary_response.metadata or {}
        delay_minutes = 0
        try:
            delay_minutes = int(md.get("delay_minutes") or 0)
        except Exception:
            delay_minutes = 0
        if delay_minutes >= 180:
            return True
        next_actions = [str(x) for x in (primary_response.next_actions or [])]
        return "compensation_check" in next_actions

    async def handle_state_transition(
        self,
        session_id: str,
        new_state: ConversationState,
        channel: str | None = None,
        customer_id: str | None = None,
    ) -> None:
        if channel is None or customer_id is None:
            ctx = await self.session_memory.get_by_session_id(session_id)
            if not ctx:
                return
            channel = ctx.channel.value if hasattr(ctx.channel, "value") else str(ctx.channel)
            customer_id = ctx.customer_id
        await self.session_memory.update_state(channel=channel, customer_id=customer_id, session_id=session_id, state=new_state)

    def _build_agent_message(
        self,
        inbound: InboundMessage,
        triage: TriageResult,
        sentiment: Dict[str, object],
        entities: Dict[str, object],
        context_window: Dict[str, object],
        directive: Dict[str, object] | None = None,
    ) -> AgentMessage:
        return AgentMessage(
            inbound=inbound,
            state=ConversationState.PROCESSING,
            extracted_entities=entities,
            language=triage.language,
            sentiment=sentiment,
            context={
                "urgency_score": triage.urgency_score,
                "triage_reasoning": triage.reasoning,
                "context_window": context_window,
                "recent_summary": context_window.get("summary", ""),
                "session_updated_at": context_window.get("updated_at"),
                "conversation_directive": dict(directive or {}),
            },
        )

    def _apply_llm_conversation_directive(
        self,
        triage: TriageResult,
        directive: Dict[str, object] | None,
        entities: Dict[str, object],
    ) -> TriageResult:
        if not isinstance(directive, dict):
            return triage
        if not bool(directive.get("continue_existing_request")):
            return triage
        last_intent_raw = directive.get("intent_override") or entities.get("_last_intent")
        if not last_intent_raw:
            return triage
        try:
            last_intent = IntentType(str(last_intent_raw))
        except ValueError:
            return triage
        # Prefer keeping the current triage if it's already specific and matches.
        if triage.intent == last_intent:
            return triage.model_copy(
                update={"reasoning": f"{triage.reasoning}; conversation directive continued current request"}
            )
        # Override generic or clearly low-information turns.
        low_info_turn = triage.intent == IntentType.GENERAL_INQUIRY or bool(directive.get("avoid_link_dump"))
        if not low_info_turn:
            return triage
        return triage.model_copy(
            update={
                "intent": last_intent,
                "suggested_agent": str(entities.get("_last_agent") or triage.suggested_agent),
                "reasoning": f"conversation directive continued prior request ({last_intent.value})",
            }
        )

    def _secondary_agents_for(self, intent: IntentType) -> list[BaseAgent]:
        if intent in {IntentType.IRROPS, IntentType.DELAY_INFO} and self._supports_appr():
            return [self.specialists["compensation_agent"]]
        return []

    def _merge_chain_responses(self, responses: Iterable[AgentResponse]) -> AgentResponse:
        items = list(responses)
        primary = items[0]
        text_parts = [primary.response_text]
        tool_calls = list(primary.tool_calls)
        next_actions = list(primary.next_actions)
        metadata = dict(primary.metadata)
        final_state = primary.state
        escalate = primary.escalate
        for response in items[1:]:
            if response.response_text:
                text_parts.append(response.response_text)
            tool_calls.extend(response.tool_calls)
            for action in response.next_actions:
                if action not in next_actions:
                    next_actions.append(action)
            metadata.update(response.metadata)
            if response.state == ConversationState.ESCALATED:
                final_state = ConversationState.ESCALATED
                escalate = True
            elif response.state == ConversationState.CONFIRMING and final_state != ConversationState.ESCALATED:
                final_state = ConversationState.CONFIRMING
        return primary.model_copy(
            update={
                "response_text": "\n\n".join(text_parts),
                "tool_calls": tool_calls,
                "next_actions": next_actions,
                "metadata": metadata,
                "state": final_state,
                "escalate": escalate,
            }
        )

    def _is_reset_request(self, text: str) -> bool:
        lower = (text or "").strip().lower()
        return lower in {
            "start over",
            "start a new request",
            "new request",
            "clear conversation",
            "reset conversation",
            "forget that",
        }

    async def _finalize_response(
        self,
        inbound: InboundMessage,
        triage: TriageResult,
        response: AgentResponse,
        sentiment: Dict[str, object],
    ) -> AgentResponse:
        channel = inbound.channel.value
        current_context_window = await self.session_memory.get_context_window(channel, inbound.customer_id, inbound.session_id)
        current_entities = dict(current_context_window.get("entities") or {})
        effort_state = self._compute_customer_effort(
            inbound=inbound,
            triage=triage,
            response=response,
            sentiment=sentiment,
            context_window=current_context_window,
        )
        response.metadata.setdefault("customer_effort", effort_state)
        self._apply_customer_effort_strategy(response, effort_state, inbound)
        if sentiment.get("deescalation_preamble"):
            response.response_text = f"{sentiment['deescalation_preamble']}{response.response_text}"
        response.intent = triage.intent
        response.language = triage.language
        response.metadata.setdefault("triage", triage.model_dump())
        response.metadata.setdefault("sentiment", sentiment)
        response.metadata.setdefault("llm", {"provider": self.llm.provider, "model": self.llm.model})
        self._attach_flair_support_context(response, triage.intent.value)
        response.metadata.setdefault(
            "grounding",
            {
                "source_backed": bool(response.metadata.get("citations") or response.metadata.get("official_next_steps")),
                "snapshot_date": self.knowledge_tools.snapshot.get("snapshot_date"),
                "tenant": self.tenant_slug,
            },
        )
        self._apply_response_presentation_prefs(response, inbound)
        response.metadata.setdefault(
            "customer_plan",
            self._build_customer_plan(
                intent_value=triage.intent.value,
                response=response,
                entities=dict(response.metadata.get("triage", {}).get("entities", {})) if isinstance(response.metadata.get("triage"), dict) else {},
            ),
        )
        response.response_text = self._sanitize_customer_text(response.response_text)
        response = await self._maybe_synthesize_customer_response(
            inbound=inbound,
            triage=triage,
            sentiment=sentiment,
            response=response,
        )
        promise_ledger = self._update_promise_ledger(
            prior_ledger=current_entities.get("_promise_ledger"),
            inbound=inbound,
            triage=triage,
            response=response,
            context_window=current_context_window,
        )
        response.metadata["promise_ledger"] = promise_ledger
        plan = response.metadata.get("customer_plan")
        if isinstance(plan, dict):
            plan["tracked_promises"] = [p for p in promise_ledger if str(p.get("status")) != "done"][:3]
            plan["customer_effort"] = effort_state
            response.metadata["customer_plan"] = plan
        session_updates = self._session_entity_updates_from_response(triage, response)
        await self.session_memory.set_entities(
            channel,
            inbound.customer_id,
            inbound.session_id,
            session_updates,
        )

        await self.handle_state_transition(inbound.session_id, response.state, channel=channel, customer_id=inbound.customer_id)
        await self.session_memory.append_history(channel, inbound.customer_id, inbound.session_id, "assistant", response.response_text)
        profile = await self.customer_profiles.get_profile(inbound.customer_id)
        valence = float(sentiment.get("valence", 0.0) or 0.0)
        # Exponential smoothing for frustration: 0 is calm, 1 is high frustration.
        frustration_signal = min(1.0, max(0.0, -valence))
        profile.historical_frustration_index = round((profile.historical_frustration_index * 0.7) + (frustration_signal * 0.3), 3)
        interactions = await self.customer_profiles.get_interactions(inbound.customer_id)
        if (
            len(interactions) >= 4
            and profile.historical_frustration_index >= 0.6
            and profile.tier == "STANDARD"
        ):
            profile.tier = "GOODWILL_PRIORITY"
            await self.analytics_tools.log_event(
                "goodwill_priority_triggered",
                {"customer_id": inbound.customer_id, "historical_frustration_index": profile.historical_frustration_index},
            )
        await self.customer_profiles.upsert_profile(profile)

        await self.customer_profiles.record_interaction(
            inbound.customer_id,
            {
                "channel": channel,
                "intent": triage.intent.value,
                "resolution": "ESCALATED" if response.escalate else response.state.value,
                "sentiment_score": valence,
                "duration_seconds": 0,
                "agent_type": response.agent,
            },
        )
        await self.analytics_tools.log_event(
            "agent_response",
            {
                "session_id": inbound.session_id,
                "customer_id": inbound.customer_id,
                "channel": channel,
                "intent": triage.intent.value,
                "agent": response.agent,
                "state": response.state.value,
                "escalate": response.escalate,
            },
        )
        response.decision_logs.append(
            self.build_decision_log(
                session_id=inbound.session_id,
                action="route_message",
                reasoning=f"intent={triage.intent.value} urgency={triage.urgency_score} agent={response.agent}",
                tool_calls=response.tool_calls,
                outcome="escalated" if response.escalate else "ok",
            )
        )
        return response

    def _apply_response_presentation_prefs(self, response: AgentResponse, inbound: InboundMessage) -> None:
        md = response.metadata if isinstance(response.metadata, dict) else {}
        directive = md.get("conversation_directive") if isinstance(md.get("conversation_directive"), dict) else {}
        if not isinstance(directive, dict):
            directive = {}
        effort = md.get("customer_effort") if isinstance(md.get("customer_effort"), dict) else {}
        if response.metadata.get("followup_choice") or bool(directive.get("avoid_link_dump")):
            response.metadata["citations"] = []
            response.metadata["official_next_steps"] = []
            sso = response.metadata.get("self_service_options")
            if isinstance(sso, list):
                response.metadata["self_service_options"] = sso[:1]
        if bool(effort.get("fast_path_active")):
            # Reduce link/choice clutter when the customer has already spent effort.
            response.metadata["citations"] = list(response.metadata.get("citations") or [])[:1]
            response.metadata["official_next_steps"] = list(response.metadata.get("official_next_steps") or [])[:1]
            sso = response.metadata.get("self_service_options")
            if isinstance(sso, list):
                response.metadata["self_service_options"] = sso[:2]
            if len(response.next_actions) > 3:
                response.next_actions = response.next_actions[:3]
        if inbound.channel.value == "voice":
            # Keep voice interactions concise and focused.
            response.metadata["voice_mode"] = True
            if len(response.next_actions) > 3:
                response.next_actions = response.next_actions[:3]

    def _attach_flair_support_context(self, response: AgentResponse, intent_value: str) -> None:
        citations = self.knowledge_tools.citations_for_intent(intent_value)
        if citations:
            response.metadata.setdefault(
                "citations",
                [
                    {
                        "title": c.get("id"),
                        "topic": c.get("topic"),
                        "source_url": c.get("source_url"),
                        "source_type": c.get("source_type"),
                        "effective_date": c.get("effective_date"),
                    }
                    for c in citations
                ],
            )
        # Add actionable official next-step channels for high-friction flows.
        if intent_value in {"COMPLAINT", "BAGGAGE", "REFUND", "IRROPS", "DELAY_INFO", "ACCESSIBILITY", "BOOKING_CHANGE", "CANCELLATION"}:
            entries = self.knowledge_tools.query("contact phone live chat support form accessibility", top_k=5)
            next_steps = []
            for entry in entries:
                next_steps.append(
                    {
                        "topic": entry.get("topic"),
                        "summary": entry.get("text"),
                        "source_url": entry.get("source_url"),
                        "source_type": entry.get("source_type"),
                    }
                )
            if next_steps:
                response.metadata.setdefault("official_next_steps", next_steps[:3])
        self_service_options = self.knowledge_tools.self_service_options_for_intent(intent_value)
        if self_service_options:
            response.metadata.setdefault("self_service_options", self_service_options)

    def platform_capabilities_matrix(self) -> Dict[str, bool]:
        supports_appr = self._supports_appr()
        return {
            "web_chat": True,
            "sms": True,
            "social": True,
            "voice": True,
            "email": True,
            "booking_changes": True,
            "refunds": True,
            "disruption_status": True,
            "appr_compensation": supports_appr,
            "baggage": True,
            "accessibility": True,
            "human_handoff": True,
            "analytics_dashboard": True,
            "audit_trail": True,
            "escalation_queue": True,
            "proactive_disruption_monitor": True,
            "sentiment_escalation": True,
            "appr_rules": supports_appr,
            "fraud_channel_guidance": True,
            "official_channel_citations": True,
            "server_side_stt": True,
            "server_side_tts": True,
            "voice_transcription_confirmation": True,
            "upload_document_analysis": True,
            "resolution_tracker": True,
            "post_interaction_summaries": True,
            "promise_ledger": True,
            "customer_effort_budgeting": True,
            "memory_freshness_confirmation": True,
            "public_guidance_contradiction_detection": True,
            "durable_local_persistence": True,
            # Not yet fully implemented / external dependencies:
            "real_flight_status_api": False,
            "real_booking_system_api": False,
            "real_crm_integration": False,
            "real_llm_provider_sdk_calls": True,
            "redis_session_memory": False,
            "postgres_persistence": False,
            "langgraph_orchestration": False,
        }

    def _build_customer_plan(self, intent_value: str, response: AgentResponse, entities: Dict[str, object]) -> Dict[str, object]:
        stage = response.state.value
        md = response.metadata if isinstance(response.metadata, dict) else {}
        domain_workflow = md.get("domain_workflow")
        if isinstance(domain_workflow, dict):
            plan = {
                "intent": str(domain_workflow.get("workflow_key") or domain_workflow.get("type") or intent_value),
                "stage": stage,
                "escalate": response.escalate,
                "what_i_can_do_now": list(domain_workflow.get("what_i_can_do_now") or []),
                "what_i_need_from_you": list(domain_workflow.get("what_i_need_from_you") or []),
                "prepared_context": list(domain_workflow.get("prepared_context") or []),
                "service_commitments": list(domain_workflow.get("service_commitments") or []),
            }
            return self._retarget_brand_in_obj(plan)
        common_commitments = [
            "I will keep context in this conversation so you do not need to repeat details.",
            "I will point you to official Flair channels or pages when self-service or escalation is better.",
        ]
        intent_specific = {
            "DELAY_INFO": {
                "what_i_can_do_now": ["Check flight status", "Explain disruption next steps", "Guide to rebooking options", "Estimate APPR compensation if delay is long enough"],
                "what_i_need_from_you": ["Flight number (e.g., F81234) or booking reference"],
            },
            "IRROPS": {
                "what_i_can_do_now": ["Check disruption status", "Guide rebooking steps", "Prepare compensation guidance", "Prepare human handoff with context"],
                "what_i_need_from_you": ["Flight number or booking reference", "What you need most right now (rebook, refund, status, human help)"],
            },
            "BOOKING_CHANGE": {
                "what_i_can_do_now": ["Check your booking", "Show rebooking/change options", "Prepare human support handoff if urgent"],
                "what_i_need_from_you": ["Booking reference (PNR)", "Any date or route change preferences"],
            },
            "CANCELLATION": {
                "what_i_can_do_now": ["Check the booking", "Explain cancellation path", "Guide refund or credit options"],
                "what_i_need_from_you": ["Booking reference (PNR)"],
            },
            "REFUND": {
                "what_i_can_do_now": ["Estimate refund amount (demo mode)", "Explain refund timelines", "Guide official refund investigation channels"],
                "what_i_need_from_you": ["Booking reference or transaction context"],
            },
            "BAGGAGE": {
                "what_i_can_do_now": ["Start baggage tracing intake", "Escalate to baggage support with context"],
                "what_i_need_from_you": ["Baggage claim number", "Booking reference (optional)"],
            },
            "ACCESSIBILITY": {
                "what_i_can_do_now": ["Document assistance request", "Guide official accessibility support channels", "Prepare human handoff with context"],
                "what_i_need_from_you": ["Type of assistance needed", "Flight details if available"],
            },
            "COMPLAINT": {
                "what_i_can_do_now": ["Document your complaint", "Prepare human escalation with context", "Share official contact and support channels"],
                "what_i_need_from_you": ["What happened", "Flight/booking details if relevant"],
            },
            "COMPENSATION_CLAIM": {
                "what_i_can_do_now": ["Estimate APPR compensation (demo mode)", "Guide claim next steps", "Prepare support handoff"],
                "what_i_need_from_you": ["Flight number", "Delay details (if known)"],
            },
            "GENERAL_INQUIRY": {
                "what_i_can_do_now": ["Answer support questions", "Point to official Flair pages and channels"],
                "what_i_need_from_you": ["A bit more detail about what you need help with"],
            },
        }.get(
            intent_value,
            {
                "what_i_can_do_now": ["Help with support questions", "Guide you to official channels"],
                "what_i_need_from_you": ["A bit more detail"],
            },
        )

        prepared_context = []
        for key, label in [("booking_reference", "Booking reference"), ("flight_number", "Flight number"), ("route", "Route"), ("travel_date", "Travel date")]:
            if entities.get(key):
                prepared_context.append({"field": key, "label": label, "value": entities.get(key)})

        plan_intent = intent_value
        if bool(md.get("missed_flight_rescue")):
            plan_intent = "MISSED_FLIGHT_RESCUE"
            intent_specific = {
                "what_i_can_do_now": [
                    "Check the booking and missed-flight context",
                    "Show rebooking options and next available flights",
                    "Prioritize urgent same-day travel paths",
                    "Prepare human support handoff with context if needed",
                ],
                "what_i_need_from_you": ["Booking reference (PNR)", "Whether you still need to travel today"],
            }
        elif str(md.get("charge_issue_type") or "") in {"unauthorized", "duplicate_or_incorrect"}:
            plan_intent = "CHARGE_ISSUE"
            intent_specific = {
                "what_i_can_do_now": [
                    "Guide the correct charge issue path (fraud vs duplicate/incorrect)",
                    "Tell you what information Flair support will need",
                    "Prepare a support handoff with your details",
                ],
                "what_i_need_from_you": ["Booking reference or transaction details", "Charge type (unauthorized, duplicate, incorrect)"],
            }
        elif str(md.get("priority_lane") or "") == "accessibility":
            common_commitments.insert(0, "I will treat this as an accessibility-priority support request.")

        plan = {
            "intent": plan_intent,
            "stage": stage,
            "escalate": response.escalate,
            "what_i_can_do_now": intent_specific["what_i_can_do_now"],
            "what_i_need_from_you": intent_specific["what_i_need_from_you"],
            "prepared_context": prepared_context,
            "service_commitments": common_commitments,
        }
        effort = md.get("customer_effort")
        if isinstance(effort, dict):
            plan["customer_effort"] = {
                "score": effort.get("score"),
                "level": effort.get("level"),
                "fast_path_active": bool(effort.get("fast_path_active")),
                "message": effort.get("customer_message"),
            }
            if bool(effort.get("fast_path_active")):
                plan["service_commitments"].append("I will use a shorter path and avoid unnecessary steps from here.")
        if isinstance(md.get("promise_ledger"), list):
            plan["tracked_promises"] = [p for p in md.get("promise_ledger", []) if str(p.get("status")) != "done"][:3]
        return self._retarget_brand_in_obj(plan)

    def _apply_followup_override(self, user_text: str, triage: TriageResult, entities: Dict[str, object]) -> TriageResult:
        lower = user_text.strip().lower()
        followup_phrases = [
            "what do you mean",
            "wdym",
            "what does that mean",
            "why",
            "why is that",
            "why would i need",
            "how long",
            "what happens next",
            "can you explain",
            "explain that",
        ]
        action_reply = (
            bool(re.search(r"\boption\s*\d+\b", lower))
            or lower.isdigit()
            or lower in {
                "yes",
                "no",
                "nope",
                "not now",
                "do it",
                "go ahead",
                "confirm",
                "submit it",
                "refund now",
                "credit instead",
            }
        )
        has_pending_actions = isinstance(entities.get("_last_next_actions"), list) and bool(entities.get("_last_next_actions"))
        is_short_followup = len(lower) <= 80 and (
            any(lower.startswith(p) or lower == p for p in followup_phrases)
            or (action_reply and has_pending_actions)
        )
        if not is_short_followup:
            return triage
        last_intent_raw = entities.get("_last_intent")
        last_agent = str(entities.get("_last_agent") or "")
        if not last_intent_raw:
            return triage
        try:
            last_intent = IntentType(str(last_intent_raw))
        except ValueError:
            return triage
        # Only override if triage currently sees this as generic.
        if triage.intent != IntentType.GENERAL_INQUIRY:
            return triage
        return triage.model_copy(
            update={
                "intent": last_intent,
                "suggested_agent": last_agent or triage.suggested_agent,
                "reasoning": f"follow-up override using previous session context ({last_intent.value})",
            }
        )

    def _maybe_choice_followup_response(
        self,
        inbound: InboundMessage,
        triage: TriageResult,
        entities: Dict[str, object],
    ) -> AgentResponse | None:
        lower = (inbound.content or "").strip().lower()
        if lower not in {"no", "nope", "not now", "nah"}:
            return None

        last_intent_raw = entities.get("_last_intent")
        pending_actions = [str(x) for x in (entities.get("_last_next_actions") or [])] if isinstance(entities.get("_last_next_actions"), list) else []
        pending_action_type = str(entities.get("_pending_action_type") or "")
        if not last_intent_raw:
            return None
        try:
            last_intent = IntentType(str(last_intent_raw))
        except ValueError:
            return None

        pnr = str(entities.get("booking_reference") or "").upper()
        flight = str(entities.get("flight_number") or "").upper()
        trip_bits = [v for v in [pnr, flight] if v]
        trip_hint = f" I still have your recent trip context ({', '.join(trip_bits)})." if trip_bits else ""

        # Refund path: the common bad behavior in screenshots.
        if last_intent == IntentType.REFUND:
            if "provide_booking_reference" in pending_actions and not pnr:
                return AgentResponse(
                    session_id=inbound.session_id,
                    customer_id=inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "No problem. I cannot check your exact refund eligibility without a booking reference, but I can still explain the general refund path, "
                        "or I can help you contact official Flair support right away if you prefer." + trip_hint
                    ),
                    intent=last_intent,
                    agent="followup_choice_layer",
                    next_actions=["continue_current_request", "human_agent_if_urgent", "switch_to_new_request"],
                    metadata={"followup_choice": True, "choice_type": "declined_booking_reference"},
                )
            if pending_action_type == "refund_decision" or {"submit_refund", "choose_travel_credit"} <= set(pending_actions):
                return AgentResponse(
                    session_id=inbound.session_id,
                    customer_id=inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "Understood. I will not submit anything yet. If you want, I can explain the difference between refund and travel credit, or keep this request open while you decide."
                        + trip_hint
                    ),
                    intent=last_intent,
                    agent="followup_choice_layer",
                    next_actions=["continue_current_request", "switch_to_new_request", "human_agent_if_urgent"],
                    metadata={"followup_choice": True, "choice_type": "declined_refund_action"},
                )

        if last_intent in {IntentType.BOOKING_CHANGE, IntentType.CANCELLATION}:
            if "provide_booking_reference" in pending_actions and not pnr:
                return AgentResponse(
                    session_id=inbound.session_id,
                    customer_id=inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "Okay. I cannot check or change the booking without the booking reference. If you want, I can explain the general change or cancellation path, or help you reach human support now."
                        + trip_hint
                    ),
                    intent=last_intent,
                    agent="followup_choice_layer",
                    next_actions=["continue_current_request", "human_agent_if_urgent", "switch_to_new_request"],
                    metadata={"followup_choice": True, "choice_type": "declined_booking_lookup"},
                )
            if pending_action_type == "rebooking_selection":
                return AgentResponse(
                    session_id=inbound.session_id,
                    customer_id=inbound.customer_id,
                    state=ConversationState.CONFIRMING,
                    response_text=(
                        "No problem. I have not changed your booking. If you want, I can keep the options available and you can choose one later, or I can help with a different request."
                        + trip_hint
                    ),
                    intent=last_intent,
                    agent="followup_choice_layer",
                    next_actions=["continue_current_request", "switch_to_new_request", "human_agent_if_urgent"],
                    metadata={"followup_choice": True, "choice_type": "declined_rebooking_option"},
                )

        if last_intent in {IntentType.DELAY_INFO, IntentType.IRROPS} and "provide_flight_number_or_booking_reference" in pending_actions:
            return AgentResponse(
                session_id=inbound.session_id,
                customer_id=inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "Understood. I cannot check live status without a flight number or booking reference. If your trip is urgent, I can connect you to human support right away." + trip_hint
                ),
                intent=last_intent,
                agent="followup_choice_layer",
                next_actions=["human_agent_if_urgent", "switch_to_new_request"],
                metadata={"followup_choice": True, "choice_type": "declined_status_lookup"},
            )

        if last_intent == IntentType.ACCESSIBILITY:
            return AgentResponse(
                session_id=inbound.session_id,
                customer_id=inbound.customer_id,
                state=ConversationState.CONFIRMING,
                response_text=(
                    "Understood. I can pause the request here. If you need urgent accessibility assistance, Flair's published accessibility line is 1-833-382-5421."
                    + trip_hint
                ),
                intent=last_intent,
                agent="followup_choice_layer",
                next_actions=["continue_current_request", "human_agent_if_urgent", "switch_to_new_request"],
                metadata={"followup_choice": True, "choice_type": "declined_accessibility_details"},
            )
        return None

    def _maybe_clarification_response(
        self,
        inbound: InboundMessage,
        triage: TriageResult,
        entities: Dict[str, object],
        context_window: Dict[str, object],
    ) -> AgentResponse | None:
        lower = inbound.content.strip().lower()
        if len(lower) > 120:
            return None
        clarification_starts = (
            "what do you mean",
            "wdym",
            "what does that mean",
            "why",
            "why is that",
            "why would i need",
            "how long",
            "what happens next",
            "can you explain",
            "explain that",
        )
        if not any(lower.startswith(p) or lower == p for p in clarification_starts):
            return None

        last_intent_raw = entities.get("_last_intent")
        if not last_intent_raw:
            return None
        try:
            last_intent = IntentType(str(last_intent_raw))
        except ValueError:
            return None

        history = context_window.get("history", [])
        last_assistant = ""
        if isinstance(history, list):
            for item in reversed(history):
                if item.get("role") == "assistant" and item.get("content"):
                    last_assistant = str(item.get("content"))
                    break
        pnr = str(entities.get("booking_reference") or "").upper()
        flight = str(entities.get("flight_number") or "").upper()

        response_text = ""
        if last_intent == IntentType.REFUND:
            response_text = (
                "I was referring to the difference between getting a refund to your original payment method and taking travel credit. "
                "A refund usually returns the eligible amount to your original payment method and may take time to process, while travel credit can be issued for future travel and may include a bonus in this demo flow."
            )
        elif last_intent in {IntentType.BOOKING_CHANGE, IntentType.CANCELLATION}:
            response_text = (
                "I need your booking reference so I can verify the booking details before showing available changes or cancellation options. "
                "That helps avoid making changes on the wrong reservation and lets me pull the correct flight and fare information."
            )
        elif last_intent in {IntentType.DELAY_INFO, IntentType.IRROPS}:
            response_text = (
                "I was referring to checking the latest flight status first, then showing the next steps based on the result. "
                "If there is a delay or cancellation, I can guide you through rebooking options and compensation information."
            )
        elif last_intent == IntentType.COMPENSATION_CLAIM:
            response_text = (
                "I was referring to APPR compensation eligibility. The estimated amount depends on the delay length and the applicable rule category. "
                "I can calculate an estimate once I have the flight and delay details."
            )
        elif last_intent == IntentType.BAGGAGE:
            response_text = (
                "I was asking for the baggage claim number because it is the fastest way to trace the bag in baggage support workflows. "
                "If the bag cannot be located automatically, I can escalate the case with the details you provide."
            )
        elif last_intent == IntentType.ACCESSIBILITY:
            response_text = (
                "I was asking for the assistance details so the correct support can be arranged, such as wheelchair or airport assistance. "
                "Sharing your flight details also helps route the request correctly and avoid delays."
            )
        elif last_intent == IntentType.COMPLAINT:
            response_text = (
                "I was referring to documenting your complaint and gathering the key details so the support team can review it without asking you to repeat everything."
            )
        else:
            response_text = (
                "I was referring to the next step needed to help with your request as quickly as possible. "
                "If you want, I can continue from the previous step with the details you already shared."
            )

        if pnr or flight:
            identifiers = ", ".join(v for v in [pnr, flight] if v)
            response_text += f" I still have your recent trip context on this conversation ({identifiers}) unless you want to start over with a different trip."
        if last_assistant:
            response_text += f" (Previous step: {last_assistant[:180].rstrip()}{'...' if len(last_assistant) > 180 else ''})"

        return AgentResponse(
            session_id=inbound.session_id,
            customer_id=inbound.customer_id,
            state=ConversationState.CONFIRMING,
            response_text=response_text,
            intent=last_intent,
            agent="clarification_layer",
            language=triage.language,
            next_actions=["continue_current_request", "switch_to_new_request"],
            metadata={"clarification": True},
        )

    def _sanitize_customer_text(self, text: str) -> str:
        clean = (text or "").strip()
        if not clean:
            return clean
        replacements = {
            "â€™": "'",
            "â€œ": '"',
            "â€\x9d": '"',
            "â€“": "-",
            "â€”": "-",
        }
        for bad, good in replacements.items():
            clean = clean.replace(bad, good)
        clean = self._retarget_brand_text(clean)
        clean = re.sub(r"\s{2,}", " ", clean).strip()
        return clean

    async def _maybe_synthesize_customer_response(
        self,
        inbound: InboundMessage,
        triage: TriageResult,
        sentiment: Dict[str, object],
        response: AgentResponse,
    ) -> AgentResponse:
        if not self.llm.available():
            return response
        if response.metadata.get("llm_rewritten"):
            return response
        # Avoid unnecessary rewriting for extremely short direct confirmations.
        if len((response.response_text or "").strip()) < 36 and not response.next_actions:
            return response

        triage_meta = response.metadata.get("triage")
        entities = {}
        if isinstance(triage_meta, dict):
            maybe_entities = triage_meta.get("entities")
            if isinstance(maybe_entities, dict):
                entities = maybe_entities

        llm_result = await self.llm.generate(
            system_prompt=(
                "You are composing the final customer-facing reply for an airline support agent. "
                "Rewrite the draft response into natural, efficient, kind wording. Answer the customer's actual turn directly first. "
                "Preserve factual details, numbers, IDs, flight and booking references, and any published phone number or official links. "
                "Do not add generic help-centre/contact-channel explanations unless the draft explicitly requires them for the next step. "
                "Do not mention internal tools, CRM, tickets, metadata, or implementation details unless the customer explicitly asks. "
                "If the customer said a short follow-up like yes/no, interpret it in the context of the draft response rather than treating it as a new topic. "
                "If this is a voice turn, keep the response short, phone-friendly, and ask at most one follow-up question. "
                "If customer effort is high, minimize questions and offer the fastest reasonable next step."
            ),
            user_prompt=inbound.content,
            context={
                "language": triage.language,
                "channel": inbound.channel.value,
                "intent": triage.intent.value,
                "urgency_score": triage.urgency_score,
                "state": response.state.value,
                "escalate": response.escalate,
                "specialist_response": response.response_text,
                "next_actions": response.next_actions,
                "entities": entities,
                "sentiment": {"emotion": sentiment.get("emotion"), "arousal": sentiment.get("arousal")},
                "conversation_directive": (response.metadata.get("conversation_directive") if isinstance(response.metadata, dict) else {}),
                "customer_effort": (response.metadata.get("customer_effort") if isinstance(response.metadata, dict) else {}),
            },
            response_format="text",
        )
        rewritten = self._sanitize_customer_text(llm_result.text)
        if not rewritten or len(rewritten) < 18:
            return response
        call_center = self._tenant_call_center_number()
        if call_center and call_center in response.response_text and call_center not in rewritten:
            rewritten = f"{rewritten} {self._tenant_brand_display()} published call center number is {call_center}. Wait times may vary."
        response.response_text = rewritten
        response.metadata["llm_rewritten"] = True
        response.metadata["llm_rewriter"] = {"provider": llm_result.provider, "model": llm_result.model}
        return response

    def _compute_customer_effort(
        self,
        *,
        inbound: InboundMessage,
        triage: TriageResult,
        response: AgentResponse,
        sentiment: Dict[str, object],
        context_window: Dict[str, object],
    ) -> Dict[str, object]:
        history = context_window.get("history") if isinstance(context_window, dict) else []
        if not isinstance(history, list):
            history = []
        user_turns = sum(1 for item in history if isinstance(item, dict) and item.get("role") == "user")
        assistant_turns = sum(1 for item in history if isinstance(item, dict) and item.get("role") == "assistant")
        entities = context_window.get("entities") if isinstance(context_window, dict) else {}
        if not isinstance(entities, dict):
            entities = {}

        score = 0
        reasons: List[str] = []

        if user_turns >= 3:
            score += 1
            reasons.append("multiple_turns")
        if user_turns >= 6:
            score += 2
            reasons.append("long_conversation")
        if response.state == ConversationState.CONFIRMING:
            score += 1
            reasons.append("waiting_on_details")
        if inbound.channel.value == "voice" and response.state == ConversationState.CONFIRMING:
            score += 1
            reasons.append("voice_detail_collection")

        try:
            valence = float(sentiment.get("valence", 0.0) or 0.0)
        except Exception:
            valence = 0.0
        if valence <= -0.35:
            score += 1
            reasons.append("negative_sentiment")
        if valence <= -0.65:
            score += 1
            reasons.append("strong_negative_sentiment")
        try:
            consecutive_negative = int(sentiment.get("consecutive_negative_turns", 0) or 0)
        except Exception:
            consecutive_negative = 0
        if consecutive_negative >= 2:
            score += 2
            reasons.append("repeated_negative_turns")

        last_intent = str(entities.get("_last_intent") or "")
        last_next_actions = entities.get("_last_next_actions")
        overlap = 0
        if isinstance(last_next_actions, list):
            overlap = len(set(str(x) for x in last_next_actions) & set(str(x) for x in (response.next_actions or [])))
        if (
            last_intent == triage.intent.value
            and response.state == ConversationState.CONFIRMING
            and overlap >= 1
            and user_turns >= 2
        ):
            score += 2
            reasons.append("repeat_step_risk")

        lower = (inbound.content or "").strip().lower()
        if len(lower) <= 12 and user_turns >= 4:
            score += 1
            reasons.append("short_followups_after_multiple_turns")

        score = max(0, min(10, score))
        if score >= 7:
            level = "high"
        elif score >= 4:
            level = "medium"
        else:
            level = "low"

        fast_path_active = level == "high" or (level == "medium" and bool(sentiment.get("deescalation_preamble")))
        customer_message = {
            "low": "Normal support path active.",
            "medium": "I will keep this efficient and avoid unnecessary steps.",
            "high": "Fast path active: I will reduce back-and-forth and prioritize the quickest safe next step.",
        }[level]
        return {
            "score": score,
            "level": level,
            "fast_path_active": fast_path_active,
            "reasons": reasons[:6],
            "user_turns": user_turns,
            "assistant_turns": assistant_turns,
            "customer_message": customer_message,
        }

    def _apply_customer_effort_strategy(
        self,
        response: AgentResponse,
        effort: Dict[str, object],
        inbound: InboundMessage,
    ) -> None:
        if not isinstance(effort, dict):
            return
        if not bool(effort.get("fast_path_active")):
            return
        if response.state in {ConversationState.CONFIRMING, ConversationState.PROCESSING}:
            if "human_agent_if_urgent" not in response.next_actions:
                response.next_actions.append("human_agent_if_urgent")
        if len(response.next_actions) > 4:
            response.next_actions = response.next_actions[:4]
        if inbound.channel.value == "voice":
            parts = re.split(r"(?<=[.!?])\s+", str(response.response_text or "").strip())
            if len(parts) > 2:
                response.response_text = " ".join(parts[:2]).strip()
        else:
            text = str(response.response_text or "").strip()
            if len(text) > 520 and response.state == ConversationState.CONFIRMING:
                parts = re.split(r"(?<=[.!?])\s+", text)
                if len(parts) > 3:
                    response.response_text = " ".join(parts[:3]).strip()
        response.metadata["effort_fast_path_applied"] = True

    def _update_promise_ledger(
        self,
        *,
        prior_ledger: object,
        inbound: InboundMessage,
        triage: TriageResult,
        response: AgentResponse,
        context_window: Dict[str, object],
    ) -> List[Dict[str, object]]:
        now_iso = datetime.utcnow().isoformat()
        ledger_map: Dict[str, Dict[str, object]] = {}
        if isinstance(prior_ledger, list):
            for item in prior_ledger:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("id") or "").strip()
                if not key:
                    continue
                ledger_map[key] = {
                    "id": key,
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "status": str(item.get("status") or "active"),
                    "updated_at": str(item.get("updated_at") or now_iso),
                }

        def upsert(item_id: str, title: str, summary: str, status: str) -> None:
            existing = ledger_map.get(item_id, {})
            ledger_map[item_id] = {
                "id": item_id,
                "title": title,
                "summary": summary,
                "status": status,
                "updated_at": now_iso,
                "created_at": str(existing.get("created_at") or now_iso),
                "due_at": existing.get("due_at"),
                "customer_reminder": existing.get("customer_reminder"),
                "auto_followup": bool(existing.get("auto_followup", False)),
            }

        brand = self._tenant_brand_display()
        upsert(
            "context_continuity",
            "No-repeat continuity",
            "I will keep your details in this conversation so you do not have to repeat them.",
            "active",
        )

        if response.state == ConversationState.CONFIRMING:
            pending_actions = [str(a).replace("_", " ") for a in (response.next_actions or [])[:3]]
            summary = "I will keep the next step ready so you can continue from where you left off."
            if pending_actions:
                summary = f"Next step is ready: {', '.join(pending_actions)}."
            upsert("next_step_ready", "Next step prepared", summary, "active")
        elif response.state == ConversationState.RESOLVED:
            if "next_step_ready" in ledger_map:
                ledger_map["next_step_ready"]["status"] = "done"
                ledger_map["next_step_ready"]["updated_at"] = now_iso

        md = response.metadata if isinstance(response.metadata, dict) else {}
        if response.escalate:
            upsert(
                "human_handoff_context",
                "Human handoff prepared",
                f"I will preserve this conversation context for {brand} support so you do not have to start over.",
                "active",
            )
        if isinstance(md.get("refund"), dict):
            refund_id = str((md.get("refund") or {}).get("refund_id") or "").strip()
            upsert(
                "refund_progress",
                "Refund request submitted",
                f"I submitted your refund request{f' ({refund_id})' if refund_id else ''} and will keep the next steps visible here.",
                "done",
            )
        if isinstance(md.get("voucher"), dict):
            amount = (md.get("voucher") or {}).get("voucher_value_cad")
            upsert(
                "travel_credit_progress",
                "Travel credit issued",
                f"I issued travel credit{f' for ${amount} CAD' if amount is not None else ''}.",
                "done",
            )
        if isinstance(md.get("booking"), dict):
            booking_status = str((md.get("booking") or {}).get("status") or "").upper()
            if booking_status == "REBOOKED":
                upsert(
                    "booking_change_progress",
                    "Rebooking completed",
                    "I updated the booking and kept the updated trip details in this conversation.",
                    "done",
                )
            elif booking_status == "CANCELLED":
                upsert(
                    "booking_change_progress",
                    "Cancellation completed",
                    "I updated the booking status and kept the next steps in this conversation.",
                    "done",
                )
        if isinstance(md.get("flight_status"), dict) and any(a in (response.next_actions or []) for a in ["confirm_rebooking_option", "rebooking_options", "compensation_check"]):
            upsert(
                "recovery_options_ready",
                "Recovery options prepared",
                "I checked the latest status and prepared recovery options in this conversation.",
                "active",
            )
        if isinstance(md.get("workflow_artifact"), dict):
            wf_title = str((md.get("workflow_artifact") or {}).get("title") or "workflow guidance")
            upsert(
                "workflow_guidance_ready",
                "Workflow guidance prepared",
                f"I prepared the next-step workflow guidance for {wf_title.lower()}.",
                "active",
            )

        # Promise Keeper: assign lightweight follow-up windows so overdue commitments can be highlighted.
        due_rules = {
            "human_handoff_context": {
                "hours": 6,
                "reminder": f"If you have not heard back yet, I can help you continue with {brand} support without restarting.",
            },
            "refund_progress": {
                "hours": 24,
                "reminder": "If your refund status has not changed, I can help you check the next step or prepare a follow-up.",
            },
            "recovery_options_ready": {
                "hours": 4,
                "reminder": "If your plans changed, I can refresh recovery options and the fastest next step.",
            },
            "next_step_ready": {
                "hours": 24,
                "reminder": "I still have your next step ready if you want to continue where you left off.",
            },
            "workflow_guidance_ready": {
                "hours": 24,
                "reminder": "I can continue this workflow without you starting over.",
            },
        }
        for item_id, item in list(ledger_map.items()):
            rule = due_rules.get(item_id)
            if not rule:
                continue
            item["auto_followup"] = True
            item["customer_reminder"] = str(rule.get("reminder") or "")
            created_at_raw = str(item.get("created_at") or now_iso)
            try:
                created_dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                created_dt = datetime.utcnow()
            due_at = created_dt + timedelta(hours=int(rule.get("hours") or 24))
            item["due_at"] = due_at.isoformat()
            if str(item.get("status")) == "active" and datetime.utcnow() > due_at:
                item["status"] = "overdue"
                item["updated_at"] = now_iso
                # Do not overwrite with a harsher tone if the item was already marked for review.
                if item.get("customer_reminder"):
                    item["summary"] = str(item["customer_reminder"])

        # If the session has been quiet for a long time, flag active promises as needing reconfirmation.
        try:
            updated_at = str(context_window.get("updated_at") or "")
            age_seconds = 0.0
            if updated_at:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age_seconds = abs((datetime.utcnow() - dt.replace(tzinfo=None)).total_seconds())
            if age_seconds > 7 * 24 * 60 * 60:
                for item in ledger_map.values():
                    if str(item.get("status")) == "active":
                        item["status"] = "review"
                        item["summary"] = "This request may be older. I will confirm details before continuing."
                        item["updated_at"] = now_iso
        except Exception:
            pass

        status_rank = {"overdue": 0, "active": 1, "review": 2, "done": 3}
        ordered = sorted(
            ledger_map.values(),
            key=lambda x: (status_rank.get(str(x.get("status")), 9), str(x.get("updated_at") or "")),
            reverse=False,
        )
        return ordered[:8]

    def _session_entity_updates_from_response(self, triage: TriageResult, response: AgentResponse) -> Dict[str, object]:
        updates: Dict[str, object] = {
            "_last_intent": triage.intent.value,
            "_last_agent": response.agent,
            "_last_state": response.state.value,
            "_last_next_actions": list(response.next_actions or []),
            "_last_response_at": datetime.utcnow().isoformat(),
        }
        md = response.metadata or {}
        if isinstance(md.get("booking"), dict):
            booking = md["booking"]
            if booking.get("pnr"):
                updates["booking_reference"] = str(booking["pnr"]).upper()
            if booking.get("flight_number"):
                updates["flight_number"] = str(booking["flight_number"]).upper()
            if booking.get("route"):
                updates["route"] = str(booking["route"]).upper()
            if booking.get("departure_date"):
                updates["travel_date"] = str(booking["departure_date"])
        if isinstance(md.get("flight_status"), dict):
            status = md["flight_status"]
            if status.get("flight_number"):
                updates["flight_number"] = str(status["flight_number"]).upper()
            updates["_last_flight_status"] = {
                "status": status.get("status"),
                "delay_minutes": status.get("delay_minutes"),
                "departure_gate": status.get("departure_gate"),
                "timestamp": status.get("timestamp"),
            }
        if "rebooking_options" in md and isinstance(md.get("rebooking_options"), list):
            updates["_pending_rebooking_options"] = md.get("rebooking_options", [])
            if md.get("rebooking_options"):
                updates["_pending_action_type"] = "rebooking_selection"
        elif response.state == ConversationState.RESOLVED and triage.intent in {IntentType.BOOKING_CHANGE, IntentType.CANCELLATION}:
            updates["_pending_rebooking_options"] = []
            updates["_pending_action_type"] = None

        if "refund_amount_cad" in md:
            updates["_pending_refund_amount_cad"] = md.get("refund_amount_cad")
            updates["_pending_action_type"] = "refund_decision"
        elif response.state == ConversationState.RESOLVED and triage.intent == IntentType.REFUND:
            updates["_pending_refund_amount_cad"] = None
            updates["_pending_action_type"] = None

        if "refund" in md and isinstance(md.get("refund"), dict):
            updates["_last_refund"] = md["refund"]
        if "voucher" in md and isinstance(md.get("voucher"), dict):
            updates["_last_voucher"] = md["voucher"]
        if isinstance(md.get("promise_ledger"), list):
            updates["_promise_ledger"] = md.get("promise_ledger", [])
        if isinstance(md.get("customer_effort"), dict):
            updates["_customer_effort"] = md.get("customer_effort", {})
        return updates

    def _tenant_brand_display(self) -> str:
        if self.tenant_profile and self.tenant_profile.display_name:
            return self.tenant_profile.display_name.replace(" Agents", "")
        return "Support"

    def _tenant_call_center_number(self) -> str | None:
        md = (self.tenant_profile.metadata if self.tenant_profile else {}) or {}
        for key in ["call_center_phone", "primary_support_phone", "support_phone"]:
            value = md.get(key)
            if value:
                return str(value)
        return None

    def _tenant_accessibility_number(self) -> str | None:
        md = (self.tenant_profile.metadata if self.tenant_profile else {}) or {}
        for key in ["accessibility_phone", "accessibility_support_phone"]:
            value = md.get(key)
            if value:
                return str(value)
        return None

    def _supports_appr(self) -> bool:
        if self.tenant_slug == "flair":
            return True
        md = (self.tenant_profile.metadata if self.tenant_profile else {}) or {}
        if bool(md.get("supports_appr")):
            return True
        if str(md.get("country_focus") or "").lower() == "canada":
            return True
        if str(getattr(self.tenant_profile, "locale", "") or "").lower().endswith("ca"):
            return True
        return False

    def _retarget_brand_text(self, text: str) -> str:
        clean = str(text or "")
        if self.tenant_slug == "flair":
            return clean
        brand = self._tenant_brand_display()
        call_center = self._tenant_call_center_number()
        accessibility_phone = self._tenant_accessibility_number()
        # Replace Flair-specific references so white-label tenants do not expose wrong brand/call numbers.
        clean = clean.replace("Flair Airlines", brand)
        clean = clean.replace("Flair's", f"{brand}'s")
        clean = clean.replace("Flair ", f"{brand} ")
        clean = clean.replace(" Flair", f" {brand}")
        if call_center:
            clean = clean.replace("1-403-709-0808", call_center)
        if accessibility_phone:
            clean = clean.replace("1-877-291-9427", accessibility_phone)
            clean = clean.replace("1-833-382-5421", accessibility_phone)
        return clean

    def _retarget_brand_in_obj(self, value):
        if self.tenant_slug == "flair":
            return value
        if isinstance(value, str):
            return self._retarget_brand_text(value)
        if isinstance(value, list):
            return [self._retarget_brand_in_obj(v) for v in value]
        if isinstance(value, dict):
            return {k: self._retarget_brand_in_obj(v) for k, v in value.items()}
        return value
