"""
MCP сервер для работы с 1С:Напарник на основе FastMCP.
Оригинальная идея: https://github.com/comol/1c-code-checker
Алгоритмы API заимствованы из: https://github.com/SteelMorgan/spring-mcp-1c-copilot
"""

import os
import logging
import unicodedata
from typing import Optional
from fastmcp import FastMCP
from .onec_api_client import OneCApiClient, DirectToolError, _strip_thinking_tags

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


# ---------------------------------------------------------------------------
# Direct mode helpers
# ---------------------------------------------------------------------------

_INPUT_MAX_LENGTH = int(os.environ.get("ONEC_AI_INPUT_MAX_LENGTH", "100000"))
_DIRECT_MODE = os.environ.get("MCP_TOOL_CALL_MODE", "standard").lower() == "direct"


def _is_direct_mode() -> bool:
    """Check if direct tool calling mode is enabled (cached at startup)."""
    return _DIRECT_MODE


def _sanitize_text(text: str) -> str:
    """Clean text: remove thinking tags, normalize unicode, strip control chars."""
    if not text:
        return text
    text = _strip_thinking_tags(text)
    text = unicodedata.normalize('NFKC', text)
    cleaned = ''
    for char in text:
        if unicodedata.category(char) not in ('Cc', 'Cf') or char in ('\n', '\r', '\t'):
            cleaned += char
    return cleaned.strip()


def _truncate_input(text: str) -> str:
    """Truncate input to configured max length (chars, not bytes)."""
    if len(text) > _INPUT_MAX_LENGTH:
        return text[:_INPUT_MAX_LENGTH]
    return text


async def _send_prompt(query: str) -> str:
    """Send a prompt via tool chain (standard mode). Used as fallback for direct mode."""
    return await _send_with_tools(query)


async def _call_direct_tool(upstream_tool: str, arguments: dict, fallback_prompt: str = "") -> str:
    """Call an upstream tool directly. Falls back to prompt on failure."""
    client = _get_api_client()
    conversation_id = await client.create_conversation(skill_name_override="custom")
    try:
        result = await client.call_exact_tool(conversation_id, upstream_tool, arguments)
        cleaned = _sanitize_text(result)
        if cleaned:
            return cleaned
        logger.warning(f"Direct tool {upstream_tool} returned empty, falling back to prompt")
    except DirectToolError as e:
        logger.warning(f"Direct mode fallback: {e.diagnostic_summary()}")
    except Exception as e:
        logger.warning(f"Direct mode error for {upstream_tool}: {e}")

    # Освобождаем слот сессии, чтобы не накапливать "мертвые" сессии при fallback
    client.sessions.pop(conversation_id, None)

    if fallback_prompt:
        return await _send_prompt(fallback_prompt)
    return f"Ошибка: инструмент {upstream_tool} не вернул результата."


