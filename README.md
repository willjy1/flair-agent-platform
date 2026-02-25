# Flair Agent Platform

Agentic customer service platform for Flair Airlines support workflows.

This repository is organized around:
- `agents/`: orchestrator + specialist agents
- `tools/`: tool wrappers for booking, CRM, payments, notifications, compliance, analytics
- `memory/`: session memory, customer profile repository, policy/vector store
- `channels/`: chat, SMS, social, voice, and email handlers
- `api/`: FastAPI app, routers, middleware
- `compliance/`: APPR, GDPR, audit logging
- `frontend/`: React + Tailwind admin dashboard
- `tests/`: unit, integration, and scenario tests

## Quick start

1. Start infra:
   - `docker compose up -d`
2. Install Python dependencies (example):
   - `pip install fastapi uvicorn pydantic pytest httpx redis celery`
3. Run API:
   - `uvicorn api.main:app --reload`
4. Run tests:
   - `pytest -q`

## Notes

- The booking, CRM, payment, and flight-status integrations are implemented with mock-safe defaults for local development.
- The orchestration path is async-first and can run tool/agent chains in sequence or parallel.
