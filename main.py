"""
Главный файл для запуска MCP сервера.
"""

from src.mcp_server import mcp
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class McpHttpMiddleware:
    """
    ASGI middleware для HTTP-совместимости streamable-http транспорта.

    Делает две вещи:
    1. На GET /mcp без Accept: text/event-stream (браузер, healthcheck)
       отвечает JSON-пояснением вместо голого 405. GET с SSE-Accept не
       перехватывает - это легальный запрос потока по протоколу Streamable
       HTTP, его обрабатывает транспорт. POST и прочие методы не затрагивает.
    2. Если клиент не передал Accept с text/event-stream, подставляет
       'application/json, text/event-stream' - совместимость MCP SDK >= 1.8.0
       с клиентами без корректного Accept.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode().lower()
            # GET /mcp с Accept: text/event-stream - это легальный запрос
            # SSE-потока по протоколу Streamable HTTP, его не перехватываем
            # (транспорт сам ответит по протоколу, в stateless - 405).
            if (
                scope.get("method") == "GET"
                and scope.get("path", "").rstrip("/") == "/mcp"
                and "text/event-stream" not in accept
            ):
                body = json.dumps({
                    "status": "ok",
                    "message": "MCP-сервер работает (транспорт streamable-http).",
                    "detail": "Endpoint принимает только POST от MCP-клиентов. "
                              "GET здесь не используется - 405 в логах при опросе "
                              "браузером или healthcheck это норма. Если клиент "
                              "требует SSE-транспорт, запустите с USESSE=true.",
                }, ensure_ascii=False).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")],
                })
                await send({"type": "http.response.body", "body": body})
                return
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
        kwargs["middleware"] = [Middleware(McpHttpMiddleware)]
        kwargs["stateless_http"] = True

    mcp.run(
        transport=transport_method,
        host="0.0.0.0",
        port=http_port,
        path="/mcp",
        **kwargs,
    )
