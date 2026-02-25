from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "anthropic")
    default_model: str = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    xai_api_key: str = os.getenv("XAI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_stt_model: str = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    openai_tts_model: str = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    openai_tts_voice: str = os.getenv("OPENAI_TTS_VOICE", "alloy")
    openai_tts_instructions: str = os.getenv(
        "OPENAI_TTS_INSTRUCTIONS",
        "Speak in a warm, professional, calm customer support tone.",
    )
    anthropic_base_url: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    xai_base_url: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")

    postgres_url: str = os.getenv("POSTGRES_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "")

    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    twitter_bearer_token: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_base_url: str = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model_id: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    elevenlabs_stability: str = os.getenv("ELEVENLABS_STABILITY", "")
    elevenlabs_similarity_boost: str = os.getenv("ELEVENLABS_SIMILARITY_BOOST", "")
    elevenlabs_style: str = os.getenv("ELEVENLABS_STYLE", "")
    elevenlabs_speed: str = os.getenv("ELEVENLABS_SPEED", "")
    elevenlabs_use_speaker_boost: str = os.getenv("ELEVENLABS_USE_SPEAKER_BOOST", "")

    flair_booking_api_url: str = os.getenv("FLAIR_BOOKING_API_URL", "http://localhost:9999/mock-booking")
    flair_booking_api_key: str = os.getenv("FLAIR_BOOKING_API_KEY", "dev-key")
    flair_flight_status_api_url: str = os.getenv("FLAIR_FLIGHT_STATUS_API_URL", "http://localhost:9999/mock-flight-status")

    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    appr_version: str = os.getenv("APPR_VERSION", "2024-09")
    default_currency: str = os.getenv("DEFAULT_CURRENCY", "CAD")
    default_locale: str = os.getenv("DEFAULT_LOCALE", "en-CA")

    audit_log_path: str = os.getenv("AUDIT_LOG_PATH", "./data/audit.log.jsonl")
    analytics_log_path: str = os.getenv("ANALYTICS_LOG_PATH", "./data/analytics.log.jsonl")
    session_store_path: str = os.getenv("SESSION_STORE_PATH", "./data/session_store.json")
    customer_profile_store_path: str = os.getenv("CUSTOMER_PROFILE_STORE_PATH", "./data/customer_profiles.json")
    crm_store_path: str = os.getenv("CRM_STORE_PATH", "./data/crm_cases.json")
    support_reference_store_path: str = os.getenv("SUPPORT_REFERENCE_STORE_PATH", "./data/support_references.json")
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 60)
    llm_timeout_seconds: int = _int("LLM_TIMEOUT_SECONDS", 25)

    debug: bool = _bool("DEBUG", True)


SETTINGS = Settings()
