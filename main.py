"""
Главный файл для запуска MCP сервера.
"""

from src.mcp_server import mcp
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AcceptHeaderMiddleware:
    """
    ASGI middleware: если клиент не передал Accept с text/event-stream,
    подставляет 'application/json, text/event-stream'.
    Решает проблему совместимости MCP SDK >= 1.8.0 streamable-http
    с клиентами, не отправляющими корректный Accept.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                new_headers = [
                    (k, v) for k, v in scope["headers"] if k != b"accept"
                ]
                new_headers.append(
                    (b"accept", b"application/json, text/event-stream")
                )
                scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)


if __name__ == "__main__":
    use_sse = os.environ.get("USESSE", "false").lower() == "true"
    transport_method = "sse" if use_sse else "streamable-http"
    http_port = int(os.environ.get("HTTP_PORT", "8007"))

    logger.info(f"Запуск MCP сервера на порту {http_port} с транспортом {transport_method}")

    kwargs = {}
    if transport_method == "streamable-http":
        from starlette.middleware import Middleware
        kwargs["middleware"] = [Middleware(AcceptHeaderMiddleware)]
        kwargs["stateless_http"] = True

    mcp.run(
        transport=transport_method,
        host="0.0.0.0",
        port=http_port,
        path="/mcp",
        **kwargs,
    )
