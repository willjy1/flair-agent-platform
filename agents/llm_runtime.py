from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import httpx

from settings import SETTINGS


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    raw: Dict[str, Any]


class LLMRuntime:
    """Swappable LLM/STT/TTS runtime with deterministic fallback for local development."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self.provider = (provider or SETTINGS.default_llm_provider or "heuristic").lower()
        self.model = model or SETTINGS.default_model or "heuristic-local"

    def available(self) -> bool:
        if self.provider == "anthropic":
            return bool(SETTINGS.anthropic_api_key)
        if self.provider in {"xai", "grok"}:
            return bool(SETTINGS.xai_api_key)
        if self.provider == "openai":
            return bool(SETTINGS.openai_api_key)
        return False

    def stt_available(self) -> bool:
        return bool(SETTINGS.openai_api_key)

    def tts_available(self) -> bool:
        return bool(SETTINGS.elevenlabs_api_key or SETTINGS.openai_api_key)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Dict[str, Any] | None = None,
        response_format: str = "text",
    ) -> LLMResult:
        context = context or {}
        if self.available():
            try:
                if self.provider == "openai":
                    return await self._generate_openai(system_prompt, user_prompt, context, response_format)
                if self.provider == "anthropic":
                    return await self._generate_anthropic(system_prompt, user_prompt, context, response_format)
                if self.provider in {"xai", "grok"}:
                    return await self._generate_xai(system_prompt, user_prompt, context, response_format)
            except Exception as exc:  # pragma: no cover - network/provider variability
                # Fall through to deterministic local fallback so the platform remains usable offline.
                context = {**context, "_remote_error": str(exc)}

        if response_format == "json":
            payload = self._heuristic_json(user_prompt, context)
            return LLMResult(
                text=json.dumps(payload, ensure_ascii=True),
                provider="heuristic",
                model="heuristic-local",
                raw={"fallback": True, "json": payload},
            )
        text = self._heuristic_text(user_prompt, context)
        return LLMResult(
            text=text,
            provider="heuristic",
            model="heuristic-local",
            raw={"fallback": True, "remote_error": context.get("_remote_error")},
        )

    async def classify_intent(
        self,
        text: str,
        intents: Iterable[str],
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        ctx = dict(context or {})
        ctx["candidate_intents"] = list(intents)
        result = await self.generate(
            system_prompt=(
                "Classify the customer service intent. Return strict JSON with keys: "
                "intent, urgency_score, entities, suggested_agent, escalate_immediately, reasoning."
            ),
            user_prompt=text,
            context=ctx,
            response_format="json",
        )
        try:
            data = json.loads(result.text)
        except json.JSONDecodeError:
            data = {}
        data.setdefault("provider", result.provider)
        data.setdefault("model", result.model)
        return data

    async def conversation_directive(self, text: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        ctx = dict(context or {})
        heuristic = self._heuristic_conversation_directive(text, ctx)
        if not self.available():
            heuristic["provider"] = "heuristic"
            heuristic["model"] = "heuristic-local"
            return heuristic
        try:
            result = await self.generate(
                system_prompt=(
                    "Interpret the customer's turn in context for an airline support agent. "
                    "Return strict JSON with keys: continue_existing_request (bool), followup_kind (string), "
                    "intent_override (string|null), ask_one_question_only (bool), avoid_link_dump (bool), "
                    "customer_goal (string), confidence (0-1). "
                    "If the customer is answering a prior question (yes/no/option number/short response), prefer continuing the current request."
                ),
                user_prompt=text,
                context=ctx,
                response_format="json",
            )
            data = json.loads(result.text)
            if not isinstance(data, dict):
                raise ValueError("directive_not_dict")
            normalized = {
                "continue_existing_request": bool(data.get("continue_existing_request", heuristic["continue_existing_request"])),
                "followup_kind": str(data.get("followup_kind") or heuristic["followup_kind"]),
                "intent_override": data.get("intent_override"),
                "ask_one_question_only": bool(data.get("ask_one_question_only", heuristic["ask_one_question_only"])),
                "avoid_link_dump": bool(data.get("avoid_link_dump", heuristic["avoid_link_dump"])),
                "customer_goal": str(data.get("customer_goal") or heuristic["customer_goal"]),
                "confidence": float(data.get("confidence", heuristic["confidence"])),
                "provider": result.provider,
                "model": result.model,
            }
            return normalized
        except Exception:
            heuristic["provider"] = "heuristic"
            heuristic["model"] = "heuristic-local"
            return heuristic

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm", language: str = "en") -> Dict[str, Any]:
        if not audio_bytes:
            return {"ok": False, "error": "empty_audio", "provider": "none"}
        if SETTINGS.openai_api_key:
            models = [SETTINGS.openai_stt_model, "gpt-4o-mini-transcribe", "whisper-1"]
            tried: List[str] = []
            for model in models:
                if not model or model in tried:
                    continue
                tried.append(model)
                try:
                    text = await self._transcribe_openai(audio_bytes=audio_bytes, mime_type=mime_type, model=model, language=language)
                    if text:
                        return {"ok": True, "text": text, "provider": "openai", "model": model}
                except Exception as exc:  # pragma: no cover - network/provider variability
                    last_err = str(exc)
            return {"ok": False, "error": last_err if "last_err" in locals() else "openai_stt_failed", "provider": "openai"}
        return {"ok": False, "error": "stt_not_configured", "provider": "none"}

    async def synthesize_speech(self, text: str, voice_mode: str = "support") -> Dict[str, Any]:
        clean = (text or "").strip()
        if not clean:
            return {"ok": False, "error": "empty_text"}
        if SETTINGS.elevenlabs_api_key and SETTINGS.elevenlabs_voice_id:
            try:
                audio, mime = await self._tts_elevenlabs(clean, voice_mode=voice_mode)
                return {
                    "ok": True,
                    "provider": "elevenlabs",
                    "mime_type": mime,
                    "audio_bytes_b64": base64.b64encode(audio).decode("ascii"),
                }
            except Exception as exc:  # pragma: no cover - network/provider variability
                err = str(exc)
        else:
            err = None
        if SETTINGS.openai_api_key:
            try:
                audio, mime = await self._tts_openai(clean, voice_mode=voice_mode)
                return {
                    "ok": True,
                    "provider": "openai",
                    "mime_type": mime,
                    "audio_bytes_b64": base64.b64encode(audio).decode("ascii"),
                }
            except Exception as exc:  # pragma: no cover - network/provider variability
                err = str(exc)
        return {"ok": False, "error": err or "tts_not_configured"}

    async def _generate_openai(self, system_prompt: str, user_prompt: str, context: Dict[str, Any], response_format: str) -> LLMResult:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._compose_user_content(user_prompt, context, response_format)},
            ],
            "temperature": 0.2,
        }
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=SETTINGS.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{SETTINGS.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {SETTINGS.openai_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        text = self._extract_chat_completion_text(data)
        return LLMResult(text=text, provider="openai", model=self.model, raw=data)

    async def _generate_xai(self, system_prompt: str, user_prompt: str, context: Dict[str, Any], response_format: str) -> LLMResult:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._compose_user_content(user_prompt, context, response_format)},
            ],
            "temperature": 0.2,
        }
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=SETTINGS.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{SETTINGS.xai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {SETTINGS.xai_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        text = self._extract_chat_completion_text(data)
        return LLMResult(text=text, provider="xai", model=self.model, raw=data)

    async def _generate_anthropic(self, system_prompt: str, user_prompt: str, context: Dict[str, Any], response_format: str) -> LLMResult:
        content = self._compose_user_content(user_prompt, context, response_format)
        async with httpx.AsyncClient(timeout=SETTINGS.llm_timeout_seconds) as client:
            resp = await client.post(
                f"{SETTINGS.anthropic_base_url.rstrip('/')}/messages",
                headers={
                    "x-api-key": SETTINGS.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 900,
                    "temperature": 0.2,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": content}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text_parts: List[str] = []
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        return LLMResult(text="\n".join(t for t in text_parts if t).strip(), provider="anthropic", model=self.model, raw=data)

    async def _transcribe_openai(self, audio_bytes: bytes, mime_type: str, model: str, language: str) -> str:
        filename = "input.webm"
        if "wav" in mime_type:
            filename = "input.wav"
        elif "mp4" in mime_type or "m4a" in mime_type:
            filename = "input.m4a"
        form = {
            "model": (None, model),
            "language": (None, language),
        }
        files = {"file": (filename, audio_bytes, mime_type or "application/octet-stream")}
        async with httpx.AsyncClient(timeout=max(SETTINGS.llm_timeout_seconds, 45)) as client:
            resp = await client.post(
                f"{SETTINGS.openai_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {SETTINGS.openai_api_key}"},
                files={**form, **files},
            )
            resp.raise_for_status()
            data = resp.json()
        text = str(data.get("text", "") or "").strip()
        if text:
            return text
        # Some future-compatible responses may return segments/content.
        segments = data.get("segments") or []
        if isinstance(segments, list):
            joined = " ".join(str(seg.get("text", "")).strip() for seg in segments if isinstance(seg, dict)).strip()
            return joined
        return ""

    async def _tts_openai(self, text: str, voice_mode: str = "support") -> tuple[bytes, str]:
        instructions = SETTINGS.openai_tts_instructions
        if voice_mode == "phone":
            instructions += " Keep pacing concise and phone-friendly."
        async with httpx.AsyncClient(timeout=max(SETTINGS.llm_timeout_seconds, 45)) as client:
            resp = await client.post(
                f"{SETTINGS.openai_base_url.rstrip('/')}/audio/speech",
                headers={"Authorization": f"Bearer {SETTINGS.openai_api_key}"},
                json={
                    "model": SETTINGS.openai_tts_model,
                    "voice": SETTINGS.openai_tts_voice,
                    "input": text,
                    "format": "mp3",
                    "instructions": instructions,
                },
            )
            resp.raise_for_status()
            return resp.content, "audio/mpeg"

    async def _tts_elevenlabs(self, text: str, voice_mode: str = "support") -> tuple[bytes, str]:
        url = f"{SETTINGS.elevenlabs_base_url.rstrip('/')}/text-to-speech/{SETTINGS.elevenlabs_voice_id}"
        voice_settings: Dict[str, Any] = {}
        if SETTINGS.elevenlabs_stability:
            voice_settings["stability"] = float(SETTINGS.elevenlabs_stability)
        if SETTINGS.elevenlabs_similarity_boost:
            voice_settings["similarity_boost"] = float(SETTINGS.elevenlabs_similarity_boost)
        if SETTINGS.elevenlabs_style:
            voice_settings["style"] = float(SETTINGS.elevenlabs_style)
        if SETTINGS.elevenlabs_use_speaker_boost:
            voice_settings["use_speaker_boost"] = SETTINGS.elevenlabs_use_speaker_boost.strip().lower() in {"1", "true", "yes", "on"}
        body: Dict[str, Any] = {
            "text": text,
            "model_id": SETTINGS.elevenlabs_model_id,
        }
        if voice_settings:
            body["voice_settings"] = voice_settings
        if SETTINGS.elevenlabs_speed:
            body["speed"] = float(SETTINGS.elevenlabs_speed)
        if voice_mode == "phone":
            body.setdefault("speed", 0.95)
        async with httpx.AsyncClient(timeout=max(SETTINGS.llm_timeout_seconds, 45)) as client:
            resp = await client.post(
                url,
                headers={
                    "xi-api-key": SETTINGS.elevenlabs_api_key,
                    "accept": "audio/mpeg",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            return resp.content, "audio/mpeg"

    def _compose_user_content(self, user_prompt: str, context: Dict[str, Any], response_format: str) -> str:
        if not context:
            return user_prompt
        blob = json.dumps(context, ensure_ascii=True, default=str)[:8000]
        suffix = "\nReturn valid JSON only." if response_format == "json" else ""
        return f"{user_prompt}\n\nContext JSON:\n{blob}{suffix}"

    def _extract_chat_completion_text(self, data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            out: List[str] = []
            for part in content:
                if isinstance(part, dict):
                    if "text" in part:
                        out.append(str(part.get("text", "")))
                    elif part.get("type") == "text":
                        out.append(str(part.get("text", "")))
            return "\n".join(t for t in out if t).strip()
        return str(content).strip()

    def _heuristic_json(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        lower = text.lower()
        candidate_intents: List[str] = [str(i) for i in context.get("candidate_intents", [])]
        intent = "GENERAL_INQUIRY"
        reason = "Defaulted to general inquiry."
        keyword_map = [
            ("ACCESSIBILITY", ["wheelchair", "accessible", "mobility", "special assistance"]),
            ("BAGGAGE", ["baggage", "bag", "luggage", "claim tag", "lost bag"]),
            ("REFUND", ["refund", "money back", "duplicate charge", "incorrect charge", "unauthorized charge", "charged twice"]),
            ("CANCELLATION", ["cancel my booking", "cancel booking", "cancel flight"]),
            ("BOOKING_CHANGE", ["rebook", "change flight", "modify booking", "switch flight", "missed my flight", "missed flight", "no-show"]),
            ("COMPENSATION_CLAIM", ["compensation", "appr", "claim"]),
            ("IRROPS", ["cancelled flight", "flight cancelled", "irrops", "disruption"]),
            ("DELAY_INFO", ["flight status", "delayed", "delay", "status of flight"]),
            ("COMPLAINT", ["complaint", "unacceptable", "awful", "terrible", "horrible"]),
        ]
        for mapped_intent, keys in keyword_map:
            if any(k in lower for k in keys):
                intent = mapped_intent
                reason = f"Matched keywords for {mapped_intent}."
                break
        if candidate_intents and intent not in candidate_intents:
            intent = "GENERAL_INQUIRY"
        urgency = 4
        if intent in {"IRROPS", "DELAY_INFO", "ACCESSIBILITY"}:
            urgency = 7
        if any(k in lower for k in ["urgent", "asap", "now", "airport", "boarding", "gate"]):
            urgency = min(10, urgency + 2)
        if intent == "COMPLAINT":
            urgency = min(10, urgency + 1)
        escalate = any(k in lower for k in ["lawyer", "sue", "supervisor now", "human agent now"])
        suggested_agent = {
            "BOOKING_CHANGE": "booking_agent",
            "CANCELLATION": "booking_agent",
            "REFUND": "refund_agent",
            "BAGGAGE": "baggage_agent",
            "DELAY_INFO": "disruption_agent",
            "COMPENSATION_CLAIM": "compensation_agent",
            "ACCESSIBILITY": "accessibility_agent",
            "COMPLAINT": "complaint_agent",
            "IRROPS": "disruption_agent",
            "GENERAL_INQUIRY": "general_agent",
        }.get(intent, "general_agent")
        return {
            "intent": intent,
            "urgency_score": urgency,
            "entities": self._extract_entities(text),
            "suggested_agent": suggested_agent,
            "escalate_immediately": escalate,
            "reasoning": reason,
        }

    def _heuristic_conversation_directive(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        lower = (text or "").strip().lower()
        pending_actions = [str(x) for x in (context.get("pending_actions") or []) if str(x).strip()]
        last_intent = str(context.get("last_intent") or "") or None
        pending_action_type = str(context.get("pending_action_type") or "")
        short = len(lower) <= 80
        option_match = re.search(r"\boption\s*(\d+)\b", lower)
        bare_number = lower.isdigit()
        yes_set = {"yes", "yeah", "yep", "do it", "go ahead", "confirm", "submit it"}
        no_set = {"no", "nope", "nah", "not now"}
        clarification_prefixes = [
            "what do you mean",
            "wdym",
            "what does that mean",
            "why",
            "how long",
            "what happens next",
            "can you explain",
            "explain that",
        ]
        if short and (lower in yes_set or lower in no_set or option_match or bare_number):
            return {
                "continue_existing_request": True,
                "followup_kind": "choice_reply",
                "intent_override": last_intent,
                "ask_one_question_only": True,
                "avoid_link_dump": True,
                "customer_goal": "Continue the current request",
                "confidence": 0.94 if pending_actions or pending_action_type else 0.72,
            }
        if short and any(lower.startswith(p) or lower == p for p in clarification_prefixes):
            return {
                "continue_existing_request": True,
                "followup_kind": "clarification",
                "intent_override": last_intent,
                "ask_one_question_only": True,
                "avoid_link_dump": True,
                "customer_goal": "Clarify the previous step",
                "confidence": 0.92 if last_intent else 0.55,
            }
        if lower in {"start over", "new request", "reset conversation"}:
            return {
                "continue_existing_request": False,
                "followup_kind": "reset",
                "intent_override": None,
                "ask_one_question_only": True,
                "avoid_link_dump": True,
                "customer_goal": "Start a new request",
                "confidence": 0.99,
            }
        if "voice" in str(context.get("channel", "")).lower():
            return {
                "continue_existing_request": False,
                "followup_kind": "new_turn",
                "intent_override": None,
                "ask_one_question_only": True,
                "avoid_link_dump": False,
                "customer_goal": "Resolve the request quickly by voice",
                "confidence": 0.65,
            }
        return {
            "continue_existing_request": False,
            "followup_kind": "new_turn",
            "intent_override": None,
            "ask_one_question_only": False,
            "avoid_link_dump": False,
            "customer_goal": "Handle the user's request",
            "confidence": 0.5,
        }

    def _heuristic_text(self, text: str, context: Dict[str, Any]) -> str:
        lower = text.lower().strip()

        # If a specialist response is provided, rewrite it into cleaner customer-facing wording.
        specialist_response = str(context.get("specialist_response") or "").strip()
        if specialist_response:
            intent = str(context.get("intent") or "")
            next_actions = [str(a).replace("_", " ") for a in (context.get("next_actions") or [])][:4]
            facts = []
            if context.get("entities"):
                entities = context.get("entities") or {}
                if isinstance(entities, dict):
                    if entities.get("booking_reference"):
                        facts.append(f"Booking reference: {entities['booking_reference']}")
                    if entities.get("flight_number"):
                        facts.append(f"Flight: {entities['flight_number']}")
            lead = specialist_response.replace("Ã¢â‚¬â„¢", "'").replace("Ã¢â‚¬â€œ", "-")
            if next_actions:
                lead = f"{lead} Next step options: {', '.join(next_actions)}."
            if intent == "DELAY_INFO" and "Please share your flight number" in lead:
                return "I can check that. Please share your flight number (for example F81234) or your booking reference."
            return lead

        if "what can you do" in lower:
            return (
                "I can help with flight status and disruptions, rebooking and cancellations, refund and charge guidance, "
                "baggage issues, accessibility support, and connecting you to a human agent with context preserved."
            )
        if lower in {"no", "nope", "not now"}:
            return "No problem. Tell me what you want to do next and I will keep it simple."
        hits = context.get("policy_hits") or []
        if hits:
            snippet = str(hits[0].get("text", "")).replace("Ã¢â‚¬â„¢", "'")[:220].strip()
            if snippet:
                return f"Here is the most relevant official guidance I found: {snippet}"
        if any(g in lower for g in ["hello", "hi", "hey"]):
            return "Hello. How can I help with your trip today?"
        if "missed flight" in lower or "missed my flight" in lower or "no-show" in lower:
            return (
                "I'm sorry that happened. I can help check your options. Please share your booking reference so I can look up the trip and guide the next steps. "
                "If you want to contact Flair directly, Flair's published call center number is 1-403-709-0808. Wait times may vary."
            )
        return "I can help with that. Please share your booking reference, flight number, or a bit more detail about the issue."

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        pnr_match = None
        for candidate in re.finditer(r"\b([A-Z0-9]{6})\b", text.upper()):
            value = candidate.group(1)
            if any(ch.isdigit() for ch in value) and not re.fullmatch(r"F8\d{4,5}", value):
                pnr_match = candidate
                break
        flight_match = re.search(r"\b(F8\d{3,4})\b", text.upper())
        route_match = re.search(r"\b([A-Z]{3})\s*[-/]\s*([A-Z]{3})\b", text.upper())
        date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        pax_match = re.search(r"\b(\d+)\s+(?:passengers?|people|travellers?)\b", text.lower())
        if pnr_match:
            entities["booking_reference"] = pnr_match.group(1)
        if flight_match:
            entities["flight_number"] = flight_match.group(1)
        if route_match:
            entities["route"] = f"{route_match.group(1)}-{route_match.group(2)}"
        if date_match:
            entities["travel_date"] = date_match.group(1)
        if pax_match:
            entities["passenger_count"] = int(pax_match.group(1))
        if "today" in text.lower():
            entities.setdefault("date_hint", "today")
        if "tomorrow" in text.lower():
            entities.setdefault("date_hint", "tomorrow")
        return entities



