"""
Главный файл для запуска MCP сервера.
"""

from src.mcp_server import mcp
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    use_sse = os.environ.get("USESSE", "false").lower() == "true"
    transport_method = "sse" if use_sse else "streamable-http"
    http_port = int(os.environ.get("HTTP_PORT", "8007"))
    
    logger.info(f"Запуск MCP сервера на порту {http_port} с транспортом {transport_method}")
    mcp.run(transport=transport_method, host="0.0.0.0", port=http_port, path="/mcp")