@mcp.tool()
async def ask_1c_ai(question: str, create_new_session: bool = False) -> str:
    """
    Ask a free-form question to the 1C:Naparnik AI assistant.
    Use this tool for any 1C-related question that does not fit the specialised tools:
    general 1C development advice, architecture questions, explanations of concepts,
    syntax clarification, or anything else about the 1C:Enterprise ecosystem.

    Unlike all other tools (which always start a fresh session), this tool reuses the
    most recent session by default to preserve conversation context for follow-up questions.
    Set create_new_session=True to start from scratch when switching topics.

    For code checking use check_1c_code, for style review use review_1c_code,
    for documentation search use search_1c_documentation / onec_help / its_help.

    Args:
        question: Any question about 1C:Enterprise development
        create_new_session: If True, starts a fresh conversation. If False (default), reuses the latest session.

    Returns:
        Answer from the 1C:Naparnik AI
    """
    question = _sanitize_text(_truncate_input(question))
    if not question:
        return "Ошибка: вопрос не может быть пустым"
    try:
        client = _get_api_client()
        conversation_id = await client.get_or_create_session(create_new=create_new_session)
        answer = await client.send_message(conversation_id, question)
        return _sanitize_text(answer)
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def explain_1c_syntax(syntax_element: str, context: str = "") -> str:
    """
    Explain a specific 1C:Enterprise syntax element or language construct.
    Use this for focused questions about a particular keyword, operator, statement,
    or built-in function. Provide optional context to get a more relevant explanation.

    For broader questions, use ask_1c_ai instead.

    Args:
        syntax_element: The syntax element to explain (e.g. 'ВЫБРАТЬ', 'ОбщийМодуль', 'Попытка')
        context: Optional usage context for a more relevant answer

    Returns:
        Explanation of the syntax element
    """
    syntax_element = _sanitize_text(_truncate_input(syntax_element))
    if not syntax_element:
        return "Ошибка: элемент синтаксиса не может быть пустым"
    try:
        question = f"Объясни синтаксис элемента 1С: {syntax_element}"
        if context:
            question += f"\n\nКонтекст: {_sanitize_text(context)}"

        client = _get_api_client()
        conversation_id = await client.get_or_create_session()
        answer = await client.send_message(conversation_id, question)
        return _sanitize_text(answer)
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def check_1c_code(code: str, check_type: str = "syntax") -> str:
    """
    Check 1C:Enterprise code for syntax errors, logical issues, and performance problems.
    Use this tool for a technical correctness check: will the code compile, are there bugs,
    are there N+1 queries or other performance anti-patterns.

    In direct mode, syntax checking uses an upstream syntax-checker for precise validation,
    then adds logic and performance analysis via prompt. Automatically falls back to
    prompt-only mode if the direct tool is unavailable.

    For style/standards compliance, use review_1c_code instead.
    For an AI-proposed rewrite, use rewrite_1c_code instead.

    Args:
        code: 1C code to check
        check_type: Check type - syntax, logic, or performance

    Returns:
        List of errors and issues found with recommendations
    """
    code = _sanitize_text(_truncate_input(code))
    if not code.strip():
        return "Ошибка: код для проверки не может быть пустым"

    check_descriptions = {
        "syntax": "синтаксические ошибки",
        "logic": "логические ошибки и потенциальные проблемы",
        "performance": "проблемы производительности и оптимизации"
    }
    check_desc = check_descriptions.get(check_type, "ошибки")

    # Промпт формируется ДО ветвления (для fallback)
    prompt = (
        f"Проверь этот код 1С на {check_desc} и дай рекомендации:\n\n"
        f"```bsl\n{code}\n```"
    )

    try:
        # Direct mode: только когда запрашивается syntax (или полная проверка)
        if _is_direct_mode() and check_type == "syntax":
            try:
                syntax_result = await _call_direct_tool(
                    "mcp__syntax-checker__validate",
                    {"code": code},
                    fallback_prompt=""
                )

                logic_perf_prompt = (
                    "Проверь этот код 1С ТОЛЬКО на логические ошибки и проблемы производительности.\n"
                    "Не проверяй синтаксис (он уже проверен) и не проверяй стиль/стандарты.\n"
                    "Найди: ошибки логики, потенциальные баги, запросы в цикле, неоптимальные конструкции.\n\n"
                    f"Код:\n```bsl\n{code}\n```"
                )
                logic_result = await _send_prompt(logic_perf_prompt)

                parts = []
                if syntax_result:
                    parts.append(f"## Синтаксис\n\n{syntax_result}")
                if logic_result:
                    parts.append(f"## Логика и производительность\n\n{logic_result}")
                return "\n\n".join(parts) if parts else "Ошибок не найдено."

            except DirectToolError as e:
                logger.warning(f"check_1c_code direct fallback: {e.diagnostic_summary()}")
                # Полный fallback на единый промпт через tool chain
                return await _send_prompt(prompt)

        # Standard mode
        return await _send_with_tools(prompt)

    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


