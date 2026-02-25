from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("/status/{flight_number}")
async def get_flight_status(flight_number: str, request: Request):
    tools = request.app.state.orchestrator.flight_status_tools
    return await tools.get_realtime_status(flight_number)

