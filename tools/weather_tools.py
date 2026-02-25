from __future__ import annotations

from typing import Dict


class WeatherTools:
    async def disruption_risk(self, route: str, departure_iso: str) -> Dict[str, object]:
        route_factor = 0.4 if "YYZ" in route or "YVR" in route else 0.2
        risk_score = min(0.95, 0.25 + route_factor)
        risk_level = "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW"
        return {"route": route, "departure_iso": departure_iso, "risk_score": risk_score, "risk_level": risk_level}
