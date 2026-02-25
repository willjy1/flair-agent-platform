from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import require_role


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
async def dashboard_metrics(request: Request, _role: str = Depends(require_role("SUPERVISOR", "ADMIN"))):
    orchestrator = request.app.state.orchestrator
    metrics = await orchestrator.analytics_tools.dashboard_metrics()
    open_cases = await orchestrator.crm_tools.list_open_cases()
    return {
        **metrics,
        "open_escalation_cases": len(open_cases),
        "llm": {"provider": orchestrator.llm.provider, "model": orchestrator.llm.model},
    }


@router.get("/sentiment")
async def sentiment_trends(request: Request, _role: str = Depends(require_role("SUPERVISOR", "ADMIN"))):
    # In-memory aggregation from interaction history.
    profiles = request.app.state.orchestrator.customer_profiles
    values = []
    for customer_id in list(profiles._interaction_history.keys()):  # dev-only in-memory repo access
        for row in await profiles.get_interactions(customer_id):
            values.append(float(row.get("sentiment_score", 0.0)))
    avg = sum(values) / len(values) if values else 0.0
    negative = sum(1 for v in values if v < -0.2)
    return {"count": len(values), "average_sentiment": round(avg, 3), "negative_interactions": negative}

