# Dockerfile для FastMCP сервера с исправленными алгоритмами API
# Оригинальная идея: https://github.com/comol/1c-code-checker
# Алгоритмы API: https://github.com/SteelMorgan/spring-mcp-1c-copilot

FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY src/ ./src/
COPY main.py .

# Создаем пользователя для запуска приложения
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Переменные окружения (секреты передаются через docker run -e / compose)
ENV ONEC_AI_BASE_URL="https://code.1c.ai"
ENV ONEC_AI_TIMEOUT=30
ENV ONEC_AI_SKILL_NAME="raw"
ENV ONEC_AI_AUTH_FORMAT="plain"
ENV HTTP_PORT=8007
ENV USESSE="false"

# Открываем порт
EXPOSE 8007

# Healthcheck - проверяем доступность MCP endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8007/mcp || exit 1

# Запуск приложения
CMD ["python", "main.py"]
