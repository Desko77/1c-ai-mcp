# 1C Code Checker — MCP-сервер для 1С:Напарник

[![Docker Hub](https://img.shields.io/docker/pulls/desko77/1c-code-checker)](https://hub.docker.com/r/desko77/1c-code-checker)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

MCP-сервер (Model Context Protocol) для интеграции IDE с API [1С:Напарник](https://code.1c.ai). Построен на FastMCP (Python), упакован в Docker. Работает с Cursor, Claude Code и любыми MCP-совместимыми клиентами.

Форк [comol/1c-code-checker](https://github.com/comol/1c-code-checker) с исправлениями API-формата (ошибки 422), заимствованными из [SteelMorgan/spring-mcp-1c-copilot](https://github.com/SteelMorgan/spring-mcp-1c-copilot).

## Предварительные требования

- **Docker** (или Docker Desktop)
- **Токен 1С:Напарник** — получить на [code.1c.ai](https://code.1c.ai) (требуется подписка ИТС)

## Быстрый старт

### Вариант A: Готовый образ из Docker Hub (рекомендуется)

```bash
docker run -d --name 1c-code-checker -p 8007:8007 \
  -e ONEC_AI_TOKEN="ваш-токен" \
  desko77/1c-code-checker:latest
```

Или через Docker Compose — создайте файл `docker-compose.yml`:

```yaml
services:
  1c-code-checker:
    image: desko77/1c-code-checker:latest
    container_name: 1c-code-checker
    ports:
      - "8007:8007"
    environment:
      ONEC_AI_TOKEN: "${ONEC_AI_TOKEN}"
    restart: unless-stopped
```

```bash
# Создать .env с токеном (не попадает в git)
echo 'ONEC_AI_TOKEN=ваш-токен' > .env

# Запустить
docker compose up -d
```

### Вариант B: Сборка из исходников

```bash
git clone https://github.com/Desko77/1c-code-checker.git
cd 1c-code-checker

# Создать .env с токеном
echo 'ONEC_AI_TOKEN=ваш-токен' > .env

# Собрать и запустить
docker compose up -d --build
```

### Проверка работоспособности

```bash
# Должен вернуть HTTP 200
curl http://localhost:8007/mcp
```

## Подключение к IDE

### Cursor

Добавьте в `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "1c-code-checker": {
      "url": "http://localhost:8007/mcp"
    }
  }
}
```

### Claude Code

Добавьте в `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "1c-code-checker": {
      "url": "http://localhost:8007/mcp"
    }
  }
}
```

### Другие MCP-клиенты

Endpoint: `http://localhost:8007/mcp`
Транспорт: Streamable HTTP (по умолчанию) или SSE (`USESSE=true`).

## Инструменты

### `check_1c_code`

Проверка кода 1С на ошибки, производительность и лучшие практики.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `code` | string | Код 1С для проверки |
| `check_type` | string | `syntax` (по умолчанию), `logic`, `performance` |

### `ask_1c_ai`

Произвольный вопрос к 1С:Напарник.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `question` | string | Вопрос |
| `create_new_session` | bool | Создать новую сессию (по умолчанию `false`) |

### `explain_1c_syntax`

Объяснение синтаксиса элемента 1С.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `syntax_element` | string | Элемент синтаксиса |
| `context` | string | Контекст использования (опционально) |

## Конфигурация

Все параметры передаются через переменные окружения.

| Переменная | Обязательна | По умолчанию | Описание |
|------------|-------------|--------------|----------|
| `ONEC_AI_TOKEN` | Да* | — | Токен API 1С:Напарник |
| `ONEC_AI_TOKEN_FILE` | Нет | — | Путь к файлу с токеном (Docker Secrets) |
| `ONEC_AI_BASE_URL` | Нет | `https://code.1c.ai` | Базовый URL API |
| `ONEC_AI_SKILL_NAME` | Нет | `raw` | Skill для дискуссий (`raw`, `custom`) |
| `ONEC_AI_AUTH_FORMAT` | Нет | `plain` | Формат Authorization: `plain` или `bearer` |
| `ONEC_AI_TIMEOUT` | Нет | `30` | Таймаут HTTP-запросов (сек) |
| `HTTP_PORT` | Нет | `8007` | Порт MCP-сервера |
| `USESSE` | Нет | `false` | Транспорт: `true`=SSE, `false`=streamable-http |
| `MAX_ACTIVE_SESSIONS` | Нет | `10` | Лимит одновременных сессий |
| `SESSION_TTL` | Нет | `3600` | TTL сессии (сек) |

\* Обязателен `ONEC_AI_TOKEN` или `ONEC_AI_TOKEN_FILE`.

### Docker Secrets

Для production-окружений токен можно передать через файл:

```yaml
services:
  1c-code-checker:
    image: desko77/1c-code-checker:latest
    environment:
      ONEC_AI_TOKEN_FILE: /run/secrets/onec_token
    secrets:
      - onec_token

secrets:
  onec_token:
    file: ./onec_token.txt
```

## Архитектура

```
MCP-клиент (Cursor / Claude Code)
  → FastMCP HTTP endpoint (:8007/mcp)
    → mcp_server.py (обработчики инструментов)
      → OneCApiClient (HTTP-клиент)
        → code.1c.ai API (SSE-стриминг)
          → парсинг ответа → возврат клиенту
```

### SSE-парсер

Поддерживает три формата ответа API:

| Формат | Структура | Тип |
|--------|-----------|-----|
| Legacy | `{"content_delta": "текст"}` | Инкрементальный |
| OpenAI-like | `{"choices": [{"delta": {"content": "текст"}}]}` | Инкрементальный |
| Completed | `{"content": {"text": "полный текст"}}` | Финальный |

Дополнительно:
- Автоматическое удаление `<thinking>`/`<think>` блоков из ответов
- Fallback при получении `tool_calls` — повтор запроса с `skill_name="raw"`
- Логирование `reasoning`-блоков на уровне DEBUG

## Разработка

### Локальный запуск без Docker

```bash
pip install -r requirements.txt
export ONEC_AI_TOKEN="ваш-токен"
python main.py
```

### Структура проекта

```
main.py                       # Точка входа
src/
  mcp_server.py                # MCP-инструменты (@mcp.tool)
  onec_api_client.py           # HTTP-клиент к API 1С:Напарник
Dockerfile                     # Dockerfile
docker-compose.yml             # Compose для сборки из исходников
tests/                         # Тестовые скрипты
.github/workflows/
  docker-publish.yml           # CI: сборка и публикация в Docker Hub
```

## Благодарности

- [comol/1c-code-checker](https://github.com/comol/1c-code-checker) — оригинальная идея
- [SteelMorgan/spring-mcp-1c-copilot](https://github.com/SteelMorgan/spring-mcp-1c-copilot) — правильные алгоритмы API
- [FastMCP](https://github.com/jlowin/fastmcp) — фреймворк MCP-серверов

## Лицензия

MIT — см. [LICENSE](LICENSE)