async def _send_with_tools(query: str) -> str:
    """Отправить запрос через tool chain (skill_name='custom' + автоподтверждение tool_calls)."""
    client = _get_api_client()
    conversation_id = await client.create_conversation(skill_name_override="custom")
    return await client.send_message_with_tool_chain(conversation_id, query)


@mcp.tool()
async def review_1c_code(code: str) -> str:
    """
    Review 1C:Enterprise code for style, standards compliance, and best practices.
    Use this tool for a quality/style review: naming conventions, code structure,
    compliance with 1C development standards (ITS), readability, and recommendations.

    This tool does NOT check for syntax errors or bugs - use check_1c_code for that.
    For an AI-proposed rewrite, use rewrite_1c_code instead.

    Args:
        code: 1C code to review

    Returns:
        Style issues, standards violations, and improvement recommendations
    """
    code = _sanitize_text(_truncate_input(code))
    if not code.strip():
        return "Ошибка: код не может быть пустым"

    prompt = (
        "Проведи code review этого кода 1С с точки зрения стиля и стандартов.\n\n"
        "Проверь:\n"
        "1. Соответствие стандартам разработки 1С (ИТС)\n"
        "2. Именование переменных, процедур, функций\n"
        "3. Структуру и читаемость кода\n"
        "4. Обработку ошибок и граничных случаев\n\n"
        "Не ищи синтаксические ошибки - только стиль, стандарты и рекомендации.\n"
        f"Для каждого замечания укажи конкретное место и предложи исправление.\n\nКод:\n```bsl\n{code}\n```"
    )
    try:
        client = _get_api_client()
        conversation_id = await client.get_or_create_session(create_new=True)
        answer = await client.send_message(conversation_id, prompt)
        return _sanitize_text(answer)
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def rewrite_1c_code(code: str, goal: str = "") -> str:
    """
    Get AI-proposed rewrite of 1C:Enterprise code with best practices applied.
    The AI analyzes the code and proposes its own improved version.

    Unlike modify_1c_code (which follows explicit user instructions), this tool lets
    the AI decide what and how to improve. Optionally provide a goal to guide the rewrite
    direction (e.g. 'optimize performance', 'improve readability', 'add error handling').

    Args:
        code: 1C code to rewrite
        goal: Optional goal for the rewrite. If empty, the AI decides what to improve.

    Returns:
        Rewritten code with explanation of all changes made
    """
    code = _sanitize_text(_truncate_input(code))
    if not code.strip():
        return "Ошибка: код не может быть пустым"

    goal_line = f"Цель переписывания: {goal.strip()}\n\n" if goal.strip() else ""
    prompt = (
        f"Перепиши этот код 1С, сделав его лучше.\n\n{goal_line}"
        "Примени лучшие практики, стандарты ИТС, оптимизацию.\n"
        "Верни: 1) Полный переписанный код 2) Список изменений с объяснениями\n\n"
        f"Исходный код:\n```bsl\n{code}\n```"
    )
    try:
        client = _get_api_client()
        conversation_id = await client.get_or_create_session(create_new=True)
        answer = await client.send_message(conversation_id, prompt)
        return _sanitize_text(answer)
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def modify_1c_code(instruction: str, code: str = "") -> str:
    """
    Modify 1C:Enterprise code according to an explicit user instruction.
    Use this to apply a specific change: fix a particular bug, add a specific feature,
    refactor in a specific way. The AI follows your instruction precisely.

    Unlike rewrite_1c_code (where AI decides what to improve), this tool does exactly
    what you tell it to do. If code is not provided, generates new code from instruction.

    Args:
        instruction: Clear description of what changes are needed
        code: Source 1C code to modify (optional - if empty, generates new code)

    Returns:
        Modified code with a summary of changes
    """
    instruction = _sanitize_text(_truncate_input(instruction))
    if not instruction.strip():
        return "Ошибка: инструкция не может быть пустой"

    prompt = f"Измени код 1С по заданию. Верни итоговый код и список изменений.\n\nЗадание:\n{instruction.strip()}"
    if code:
        code = _sanitize_text(_truncate_input(code))
        if code.strip():
            prompt += f"\n\nКод:\n```bsl\n{code}\n```"
    try:
        client = _get_api_client()
        conversation_id = await client.get_or_create_session(create_new=True)
        answer = await client.send_message(conversation_id, prompt)
        return _sanitize_text(answer)
    except Exception as e:
        return f"Ошибка при обращении к 1C.ai: {str(e)}"


