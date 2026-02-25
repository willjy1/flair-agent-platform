from __future__ import annotations

from fastapi import HTTPException, Request


def get_role_from_request(request: Request) -> str:
    # Dev-friendly auth shim. Production implementation should validate JWT/API signatures.
    role = request.headers.get("X-Role", "CUSTOMER").upper()
    return role


def require_role(*allowed_roles: str):
    allowed = {r.upper() for r in allowed_roles}

    async def _dependency(request: Request) -> str:
        role = get_role_from_request(request)
        if allowed and role not in allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return role

    return _dependency

