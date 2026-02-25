from __future__ import annotations

from collections import defaultdict, deque
import re
from typing import Deque, Dict

from agents.base import BaseAgent
from models.schemas import AgentMessage, AgentResponse, ConversationState


class SentimentAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="sentiment_agent")
        self._trajectories: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=6))

    def analyze(self, session_id: str, text: str) -> Dict[str, object]:
        lower = text.lower()
        def has_term(term: str) -> bool:
            if " " in term:
                return term in lower
            return bool(re.search(rf"\b{re.escape(term)}\b", lower))
        negative_hits = sum(
            1
            for token in [
                "angry",
                "upset",
                "terrible",
                "awful",
                "ridiculous",
                "unacceptable",
                "frustrated",
                "sue",
                "lawyer",
            ]
            if has_term(token)
        )
        positive_hits = sum(1 for token in ["thanks", "thank you", "great", "helpful"] if has_term(token))
        valence = max(-1.0, min(1.0, (positive_hits - negative_hits) * 0.35))
        if "!" in text and negative_hits:
            valence = max(-1.0, valence - 0.2)
        arousal = "high" if negative_hits >= 2 or ("!" in text and negative_hits) else "medium" if negative_hits else "low"
        emotion = "angry" if negative_hits >= 2 else "frustrated" if negative_hits == 1 else "satisfied" if positive_hits else "neutral"

        self._trajectories[session_id].append(valence)
        recent = list(self._trajectories[session_id])
        consecutive_negative = 0
        for value in reversed(recent):
            if value < -0.2:
                consecutive_negative += 1
            else:
                break
        legal_risk = any(has_term(k) for k in ["lawyer", "legal", "court", "sue", "cbc", "media"])
        escalate = legal_risk or consecutive_negative >= 3
        preamble = ""
        if arousal == "high" and valence < -0.2:
            preamble = "I’m sorry this has been frustrating. I’ll keep this as quick and clear as possible. "
        return {
            "valence": round(valence, 3),
            "arousal": arousal,
            "emotion": emotion,
            "consecutive_negative_turns": consecutive_negative,
            "trajectory": recent,
            "escalate_immediately": escalate,
            "deescalation_preamble": preamble,
        }

    async def process(self, message: AgentMessage) -> AgentResponse:
        sentiment = self.analyze(message.inbound.session_id, message.inbound.content)
        return AgentResponse(
            session_id=message.inbound.session_id,
            customer_id=message.inbound.customer_id,
            state=ConversationState.PROCESSING,
            response_text=f"Sentiment: {sentiment['emotion']}",
            agent=self.name,
            metadata={"sentiment": sentiment},
        )