@mcp.tool()
async def its_help(query: str) -> str:
    """
    Search the 1C ITS (Information Technology Support) knowledge base.
    Use this tool to find methodological recommendations, technical articles,
    configuration documentation, standards, and best practices published on ITS.

    Results include document IDs (its-...-hdoc) that can be passed to fetch_its for full content.
    In direct mode, uses upstream Search_ITS tool for precise results.

    Args:
        query: Search query for ITS knowledge base

    Returns:
        Information from ITS with document IDs for use with fetch_its
    """
    query = _sanitize_text(_truncate_input(query))
    if not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым"

    prompt = f"Найди в базе знаний ИТС: {query}"
    try:
        if _is_direct_mode():
            return await _call_direct_tool(
                "mcp__knowledge-hub__Search_ITS",
                {"query": query},
                fallback_prompt=prompt,
            )
        return await _send_with_tools(prompt)
    except Exception as e:
        return f"Ошибка при поиске по ИТС: {str(e)}"


@mcp.tool()
async def fetch_its(id: str = "root") -> str:
    """
    Fetch content of a specific ITS document, catalog or database by its ID.
    Typically used after its_help to read a specific document found in search results.
    Use id='root' to explore the ITS structure. Supported IDs: root, superior, v8std,
    or document/catalog IDs like 'its-...-hdoc' or 'its-...-hdir'.

    In direct mode, uses upstream Fetch_ITS tool for precise results.

    Args:
        id: ITS document/catalog identifier (default: 'root')

    Returns:
        Content of the ITS document or catalog listing
    """
    item_id = (id or "root").strip() or "root"

    prompt = f"Получи содержимое документа ИТС по идентификатору: {item_id}"
    try:
        if _is_direct_mode():
            return await _call_direct_tool(
                "mcp__knowledge-hub__Fetch_ITS",
                {"id": item_id},
                fallback_prompt=prompt,
            )
        return await _send_with_tools(prompt)
    except Exception as e:
        return f"Ошибка при получении документа ИТС: {str(e)}"


@mcp.tool()
async def search_1c_documentation(query: str, version: str = "v8.5.1") -> str:
    """
    Search 1C:Enterprise platform documentation for a specific version.
    Use this to find information about built-in language methods, platform objects,
    types, events, properties, and general platform capabilities.
    For version-specific search, specify the version parameter.

    In direct mode, uses upstream Search_Documentation tool for precise results.
    For general queries use onec_help (latest version, no version parameter needed).

    Args:
        query: Search query about 1C:Enterprise platform
        version: Platform documentation version in format v8.x.x (default: v8.5.1)

    Returns:
        Information from 1C platform documentation
    """
    query = _sanitize_text(_truncate_input(query))
    if not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым"

    prompt = f"Найди в документации платформы 1С:Предприятие версии {version}: {query}"
    try:
        if _is_direct_mode():
            return await _call_direct_tool(
                "mcp__knowledge-hub__Search_Documentation",
                {"query": query, "version": version},
                fallback_prompt=prompt,
            )
        return await _send_with_tools(prompt)
    except Exception as e:
        return f"Ошибка при поиске в документации: {str(e)}"


