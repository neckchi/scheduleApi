from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

CORRELATION_ID_CTX_KEY = 'correlation_id'

_correlation_id_ctx_var: ContextVar[str | None] = ContextVar(CORRELATION_ID_CTX_KEY, default=None)


def get_correlation_id() -> str:
	return _correlation_id_ctx_var.get()


class RequestContextLogMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
		correlation_id = _correlation_id_ctx_var.set(request.headers.get('X-Correlation-ID', str(uuid4())))
		response = await call_next(request)
		response.headers['X-Correlation-ID'] = get_correlation_id()
		_correlation_id_ctx_var.reset(correlation_id)
		return response
