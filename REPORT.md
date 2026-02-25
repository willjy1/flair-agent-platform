# Flair Agent Platform - Customer-Facing Build Status (2026-02-25)

## What This Is

This repository now contains a working customer-facing support platform foundation for Flair Airlines:

- Unified support agent backend (chat/voice/sms/email/social capable wrappers)
- Customer-facing web support experience at `/support`
- Multi-agent orchestration (triage + specialist agents + chaining)
- Flair-specific public support knowledge/citations (official sources snapshot)
- APPR compensation estimation and support workflow logic (dev/mock mode)
- Session memory, sentiment handling, escalation, analytics, and audit logging

## What Customers Can Do Right Now (Dev/Mock Mode)

- Ask about flight status and disruptions
- Ask for rebooking help / booking changes
- Ask for cancellations and refunds
- Start baggage tracing intake
- Request accessibility support
- File complaints / request a human agent
- Continue the same conversation from web chat to phone or SMS with a support reference
- Receive official Flair channel links/guidance in responses

## Customer-Facing Experience (New)

- Route: `GET /support`
- Also root redirects to support: `GET / -> /support`
- Single modern support page (text + voice mode in one interface)
- Enter-to-send in text mode
- Browser microphone button in voice mode (with graceful error messaging)
- Voice playback in voice mode (browser speech synthesis)
- Quick actions for common high-friction support issues
- Customer-facing support plan panel (what the agent can do now / what it needs)
- Customer-facing self-service "Do it now" links based on the issue type
- Official next-step links and citations displayed in the conversation
- Channel continuation ("Continue by phone" / "Continue by SMS") with reference and summary preview
- Escalation responses can generate a support reference for later follow-up

## Core Technical Architecture Implemented

- `agents/orchestrator.py`: master router, state transitions, chaining, finalization, analytics/audit
- `agents/triage_agent.py`: intent classification, urgency scoring, entity extraction, EN/FR detection
- `agents/sentiment_agent.py`: sentiment trajectory + de-escalation + escalation triggers
- specialist agents:
  - `booking_agent.py`
  - `refund_agent.py`
  - `baggage_agent.py`
  - `disruption_agent.py`
  - `compensation_agent.py`
  - `accessibility_agent.py`
  - `complaint_agent.py`
  - `escalation_agent.py`
  - `general_agent.py`
- `memory/session_memory.py`: session state/history/entities + sliding context window
- `memory/customer_profile.py`: in-memory customer profile + interaction history
- `memory/vector_store.py`: policy retrieval store (simple term-overlap)
- `tools/*`: mock booking/CRM/payment/flight-status/compliance/analytics/etc.
- `api/main.py` + routers/middleware
- `channels/*`: web/sms/social/voice/email channel wrappers
- `tasks/disruption_monitor.py`: Celery task + proactive disruption monitor (dev/mock mode)

## Flair-Specific Improvements Added (Customer-Facing)

- Public support knowledge snapshot stored in:
  - `data/flair_public_support_snapshot_2026-02-25.json`
- Response metadata now includes:
  - official citations (`metadata.citations`)
  - official next-step guidance links (`metadata.official_next_steps`)
- Customer endpoint (`/api/v1/customer/message`) returns these in a UI-friendly format
- Flair-specific answers added for:
  - duplicate/unauthorized charges
  - official channel guidance / scam concerns
  - X (Twitter) no-longer-monitored guidance
  - mobile app check-in limitations

## Conversation Quality Improvements Implemented

- Follow-up clarification layer:
  - short follow-ups like `what do you mean`, `why`, `what happens next` now use session context
  - avoids generic reset behavior
- Missed-flight handling:
  - `missed flight` now routes to booking-change logic and responds with a practical first step
- PNR parsing fixes:
  - avoids false positives (e.g., `REFUND` treated as a booking reference)
  - correctly scans for plausible PNRs later in the message

## Customer API Endpoints (Implemented)

- `GET /support` (customer-facing page)
- `GET /api/v1/customer/capabilities`
- `POST /api/v1/customer/message`
- `POST /api/v1/customer/voice/simulate` (backend voice wrapper preview)
- `POST /api/v1/customer/continue-channel`
- `GET /api/v1/customer/reference/{reference}`
- `GET /api/v1/customer/benchmark` (internal comparison helper; not shown in UI)

## Core Platform API Endpoints (Implemented)

- `GET /health`
- `POST /api/v1/chat/message`
- `GET /api/v1/chat/history/{session_id}`
- `WS /api/v1/chat/ws/{session_id}`
- `GET /api/v1/flights/status/{flight_number}`
- webhooks:
  - `/api/v1/webhooks/twilio`
  - `/api/v1/webhooks/twitter`
  - `/api/v1/webhooks/amazon-connect`
- admin / analytics:
  - `/api/v1/admin/escalations`
  - `/api/v1/admin/broadcast`
  - `/api/v1/analytics/dashboard`
  - `/api/v1/analytics/sentiment`

## Validation Completed

- Python compile check across all `.py` files
- FastAPI smoke tests for `/health`, `/support`, `/api/v1/customer/capabilities`, `/api/v1/customer/message`
- Manual execution of tests (17 pass in this environment)
  - `pytest` package was not installed here, so test functions were executed directly via a harness

## Run Commands

```powershell
cd C:\Users\willi\flair-agent-platform
python -m uvicorn api.main:app --reload
```

Open in browser:

- `http://127.0.0.1:8000/support`

## What Is Still Missing (Important)

- Real Flair booking/CRM/flight-status integrations
- Real Redis/PostgreSQL runtime persistence (SQL schema exists)
- Real Anthropic/xAI/OpenAI SDK calls in `LLMRuntime`
- LangChain/LangGraph orchestration (current orchestrator is custom)
- Production voice stack (telephony + STT/TTS providers)
- Full frontend build pipeline for the React admin dashboard

## Multi-Tenant Reuse (Internal, Hidden From Flair Customer UX)

The core is now partially refactored for white-label reuse while keeping the visible `/support` experience Flair-only by default:

- tenant profiles (`tenants/profiles/*.json`)
- tenant registry (`tenants/registry.py`)
- tenant-aware knowledge tools (`tools/tenant_knowledge_tools.py`)
- tenant orchestrator pool (`api/tenant_pool.py`)
- hidden tenant selection support in customer API (defaults to Flair)

## Sources Used For Flair Public Support Snapshot (Research)

Official sources:

- https://www.flyflair.com/support/contact-info
- https://flyflair.zendesk.com/hc/en-us/articles/36403059952791-Official-Contact-Channels
- https://website-prd.flyflair.com/accessible-services
- https://flyflair.zendesk.com/hc/en-us/articles/36424466563223-Wheelchairs-and-Curbside-Assistance
- https://flyflair.zendesk.com/hc/en-us/articles/36432146415127-Hearing
- https://flyflair.zendesk.com/hc/en-us/articles/36458819029783-Unauthorized-Duplicate-or-Incorrect-Charges
- https://flyflair.zendesk.com/hc/en-us/articles/37096640979351-Does-Flair-Have-an-App
- https://flyflair.zendesk.com/hc/en-us/articles/36924383675927-Flair-Resell-Ticket-Resale

Third-party signal (user-generated reviews; directional only):

- https://www.trustpilot.com/review/flyflair.com