@mcp.tool()
async def onec_help(query: str) -> str:
    """
    Search 1C:Enterprise platform documentation (latest version).
    Use this tool to find information about built-in language methods, platform objects,
    types, events, properties, and general platform capabilities.
    For version-specific search, use search_1c_documentation instead.

    In direct mode, uses upstream Search_Documentation tool for precise results.

    Args:
        query: Search query about 1C:Enterprise platform

    Returns:
        Information from 1C platform documentation
    """
    query = _sanitize_text(_truncate_input(query))
    if not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым"

    prompt = f"Найди в документации платформы 1С:Предприятие: {query}"
    try:
        if _is_direct_mode():
            return await _call_direct_tool(
                "mcp__knowledge-hub__Search_Documentation",
                {"query": query, "version": "v8.5.1"},
                fallback_prompt=prompt,
            )
        return await _send_with_tools(prompt)
    except Exception as e:
        return f"Ошибка при поиске в документации: {str(e)}"


@mcp.tool()
async def diff_1c_documentation_versions(version_a: str, version_b: str, query: str = "") -> str:
    """
    Compare 1C:Enterprise platform documentation between two versions.
    Use when asked about changes between platform versions.
    version_a should be the earlier version, version_b the later one.

    In direct mode, uses upstream Diff_Documentation_Versions tool for precise results.

    Args:
        version_a: Earlier version in format v8.3.27 or v8.3.27.189
        version_b: Later version in format v8.3.27 or v8.3.27.189
        query: Optional subject area to narrow the comparison (e.g. 'HTTP')

    Returns:
        Differences between the two documentation versions
    """
    if not version_a.strip() or not version_b.strip():
        return "Ошибка: version_a и version_b обязательны"

    prompt = f"Сравни документацию платформы 1С между версиями {version_a} и {version_b}"
    if query.strip():
        prompt += f". Предметная область: {query}"

    try:
        if _is_direct_mode():
            args = {"version_a": version_a, "version_b": version_b}
            if query.strip():
                args["query"] = query
            return await _call_direct_tool(
                "mcp__knowledge-hub__Diff_Documentation_Versions",
                args,
                fallback_prompt=prompt,
            )
        return await _send_with_tools(prompt)
    except Exception as e:
        return f"Ошибка при сравнении версий: {str(e)}"


@mcp.tool()
async def config_help(query: str, config_name: str = "") -> str:
    """
    Search documentation for a specific 1C:Enterprise application (configuration).
    Use this to find information about objects, modules, registers, documents, catalogs,
    and business logic of a specific 1C application - such as ERP, ЗУП, Бухгалтерия, УТ, etc.

    Use search_1c_documentation for platform-level documentation (language, objects, types).
    Use config_help for application-level documentation (business logic, specific documents/registers).

    If config_name is empty, the server uses the default from ONEC_CONFIG_NAME env var.

    Args:
        query: Search query about the 1C application/configuration
        config_name: Name of the 1C application (e.g. 'ERP', 'ЗУП'). If empty, uses ONEC_CONFIG_NAME.

    Returns:
        Information from the application documentation
    """
    # No direct mode: no upstream tool for configuration-specific docs
    query = _sanitize_text(_truncate_input(query))
    if not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым"
    try:
        effective_config = config_name or os.environ.get("ONEC_CONFIG_NAME", "")
        msg = query
        if effective_config:
            msg = f"Найди информацию о конфигурации 1С {effective_config}: {query}"
        return await _send_with_tools(msg)
    except Exception as e:
        return f"Ошибка при поиске по конфигурации: {str(e)}"


if __name__ == "__main__":
    # Запуск сервера
    use_sse = os.environ.get("USESSE", "false").lower() == "true"
    transport_method = "sse" if use_sse else "streamable-http"
    http_port = int(os.environ.get("HTTP_PORT", "8007"))

    logger.info(f"Запуск MCP сервера на порту {http_port} с транспортом {transport_method}")
    mcp.run(transport=transport_method, host="0.0.0.0", port=http_port, path="/mcp")
