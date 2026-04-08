# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP-сервер (Model Context Protocol) для интеграции с API 1С:Напарник (code.1c.ai). Построен на FastMCP (Python), упакован в Docker. Предоставляет 12 инструментов: анализ кода (`check_1c_code`, `ask_1c_ai`, `explain_1c_syntax`, `review_1c_code`, `rewrite_1c_code`, `modify_1c_code`) и документация (`its_help`, `fetch_its`, `search_1c_documentation`, `onec_help`, `diff_1c_documentation_versions`, `config_help`) - все через HTTP API 1С:Напарник.

Основан на идее `comol/1c-code-checker` с исправлениями формата API-запросов (ошибки 422), заимствованными из `SteelMorgan/spring-mcp-1c-copilot`.

## Architecture

```
main.py                  ← точка входа, запуск FastMCP
src/
  mcp_server.py          ← определение MCP-инструментов (@mcp.tool)
  onec_api_client.py     ← HTTP-клиент к API 1С:Напарник (httpx + SSE)
Dockerfile               ← основной Dockerfile (python:3.11-slim)
docker-compose.yml       ← compose для запуска
tests/                   ← тестовые скрипты
```

**Поток данных:** MCP-клиент (Cursor/Claude Code) → FastMCP HTTP endpoint (`:8007/mcp`) → `mcp_server.py` (tool handlers) → `OneCApiClient` → `code.1c.ai` API (SSE stream) → парсинг ответа → возврат клиенту.

**Сессии:** `OneCApiClient` управляет пулом conversation sessions (создание, переиспользование, TTL-очистка, лимит активных).

**API 1С:Напарник:**
- `POST /chat_api/v1/conversations/` — создание дискуссии (поля: `tool_name`, `skill_name`, `is_chat`)
- `POST /chat_api/v1/conversations/{id}/messages` — отправка сообщения (SSE-ответ), content: `{content: {instruction: "..."}}`

## Build & Run

```bash
# Docker build
docker build -t 1c-ai-mcp .

# Docker run
docker run -d -p 8007:8007 -e ONEC_AI_TOKEN="token" 1c-ai-mcp

# Docker Compose
docker compose up -d

# Local dev
pip install -r requirements.txt
ONEC_AI_TOKEN="token" python main.py
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ONEC_AI_TOKEN` | Yes* | — | API-токен 1С:Напарник |
| `ONEC_AI_TOKEN_FILE` | No | — | Путь к файлу с токеном (Docker Secrets, приоритет над TOKEN) |
| `ONEC_AI_BASE_URL` | No | `https://code.1c.ai` | Базовый URL API |
| `ONEC_AI_SKILL_NAME` | No | `raw` | Skill для создания дискуссий (`raw`, `custom`) |
| `ONEC_AI_AUTH_FORMAT` | No | `plain` | Формат Authorization header (`plain` / `bearer`) |
| `ONEC_AI_TIMEOUT` | No | `120` | Таймаут HTTP-запросов (сек) |
| `ONEC_CONFIG_NAME` | No | — | Конфигурация по умолчанию для config_help (например, "ERP", "ЗУП") |
| `HTTP_PORT` | No | `8007` | Порт MCP-сервера |
| `USESSE` | No | `false` | Транспорт: `true`=SSE, `false`=streamable-http |
| `MAX_ACTIVE_SESSIONS` | No | `10` | Лимит активных сессий |
| `SESSION_TTL` | No | `3600` | TTL сессии (сек) |
| `MCP_TOOL_CALL_MODE` | No | `standard` | Режим вызова upstream: `standard` (промпты) / `direct` (прямой вызов инструментов) |
| `ONEC_AI_INPUT_MAX_LENGTH` | No | `100000` | Макс. длина входных данных (символов) |
| `LOG_LEVEL` | No | `INFO` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`) |

\* Обязателен `ONEC_AI_TOKEN` или `ONEC_AI_TOKEN_FILE`.

## Testing

Тесты — скрипты в `tests/`, запускаются вручную против работающего контейнера:
```bash
python tests/test-api.py
python tests/test-check-tool.py
```

## CI/CD

GitHub Actions (`.github/workflows/docker-publish.yml`): сборка и публикация Docker-образа в Docker Hub при push в main/master или создании тега `v*`.

## Key Design Decisions

- `content` в `MessageRequest` — словарь `{content: {instruction: ...}}`, НЕ массив. Это критичное отличие от оригинального контейнера, которое устраняло ошибки 422.
- SSE-парсер поддерживает несколько форматов ответа: `content.content`, `content.text`, `content_delta` (строка или объект с `.content`), OpenAI-like `choices[0].delta.content`. Приоритет: финальный `content.text`/`content.content` > накопленные дельты.
- Echo-чанки с `role: "user"` и `finished: true` игнорируются — парсер ждёт ответ ассистента.
- Thinking-теги (`<thinking>`, `<think>`) автоматически удаляются из ответов.
- При получении `tool_calls` в ответе обычных инструментов - автоматический fallback: создается новая сессия с `skill_name="raw"` и запрос повторяется (однократно).
- Документационные инструменты (its_help, search_1c_documentation и др.) используют `skill_name="custom"` + механизм tool chain: модель генерирует tool_calls к серверным инструментам 1С:Напарник (Search_ITS, Fetch_ITS, Search_Documentation, Diff_Documentation_Versions), клиент подтверждает каждый вызов (status="accepted"), сервер выполняет поиск, модель формирует ответ с реальными данными из ИТС/документации.
- `skill_name` по умолчанию `"raw"`, конфигурируется через `ONEC_AI_SKILL_NAME`. Допустимые значения: `raw`, `custom`, `docstring`, `explain`, `review`, `modify`, `system`.
- **Direct mode** (`MCP_TOOL_CALL_MODE=direct`): документационные инструменты и check_1c_code(syntax) вызывают upstream-инструменты 1С:Напарник напрямую по имени (`mcp__knowledge-hub__Search_ITS`, `mcp__knowledge-hub__Fetch_ITS`, `mcp__knowledge-hub__Search_Documentation`, `mcp__knowledge-hub__Diff_Documentation_Versions`, `mcp__syntax-checker__validate`), вместо отправки текстовых промптов. Метод `call_exact_tool`: отправка сообщения -> матчинг tool_call по имени -> ACK -> извлечение результата. При сбое - автоматический fallback на промпт-режим (standard). По умолчанию `standard` для обратной совместимости.
