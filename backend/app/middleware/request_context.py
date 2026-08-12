"""Request-id + unhandled exception logging middleware."""

from __future__ import annotations

import logging
import traceback
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import is_production

logger = logging.getLogger("vagent.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception(
                "unhandled_api_error request_id=%s method=%s path=%s type=%s message=%s",
                request_id,
                request.method,
                request.url.path,
                type(exc).__name__,
                str(exc),
            )
            if not is_production():
                print(
                    f"[VAgent ERROR] request_id={request_id} {request.method} {request.url.path}\n"
                    f"{type(exc).__name__}: {exc}\n{tb}",
                    flush=True,
                )
            body = {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "요청을 처리하지 못했어요.",
                    "request_id": request_id,
                }
            }
            if not is_production():
                body["error"]["debug_type"] = type(exc).__name__
                body["error"]["debug_message"] = str(exc)
            response = JSONResponse(status_code=500, content=body)
        response.headers["X-Request-Id"] = request_id
        return response
