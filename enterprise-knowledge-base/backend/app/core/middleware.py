"""请求 ID 追踪中间件"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
thread_id_var: ContextVar[str] = ContextVar("thread_id", default="")
user_scope_var: ContextVar[str] = ContextVar("user_scope", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        thread_id = request.headers.get("X-Thread-ID", str(uuid.uuid4()))
        request_id_var.set(request_id)
        thread_id_var.set(thread_id)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Thread-ID"] = thread_id
        return response
