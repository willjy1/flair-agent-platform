from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from agents.orchestrator import OrchestratorAgent
from api.customer_reference_store import CustomerReferenceStore
from api.tenant_pool import TenantOrchestratorPool
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.rate_limiting import RateLimitMiddleware
from api.routers import admin, analytics, chat, customer, flights, webhooks
from channels.web_chat import WebChatConnectionManager
from pathlib import Path


def create_app() -> FastAPI:
    app = FastAPI(title="Flair Agent Platform", version="0.1.0")
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.state.tenant_pool = TenantOrchestratorPool()
    app.state.orchestrator = app.state.tenant_pool.get("flair")
    app.state.web_chat_manager = WebChatConnectionManager()
    app.state.customer_reference_store = CustomerReferenceStore()

    api_prefix = "/api/v1"
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(customer.router, prefix=api_prefix)
    app.include_router(flights.router, prefix=api_prefix)
    app.include_router(webhooks.router, prefix=api_prefix)
    app.include_router(admin.router, prefix=api_prefix)
    app.include_router(analytics.router, prefix=api_prefix)

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    async def health():
        orch: OrchestratorAgent = app.state.orchestrator
        return {
            "ok": True,
            "service": "flair-agent-platform",
            "llm_provider": orch.llm.provider,
            "llm_model": orch.llm.model,
            "llm_runtime_available": orch.llm.available(),
            "stt_available": orch.llm.stt_available(),
            "tts_available": orch.llm.tts_available(),
            "default_tenant": getattr(orch, "tenant_slug", "flair"),
        }

    @app.get("/")
    async def root():
        return RedirectResponse(url="/support", status_code=307)

    @app.get("/support")
    async def support_redirect_page():
        # Mirror customer-facing route on a short URL.
        html_path = Path(__file__).resolve().parents[1] / "web" / "customer_support.html"
        if html_path.exists():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return {"detail": "customer support page unavailable"}

    @app.get("/support/{tenant_slug}")
    async def support_tenant_alias(tenant_slug: str):
        # Generic route for white-label deployments; UI remains Flair-branded by default.
        html_path = Path(__file__).resolve().parents[1] / "web" / "customer_support.html"
        if html_path.exists():
            from fastapi.responses import HTMLResponse
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return {"detail": f"support page unavailable for {tenant_slug}"}

    return app


app = create_app()
