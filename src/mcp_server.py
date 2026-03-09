"""
MCP сервер для работы с 1С:Напарник на основе FastMCP.
Оригинальная идея: https://github.com/comol/1c-code-checker
Алгоритмы API заимствованы из: https://github.com/SteelMorgan/spring-mcp-1c-copilot
"""

import os
import logging
from typing import Optional
from fastmcp import FastMCP
from .onec_api_client import OneCApiClient

# Настройка логирования
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

# Инициализация FastMCP сервера
mcp = FastMCP("1C_Copilot")

# Глобальные переменные
_api_client: Optional[OneCApiClient] = None


def _get_api_client() -> OneCApiClient:
    """Получить или создать API клиент."""
    global _api_client

    if _api_client is None:
        # Токен: приоритет файлу (Docker Secrets), fallback на env
        token_file = os.environ.get("ONEC_AI_TOKEN_FILE", "")
        if token_file and os.path.isfile(token_file):
            with open(token_file) as f:
                token = f.read().strip()
        else:
            token = os.environ.get("ONEC_AI_TOKEN", "")

        config = {
            "onec_ai_token": token,
            "base_url": os.environ.get("ONEC_AI_BASE_URL", "https://code.1c.ai"),
            "timeout": int(os.environ.get("ONEC_AI_TIMEOUT", "30")),
            "max_active_sessions": int(os.environ.get("MAX_ACTIVE_SESSIONS", "10")),
            "session_ttl": int(os.environ.get("SESSION_TTL", "3600")),
            "skill_name": os.environ.get("ONEC_AI_SKILL_NAME", "raw"),
            "auth_format": os.environ.get("ONEC_AI_AUTH_FORMAT", "plain"),
        }

        if not config["onec_ai_token"]:
            raise ValueError("ONEC_AI_TOKEN (или ONEC_AI_TOKEN_FILE) не установлен")

        _api_client = OneCApiClient(config)

    return _api_client


@mcp.tool()
async def ask_1c_ai(question: str, create_new_session: bool = False) -> str:
    """
    Задать вопрос ИИ 1С:Напарник.

    Args:
        question: Вопрос для ИИ
        create_new_session: Создать новую сессию (опционально)

    Returns:
        Ответ от ИИ 1С:Напарник
    """
    try:
        client = _get_api_client()
        conversation_id = await client.get_or_create_session(create_new=create_new_session)
        answer = await client.send_message(conversation_id, question)
        return f"{answer}\n\nСессия: {conversation_id}"
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def explain_1c_syntax(syntax_element: str, context: str = "") -> str:
    """
    Объяснить синтаксис элемента 1С.

    Args:
        syntax_element: Элемент синтаксиса для объяснения
        context: Контекст использования (опционально)

    Returns:
        Объяснение синтаксиса элемента
    """
    try:
        question = f"Объясни синтаксис элемента 1С: {syntax_element}"
        if context:
            question += f"\n\nКонтекст: {context}"

        client = _get_api_client()
        conversation_id = await client.get_or_create_session()
        answer = await client.send_message(conversation_id, question)
        return f"{answer}\n\nСессия: {conversation_id}"
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def check_1c_code(code: str, check_type: str = "syntax") -> str:
    """
    Проверить код 1С на ошибки, проблемы производительности и соответствие лучшим практикам.

    Args:
        code: Код 1С для проверки
        check_type: Тип проверки - syntax (синтаксические ошибки), logic (логические проблемы), performance (оптимизация)

    Returns:
        Результаты анализа кода с рекомендациями
    """
    try:
        check_descriptions = {
            "syntax": "синтаксические ошибки",
            "logic": "логические ошибки и потенциальные проблемы",
            "performance": "проблемы производительности и оптимизации"
        }

        check_desc = check_descriptions.get(check_type, "ошибки")
        question = f"Проверь этот код 1С на {check_desc} и дай рекомендации:\n\n```1c\n{code}\n```"

        client = _get_api_client()
        conversation_id = await client.get_or_create_session()
        answer = await client.send_message(conversation_id, question)

        return f"Проверка кода на {check_desc}:\n\n{answer}\n\nСессия: {conversation_id}"

    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


if __name__ == "__main__":
    # Запуск сервера
    use_sse = os.environ.get("USESSE", "false").lower() == "true"
    transport_method = "sse" if use_sse else "streamable-http"
    http_port = int(os.environ.get("HTTP_PORT", "8007"))

    logger.info(f"Запуск MCP сервера на порту {http_port} с транспортом {transport_method}")
    mcp.run(transport=transport_method, host="0.0.0.0", port=http_port, path="/mcp")
