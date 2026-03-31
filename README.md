# 1C Code Checker - MCP-сервер для 1С:Напарник

[![Docker Hub](https://img.shields.io/docker/pulls/desko77/1c-code-checker)](https://hub.docker.com/r/desko77/1c-code-checker)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

MCP-сервер (Model Context Protocol) для интеграции IDE с API [1С:Напарник](https://code.1c.ai). Построен на FastMCP (Python), упакован в Docker. Работает с Cursor, Claude Code и любыми MCP-совместимыми клиентами.

**12 инструментов**: анализ кода (проверка, ревью, рефакторинг) и поиск в документации (ИТС, платформа, конфигурации).

Форк [comol/1c-code-checker](https://github.com/comol/1c-code-checker) с исправлениями API-формата (ошибки 422), заимствованными из [SteelMorgan/spring-mcp-1c-copilot](https://github.com/SteelMorgan/spring-mcp-1c-copilot).

## Предварительные требования

- **Docker** (или Docker Desktop)
- **Токен 1С:Напарник** - получить на [code.1c.ai](https://code.1c.ai) (требуется подписка ИТС)

## Быстрый старт

### Вариант A: Готовый образ из Docker Hub (рекомендуется)

```bash
docker run -d --name 1c-code-checker -p 8007:8007 \
  -e ONEC_AI_TOKEN="ваш-токен" \
  desko77/1c-code-checker:latest
```

Или через Docker Compose - создайте файл `docker-compose.yml`:

```yaml
services:
  1c-code-checker:
    image: desko77/1c-code-checker:latest
    container_name: 1c-code-checker
    ports:
      - "8007:8007"
    environment:
      ONEC_AI_TOKEN: "${ONEC_AI_TOKEN}"
    restart: always
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

### Анализ кода

#### `check_1c_code`

Проверка кода 1С: синтаксис, логика, производительность. В direct mode синтаксис проверяется через upstream syntax-checker.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `code` | string | Код 1С для проверки |
| `check_type` | string | `syntax` (по умолчанию), `logic`, `performance` |

#### `ask_1c_ai`

Произвольный вопрос к 1С:Напарник. Сохраняет контекст диалога между вызовами.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `question` | string | Вопрос |
| `create_new_session` | bool | Новая сессия (по умолчанию `false` - переиспользует предыдущую) |

#### `review_1c_code`

Code review: стиль, стандарты ИТС, именование, структура, читаемость. Не проверяет синтаксис.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `code` | string | Код 1С для ревью |

#### `rewrite_1c_code`

ИИ предлагает свою улучшенную версию кода с объяснением изменений.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `code` | string | Код 1С для переписывания |
| `goal` | string | Направление: `optimize`, `readability`, `error handling` (опционально) |

#### `modify_1c_code`

Модификация кода по явной инструкции. Если код не указан - генерирует новый.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `instruction` | string | Описание требуемых изменений |
| `code` | string | Исходный код (опционально) |

#### `explain_1c_syntax`

Объяснение конкретного элемента синтаксиса 1С.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `syntax_element` | string | Элемент синтаксиса |
| `context` | string | Контекст использования (опционально) |

### Документация и справка

#### `its_help`

Поиск по базе знаний ИТС (стандарты, методики, статьи). Возвращает ID документов для `fetch_its`.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Поисковый запрос |

#### `fetch_its`

Чтение документа ИТС по идентификатору. Используется после `its_help`.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `id` | string | ID документа (`root`, `v8std`, `its-...-hdoc`) |

#### `search_1c_documentation`

Поиск в документации платформы 1С:Предприятие для конкретной версии.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Поисковый запрос |
| `version` | string | Версия (по умолчанию `v8.5.1`) |

#### `onec_help`

Поиск в документации платформы (последняя версия). Как `search_1c_documentation`, но без указания версии.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Поисковый запрос |

#### `diff_1c_documentation_versions`

Сравнение документации платформы между двумя версиями.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `version_a` | string | Более ранняя версия (например, `v8.3.25`) |
| `version_b` | string | Более поздняя версия (например, `v8.5.1`) |
| `query` | string | Предметная область (опционально) |

#### `config_help`

Поиск документации по прикладным конфигурациям (ERP, Бухгалтерия, ЗУП, УТ и др.).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Поисковый запрос |
| `config_name` | string | Название конфигурации (опционально, берется из `ONEC_CONFIG_NAME`) |

## Конфигурация

Все параметры передаются через переменные окружения.

| Переменная | Обязательна | По умолчанию | Описание |
|------------|-------------|--------------|----------|
| `ONEC_AI_TOKEN` | Да* | - | Токен API 1С:Напарник |
| `ONEC_AI_TOKEN_FILE` | Нет | - | Путь к файлу с токеном (Docker Secrets) |
| `ONEC_AI_BASE_URL` | Нет | `https://code.1c.ai` | Базовый URL API |
| `ONEC_AI_SKILL_NAME` | Нет | `raw` | Skill для дискуссий (`raw`, `custom`) |
| `ONEC_AI_AUTH_FORMAT` | Нет | `plain` | Формат Authorization: `plain` или `bearer` |
| `ONEC_AI_TIMEOUT` | Нет | `120` | Таймаут HTTP-запросов (сек) |
| `ONEC_CONFIG_NAME` | Нет | - | Конфигурация для config_help (например, `ERP`, `ЗУП`) |
| `MCP_TOOL_CALL_MODE` | Нет | `standard` | Режим: `standard` (промпты) / `direct` (прямой вызов upstream) |
| `ONEC_AI_INPUT_MAX_LENGTH` | Нет | `100000` | Макс. длина входных данных (символов) |
| `HTTP_PORT` | Нет | `8007` | Порт MCP-сервера |
| `USESSE` | Нет | `false` | Транспорт: `true`=SSE, `false`=streamable-http |
| `MAX_ACTIVE_SESSIONS` | Нет | `10` | Лимит одновременных сессий |
| `SESSION_TTL` | Нет | `3600` | TTL сессии (сек) |
| `LOG_LEVEL` | Нет | `INFO` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`) |

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

### Direct Mode

При `MCP_TOOL_CALL_MODE=direct` документационные инструменты и `check_1c_code` (syntax) вызывают upstream-инструменты 1С:Напарник напрямую по имени, вместо текстовых промптов. Это дает более точные результаты.

Upstream-инструменты:
- `mcp__knowledge-hub__Search_ITS` - для `its_help`
- `mcp__knowledge-hub__Fetch_ITS` - для `fetch_its`
- `mcp__knowledge-hub__Search_Documentation` - для `search_1c_documentation`, `onec_help`
- `mcp__knowledge-hub__Diff_Documentation_Versions` - для `diff_1c_documentation_versions`
- `mcp__syntax-checker__validate` - для `check_1c_code` (syntax)

При сбое direct-вызова автоматический fallback на промпт-режим. По умолчанию `standard` для обратной совместимости.

## Архитектура

```
MCP-клиент (Cursor / Claude Code)
  -> FastMCP HTTP endpoint (:8007/mcp)
    -> mcp_server.py (обработчики инструментов)
      -> OneCApiClient (HTTP-клиент)
        -> code.1c.ai API (SSE-стриминг)
          -> парсинг ответа -> возврат клиенту
```

### Два режима работы

- **Standard mode** (по умолчанию): инструменты формируют текстовые промпты и отправляют в API. Документационные инструменты используют tool chain - модель сама решает какой серверный инструмент вызвать.
- **Direct mode** (`MCP_TOOL_CALL_MODE=direct`): инструменты явно запрашивают конкретный upstream-инструмент по имени, матчат ответ и подтверждают вызов. При сбое - автоматический fallback на standard mode.

### SSE-парсер

Поддерживает три формата ответа API:

| Формат | Структура | Тип |
|--------|-----------|-----|
| Legacy | `{"content_delta": "текст"}` | Инкрементальный |
| OpenAI-like | `{"choices": [{"delta": {"content": "текст"}}]}` | Инкрементальный |
| Completed | `{"content": {"text": "полный текст"}}` | Финальный |

Дополнительно:
- Автоматическое удаление `<thinking>`/`<think>` блоков из ответов
- Unicode-нормализация и очистка управляющих символов
- Fallback при получении `tool_calls` - повтор запроса с `skill_name="raw"`
- Обрезка входных данных по `ONEC_AI_INPUT_MAX_LENGTH`

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

- [comol/1c-code-checker](https://github.com/comol/1c-code-checker) - оригинальная идея
- [SteelMorgan/spring-mcp-1c-copilot](https://github.com/SteelMorgan/spring-mcp-1c-copilot) - правильные алгоритмы API
- [FastMCP](https://github.com/jlowin/fastmcp) - фреймворк MCP-серверов

## Лицензия

MIT - см. [LICENSE](LICENSE)
