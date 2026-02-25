from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse

from agents.orchestrator import OrchestratorAgent
from api.customer_reference_store import CustomerReferenceStore
from api.tenant_pool import TenantOrchestratorPool
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.rate_limiting import RateLimitMiddleware
from api.routers import admin, analytics, chat, customer, flights, webhooks
from channels.web_chat import WebChatConnectionManager
from pathlib import Path
from tenants.registry import TenantRegistry


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

    def demo_catalog_items() -> list[dict]:
        registry = TenantRegistry()
        profiles = {p.slug: p for p in registry.list_profiles() if not p.slug.endswith("_template")}
        preferred_order = [
            "flair",
            "frontier",
            "progressive",
            "geico",
            "allstate",
            "statefarm",
            "libertymutual",
            "farmers",
            "aetna",
            "humana",
            "cigna",
            "unitedhealthcare",
            "dukeenergy",
            "xfinity",
            "fedex",
            "ups",
            "dhl",
        ]
        ordered_slugs = [s for s in preferred_order if s in profiles] + sorted([s for s in profiles if s not in preferred_order])
        items: list[dict] = []
        for slug in ordered_slugs:
            profile = profiles[slug]
            md = dict(profile.metadata or {})
            items.append(
                {
                    "slug": slug,
                    "display_name": profile.display_name,
                    "vertical": profile.vertical,
                    "category": profile.category,
                    "route_path": "/support" if slug == "flair" else f"/support/{slug}",
                    "brand_name": md.get("company_name") or profile.display_name.replace(" Agents", ""),
                    "hero_title": md.get("hero_title") or "Customer support in one conversation.",
                    "hero_subtitle": md.get("hero_subtitle") or "",
                    "brand_mark": md.get("brand_mark") or slug[:2].upper(),
                    "brand_theme": dict((md.get("brand_theme") or {})),
                }
            )
        return items

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

    @app.get("/demos")
    async def demos_directory():
        html_path = Path(__file__).resolve().parents[1] / "web" / "demo_directory.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return {"detail": "demo directory unavailable"}

    @app.get("/api/v1/demos/catalog")
    async def demos_catalog():
        return {"ok": True, "demos": demo_catalog_items()}

    @app.get("/demos/links.txt")
    async def demos_links_txt(request: Request):
        base_url = str(request.base_url).rstrip("/")
        lines = []
        for item in demo_catalog_items():
            name = str(item.get("brand_name") or item.get("display_name") or item["slug"])
            path = str(item.get("route_path") or "")
            lines.append(f"{name}: {base_url}{path}")
        return PlainTextResponse("\n".join(lines) + "\n")

    return app


app = create_app()
