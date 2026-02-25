from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from settings import SETTINGS


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int | None = None) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute or SETTINGS.rate_limit_per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = self._hits[ip]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= self.requests_per_minute:
            return JSONResponse({"detail": "rate_limited"}, status_code=429)
        bucket.append(now)
        return await call_next(request)

