from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    WEB = "web"
    SMS = "sms"
    SOCIAL = "social"
    VOICE = "voice"
    EMAIL = "email"


class IntentType(str, Enum):
    BOOKING_CHANGE = "BOOKING_CHANGE"
    CANCELLATION = "CANCELLATION"
    REFUND = "REFUND"
    BAGGAGE = "BAGGAGE"
    DELAY_INFO = "DELAY_INFO"
    COMPENSATION_CLAIM = "COMPENSATION_CLAIM"
    ACCESSIBILITY = "ACCESSIBILITY"
    COMPLAINT = "COMPLAINT"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"
    IRROPS = "IRROPS"


class ConversationState(str, Enum):
    TRIAGING = "TRIAGING"
    PROCESSING = "PROCESSING"
    CONFIRMING = "CONFIRMING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class ToolCallRecord(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    success: bool = True
    duration_ms: int = 0


class AgentDecisionLog(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    agent: str
    action: str
    reasoning: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    duration_ms: int = 0
    outcome: str = "ok"


class InboundMessage(BaseModel):
    session_id: str
    customer_id: str
    channel: ChannelType
    content: str
    attachments: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=datetime.utcnow)


class AgentMessage(BaseModel):
    inbound: InboundMessage
    state: ConversationState = ConversationState.TRIAGING
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    language: str = "en"
    sentiment: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)


class TriageResult(BaseModel):
    intent: IntentType
    urgency_score: int = Field(ge=1, le=10)
    entities: Dict[str, Any] = Field(default_factory=dict)
    suggested_agent: str
    escalate_immediately: bool = False
    language: str = "en"
    reasoning: str = ""


class AgentResponse(BaseModel):
    session_id: str
    customer_id: str
    state: ConversationState
    response_text: str
    intent: Optional[IntentType] = None
    agent: str
    language: str = "en"
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    decision_logs: List[AgentDecisionLog] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    escalate: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CustomerProfile(BaseModel):
    customer_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    language_preference: str = "en"
    tier: str = "STANDARD"
    seat_preference: Optional[str] = None
    meal_preference: Optional[str] = None
    notification_channel: Optional[str] = None
    special_assistance: Optional[str] = None
    historical_frustration_index: float = 0.0


class SessionContext(BaseModel):
    session_id: str
    customer_id: str
    channel: ChannelType
    state: ConversationState = ConversationState.TRIAGING
    history: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_entities: Dict[str, Any] = Field(default_factory=dict)
    agent_chain_history: List[str] = Field(default_factory=list)
    summary: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
