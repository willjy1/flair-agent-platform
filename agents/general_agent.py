from __future__ import annotations

from typing import Any, Dict

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
        profile_md = dict(getattr(tenant_profile, "metadata", {}) or {}) if tenant_profile else {}
        self.tenant_name = str(profile_md.get("company_name") or (tenant_profile.display_name if tenant_profile else "Support")).replace(" Agents", "")

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
        tenant_payload = self._tenant_specific_payload(lower, message)
        if tenant_payload is None:
            llm_result = await self.llm.generate(
                system_prompt=(
                    f"You are a customer-facing {self.tenant_name} support assistant for the {self._tenant_vertical_label()} domain. "
                    "Be clear, efficient, and kind. Answer the customer's question directly first, then ask only for the minimum details needed. "
                    "Use policy_hits as your factual source. If the needed fact is not in policy_hits, say you are not certain and point to the best official next step instead of guessing."
                ),
                user_prompt=user_text,
                context={"policy_hits": hits, "language": message.language},
            )
            response_text = llm_result.text
            metadata: Dict[str, Any] = {"policy_hits": hits, "llm_provider": llm_result.provider, "llm_model": llm_result.model}
            next_actions = []
            state = ConversationState.RESOLVED
        else:
            response_text = str(tenant_payload.get("response_text") or "")
            metadata = {"policy_hits": hits, **dict(tenant_payload.get("metadata") or {}), "llm_provider": "rule_tenant_specific", "llm_model": "n/a"}
            next_actions = list(tenant_payload.get("next_actions") or [])
            state = tenant_payload.get("state") or (ConversationState.CONFIRMING if next_actions else ConversationState.RESOLVED)
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=state,
            response_text=response_text,
            agent=self.name,
            language=message.language,
            next_actions=next_actions,
            metadata=metadata,
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

    def _tenant_vertical_label(self) -> str:
        if not self.tenant_profile:
            return "customer support"
        vertical = (self.tenant_profile.vertical or "").replace("_", " ")
        category = (self.tenant_profile.category or "").replace("_", " ")
        return f"{vertical} / {category}".strip(" /")

    def _tenant_specific_payload(self, lower: str, message: AgentMessage) -> Dict[str, Any] | None:
        flair_answer = self._tenant_specific_answer(lower)
        if flair_answer is not None:
            return {"response_text": flair_answer}

        profile = self.tenant_profile
        vertical = str(getattr(profile, "vertical", "") or "").lower()
        category = str(getattr(profile, "category", "") or "").lower()
        brand = self.tenant_name
        md = dict(getattr(profile, "metadata", {}) or {})
        contact_url = str(md.get("contact_page_url") or "")

        def workflow(
            *,
            workflow_key: str,
            response_text: str,
            can_do: list[str],
            need: list[str],
            next_actions: list[str],
            state: ConversationState = ConversationState.CONFIRMING,
            prepared_context: list[dict] | None = None,
            extra_meta: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            return {
                "response_text": response_text,
                "state": state,
                "next_actions": next_actions,
                "metadata": {
                    "workflow_artifact": {
                        "title": workflow_key.replace("_", " ").title(),
                        "summary": response_text,
                        "required_details": need,
                        "next_steps": can_do,
                    },
                    "domain_workflow": {
                        "workflow_key": workflow_key,
                        "what_i_can_do_now": can_do,
                        "what_i_need_from_you": need,
                        "prepared_context": prepared_context or [],
                        "service_commitments": [
                            "I will keep context in this conversation so you do not need to repeat details.",
                            "I will point you to official support channels or portals when self-service is the fastest path.",
                        ],
                    },
                    **(extra_meta or {}),
                },
            }

        # Insurance: claims, policy billing, roadside, glass, document intake.
        if vertical == "insurance":
            if any(k in lower for k in ["claim status", "status of my claim", "where is my claim", "claim update"]):
                return workflow(
                    workflow_key="claim_status",
                    response_text=(
                        "I can help check the next steps for your claim. Please share your claim number (or policy number and date of loss). "
                        "If you have a claim email, estimate, or document, you can upload it and I can extract the key details."
                    ),
                    can_do=["Guide claim-status lookup steps", "Prepare claim follow-up summary", "Route to the right claims support channel"],
                    need=["Claim number, or policy number + date of loss", "Claim type (auto, home, etc.) if known"],
                    next_actions=["upload_supporting_documents", "share_claim_number", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "claim_status"},
                )
            if any(k in lower for k in ["denied claim", "claim denied", "appeal claim", "claim appeal"]):
                return workflow(
                    workflow_key="claim_denial_review",
                    response_text=(
                        "I can help organize a claim denial follow-up. Please share the claim number and the denial reason (if shown). "
                        "I can then help you prepare the appeal or support request path and the supporting documents checklist."
                    ),
                    can_do=["Explain the appeal / review path", "List supporting documents to gather", "Prepare a human handoff summary"],
                    need=["Claim number", "Denial reason code or denial message", "Date of denial notice (if available)"],
                    next_actions=["upload_supporting_documents", "share_claim_number", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "claim_denial"},
                )
            if any(k in lower for k in ["premium", "billing", "payment issue", "charged twice", "duplicate charge", "auto-pay", "autopay"]):
                return workflow(
                    workflow_key="policy_billing_or_payment",
                    response_text=(
                        f"I can help with a billing or payment issue for {brand}. Please share your policy number (or account number) and what happened "
                        "(for example duplicate charge, failed payment, or incorrect amount)."
                    ),
                    can_do=["Guide the billing dispute or payment support path", "Prepare a payment issue summary", "Route to the correct support channel"],
                    need=["Policy or account number", "Payment date and amount", "Short description of the issue"],
                    next_actions=["share_booking_or_transaction_details", "upload_supporting_documents", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "billing"},
                )
            if any(k in lower for k in ["roadside", "towing", "tow truck", "stranded"]):
                urgent_line = str(md.get("roadside_phone") or md.get("call_center_phone") or "the roadside or claims support number")
                return workflow(
                    workflow_key="roadside_assistance",
                    response_text=(
                        f"If this is a roadside emergency, use {brand}'s roadside or emergency support line immediately. "
                        f"If you want, I can help you organize what information they will ask for first (location, vehicle, policy, and safety status)."
                    ),
                    can_do=["Prepare the roadside call details", "Create a summary you can read to the agent", "Switch to phone support quickly"],
                    need=["Your location", "Vehicle and policy details", "Whether anyone is in immediate danger"],
                    next_actions=["continue_current_request", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": False, "domain_case_type": "roadside", "official_contact_url": contact_url, "support_phone_hint": urgent_line},
                )

        # Health plans: claims, prior auth, provider directory, coverage, ID cards.
        if vertical == "health":
            if any(k in lower for k in ["claim status", "medical claim", "claim payment", "eob", "explanation of benefits"]):
                return workflow(
                    workflow_key="health_claim_status",
                    response_text=(
                        "I can help with a health claim status follow-up. Please share the claim number if you have it. "
                        "If not, I can still help if you provide the member ID, provider name, and date of service."
                    ),
                    can_do=["Prepare a claim-status lookup request", "List the fastest member support channels", "Create a follow-up summary"],
                    need=["Claim number (best)", "Member ID", "Provider name and date of service"],
                    next_actions=["upload_supporting_documents", "provide_member_id", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "health_claim_status"},
                )
            if any(k in lower for k in ["prior auth", "prior authorization", "preauth", "pre-authorization", "pre authorization"]):
                return workflow(
                    workflow_key="prior_authorization_status",
                    response_text=(
                        "I can help with a prior authorization status or follow-up. Please share the authorization reference (if you have it), "
                        "the member ID, and the service/procedure or medication involved."
                    ),
                    can_do=["Organize the prior auth follow-up", "Prepare questions for member support or provider support", "Route to official contact channels"],
                    need=["Authorization reference (if available)", "Member ID", "Service/procedure or medication"],
                    next_actions=["provide_prior_authorization_reference", "provide_member_id", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "prior_auth"},
                )
            if any(k in lower for k in ["id card", "member card", "insurance card", "digital id"]):
                return workflow(
                    workflow_key="member_id_card",
                    response_text=(
                        f"I can help you get to the fastest path for a member ID card in {brand}. If you need care soon, I can also help you prepare the right support request "
                        "with your member details and plan information."
                    ),
                    can_do=["Point to official member portal/app ID-card path", "Prepare member support handoff", "Summarize what to request"],
                    need=["Plan/member details if you want a handoff prepared"],
                    next_actions=["continue_current_request", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": False, "domain_case_type": "id_card"},
                )
            if any(k in lower for k in ["find a doctor", "provider", "in network", "in-network", "specialist"]):
                return workflow(
                    workflow_key="provider_directory_help",
                    response_text=(
                        "I can help you prepare a provider search quickly. Tell me your plan/state and what type of care you need, and I can point you to the official provider directory path."
                    ),
                    can_do=["Organize provider search details", "Point to official provider directory", "Prepare a member support question if the directory is unclear"],
                    need=["Plan or product name", "State/ZIP", "Specialty or provider name"],
                    next_actions=["provider_directory_search", "continue_current_request"],
                    extra_meta={"trackable_workflow": False, "domain_case_type": "provider_search"},
                )
            if any(k in lower for k in ["covered", "coverage", "benefits", "copay", "copay", "deductible"]):
                return workflow(
                    workflow_key="benefits_or_coverage_question",
                    response_text=(
                        "I can help you prepare a clear coverage question for member support. I cannot guarantee coverage decisions here, but I can help gather the right details first."
                    ),
                    can_do=["Structure the coverage question", "List the details member support will need", "Route to official member support channels"],
                    need=["Plan/member details", "Service or procedure", "Provider/facility and date (if known)"],
                    next_actions=["explain_coverage_review", "provide_member_id", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "coverage_question"},
                )

        # Utilities: outages, billing, start/stop/move service.
        if vertical == "utilities":
            if any(k in lower for k in ["outage", "power is out", "no power", "electricity out", "gas outage", "water outage"]):
                return workflow(
                    workflow_key="outage_status_or_report",
                    response_text=(
                        f"I can help with outage status or reporting. Please share your service address (or account number) and whether the outage is already reported. "
                        "If there is a safety hazard (downed lines, gas smell, fire risk), contact emergency services and the utility emergency line immediately."
                    ),
                    can_do=["Guide outage status lookup", "Prepare outage report details", "Help with restoration update questions"],
                    need=["Service address or account number", "What service is affected", "Whether there is a safety hazard"],
                    next_actions=["provide_service_address", "report_outage", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "outage"},
                )
            if any(k in lower for k in ["bill", "billing", "payment arrangement", "payment plan", "late fee", "disconnect notice"]):
                return workflow(
                    workflow_key="utility_billing_support",
                    response_text=(
                        "I can help with a utility billing or payment issue. Please share your account number (or service address) and what happened, and I can prepare the fastest next step."
                    ),
                    can_do=["Organize a billing dispute or payment support request", "Prepare a payment arrangement question", "Route to official billing support channels"],
                    need=["Account number or service address", "Bill date and amount", "What looks wrong or urgent"],
                    next_actions=["provide_account_number", "share_booking_or_transaction_details", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "utility_billing"},
                )
            if any(k in lower for k in ["start service", "stop service", "move service", "moving"]):
                return workflow(
                    workflow_key="start_stop_move_service",
                    response_text=(
                        "I can help you prepare a start/stop/move service request. Share the service address and requested date, and I can help you organize the request before you submit it."
                    ),
                    can_do=["Prepare start/stop/move service details", "List what information the utility will need", "Route to official service-start pages or support"],
                    need=["Service address", "Requested service date", "Move-in / move-out details"],
                    next_actions=["provide_service_address", "continue_current_request"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "service_move"},
                )

        # Telecom / ISP
        if vertical in {"telecom", "isp"} or "isp" in category or "internet" in category:
            if any(k in lower for k in ["internet down", "wifi down", "no internet", "outage", "service outage"]):
                return workflow(
                    workflow_key="internet_outage_support",
                    response_text=(
                        "I can help with an internet outage or service interruption. Please share your service address or account number and whether the outage appears on the provider status page."
                    ),
                    can_do=["Guide outage status checks", "Prepare outage report/support request", "Organize troubleshooting details for a human agent"],
                    need=["Service address or account number", "What service is affected (internet/mobile/tv)", "When it started"],
                    next_actions=["provide_account_number", "provide_service_address", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "isp_outage"},
                )
            if any(k in lower for k in ["technician", "appointment", "install", "installation", "service visit"]):
                return workflow(
                    workflow_key="appointment_support",
                    response_text=(
                        "I can help with an installation or technician appointment issue. Please share your account or order number and the appointment date/time window."
                    ),
                    can_do=["Prepare appointment support request", "Summarize the problem for a human agent", "Guide to official scheduling/reschedule paths"],
                    need=["Account or order number", "Appointment date/time window", "What went wrong"],
                    next_actions=["provide_order_number", "provide_account_number", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "appointment"},
                )

        # Parcel / logistics
        if vertical in {"parcel", "logistics"} or "parcel" in category or "delivery" in category:
            if any(k in lower for k in ["where is my package", "where's my package", "track package", "tracking", "package status", "delivery status"]):
                return workflow(
                    workflow_key="parcel_tracking_or_delivery_status",
                    response_text=(
                        "I can help with package tracking or delivery status. Please share the tracking number. "
                        "If you do not have it, I can still help you prepare the fastest support request using the recipient address and delivery date."
                    ),
                    can_do=["Guide tracking and delivery-status checks", "Prepare a delivery issue follow-up", "Route to official support and tracking tools"],
                    need=["Tracking number (best)", "Delivery address/ZIP and delivery date (if tracking number unavailable)"],
                    next_actions=["share_tracking_number", "continue_current_request", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "parcel_tracking"},
                )
            if any(k in lower for k in ["delivered but not received", "missing package", "package missing", "lost package", "stolen package"]):
                return workflow(
                    workflow_key="missing_delivery_investigation",
                    response_text=(
                        "I can help with a missing delivery follow-up. Please share the tracking number and delivery address or ZIP. "
                        "I can also help you prepare the details for a trace or claim request."
                    ),
                    can_do=["Prepare a missing-delivery investigation request", "List the details support will ask for", "Prepare a human handoff summary"],
                    need=["Tracking number", "Delivery address/ZIP", "When it was marked delivered"],
                    next_actions=["share_tracking_number", "upload_supporting_documents", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "missing_delivery"},
                )
            if any(k in lower for k in ["damaged package", "damaged shipment", "package damaged", "claim for damage", "delivery damage"]):
                return workflow(
                    workflow_key="parcel_damage_claim",
                    response_text=(
                        "I can help organize a damaged package claim follow-up. Please share the tracking number and, if possible, upload photos of the packaging or damage."
                    ),
                    can_do=["Prepare a damage claim support request", "List evidence to gather", "Create a follow-up summary"],
                    need=["Tracking number", "Photos or description of damage", "Delivery date"],
                    next_actions=["share_tracking_number", "upload_supporting_documents", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "parcel_damage_claim"},
                )
            if any(k in lower for k in ["refund shipping", "delivery refund", "shipping charge", "wrong shipping charge"]):
                return workflow(
                    workflow_key="shipping_charge_or_refund_issue",
                    response_text=(
                        "I can help with a shipping charge or refund issue. Please share the tracking number (if available) and what charge looks wrong."
                    ),
                    can_do=["Prepare a billing/refund support request", "Organize shipment and charge details", "Route to official billing/support channels"],
                    need=["Tracking number or shipment reference", "Charge date and amount", "What looks wrong"],
                    next_actions=["share_booking_or_transaction_details", "share_tracking_number", "human_agent_if_urgent"],
                    extra_meta={"trackable_workflow": True, "domain_case_type": "parcel_billing"},
                )

        return None
