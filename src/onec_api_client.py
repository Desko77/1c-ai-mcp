"""
HTTP клиент для работы с API 1С:Напарник.
Оригинальная идея: https://github.com/comol/1c-code-checker
Алгоритмы API заимствованы из: https://github.com/SteelMorgan/spring-mcp-1c-copilot
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class SSEParseResult:
    """Результат парсинга SSE-потока."""
    text: str = ""
    has_tool_calls: bool = False
    has_only_reasoning: bool = False


class ConversationRequest(BaseModel):
    """Запрос на создание новой дискуссии."""
    tool_name: str = "custom"
    skill_name: str = "raw"
    ui_language: str = "russian"
    programming_language: str = ""
    script_language: str = "ru"
    is_chat: bool = True


class MessageRequest(BaseModel):
    """Запрос на отправку сообщения в дискуссию."""
    parent_uuid: Optional[str] = None
    role: str = "user"
    content: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(cls, instruction: str, parent_uuid: Optional[str] = None):
        """Создать запрос с правильным форматом content."""
        # API ожидает content как объект UserContent с полем content, содержащим instruction
        # Формат основан на анализе ошибок API: требуется instruction в content.content
        # ВАЖНО: content должен быть словарем, а не массивом!
        return cls(
            parent_uuid=parent_uuid,
            role="user",
            content={
                "content": {
                    "instruction": instruction
                }
            }
        )


class ConversationSession(BaseModel):
    """Сессия дискуссии."""
    conversation_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    last_used: datetime = Field(default_factory=datetime.now)
    messages_count: int = 0

    def update_usage(self):
        """Обновить время последнего использования."""
        self.last_used = datetime.now()
        self.messages_count += 1


# Регулярка для удаления thinking-тегов
_THINKING_RE = re.compile(r'<think(?:ing)?>.*?</think(?:ing)?>', re.DOTALL)


def _strip_thinking_tags(text: str) -> str:
    """Удалить блоки <thinking>...</thinking> и <think>...</think> из текста."""
    return _THINKING_RE.sub('', text).strip()


class OneCApiClient:
    """Клиент для работы с API 1С:Напарник."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "https://code.1c.ai").rstrip('/')
        self.token = config.get("onec_ai_token", "")
        self.timeout = config.get("timeout", 30)
        self.sessions: Dict[str, ConversationSession] = {}
        self.max_active_sessions = config.get("max_active_sessions", 10)
        self.session_ttl = config.get("session_ttl", 3600)
        self.skill_name = config.get("skill_name", "raw")

        # Формируем Authorization header
        auth_format = config.get("auth_format", "plain")
        if auth_format == "bearer":
            auth_header = f"Bearer {self.token}"
        else:
            auth_header = self.token

        # Создаем HTTP клиент с правильными заголовками
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Accept": "*/*",
                "Accept-Charset": "utf-8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "ru-ru,en-us;q=0.8,en;q=0.7",
                "Authorization": auth_header,
                "Content-Type": "application/json; charset=utf-8",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/chat/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/620.1 (KHTML, like Gecko) JavaFX/22 Safari/620.1",
            }
        )

    async def create_conversation(
        self,
        programming_language: Optional[str] = None,
        script_language: Optional[str] = None,
        skill_name_override: Optional[str] = None
    ) -> str:
        """Создать новую дискуссию."""
        try:
            effective_skill = skill_name_override or self.skill_name

            request_dict = {
                "tool_name": "custom",
                "skill_name": effective_skill,
                "ui_language": "russian",
                "is_chat": True
            }

            if programming_language:
                request_dict["programming_language"] = programming_language
            if script_language:
                request_dict["script_language"] = script_language
            else:
                request_dict["script_language"] = "ru"

            response = await self.client.post(
                f"{self.base_url}/chat_api/v1/conversations/",
                json=request_dict,
                headers={"Session-Id": ""}
            )

            if response.status_code != 200:
                error_text = response.text[:500]
                raise Exception(f"Ошибка создания дискуссии: {response.status_code} - {error_text}")

            conversation_data = response.json()
            conversation_id = conversation_data.get("uuid")

            if not conversation_id:
                raise Exception("Не получен UUID дискуссии из ответа")

            self.sessions[conversation_id] = ConversationSession(
                conversation_id=conversation_id
            )

            logger.info(f"Создана новая дискуссия: {conversation_id} (skill: {effective_skill})")
            return conversation_id

        except httpx.RequestError as e:
            raise Exception(f"Ошибка сети при создании дискуссии: {str(e)}")
        except Exception as e:
            raise Exception(f"Неожиданная ошибка при создании дискуссии: {str(e)}")

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        _is_retry: bool = False
    ) -> str:
        """Отправить сообщение в дискуссию и получить ответ."""
        try:
            if conversation_id not in self.sessions:
                self.sessions[conversation_id] = ConversationSession(
                    conversation_id=conversation_id
                )

            self.sessions[conversation_id].update_usage()

            request_data = MessageRequest.create(message)

            url = f"{self.base_url}/chat_api/v1/conversations/{conversation_id}/messages"

            async with self.client.stream(
                "POST",
                url,
                json=request_data.model_dump(),
                headers={"Accept": "text/event-stream"}
            ) as response:

                if response.status_code != 200:
                    error_text = await response.aread()
                    error_details = error_text.decode('utf-8', errors='ignore')[:500]
                    logger.error(f"Ошибка отправки сообщения {response.status_code}: {error_details}")
                    raise Exception(f"Ошибка отправки сообщения: {response.status_code} - {error_details}")

                parse_result = await self._parse_sse_response(response)

            # Fallback: если получены tool_calls — повторить с skill_name="raw"
            if parse_result.has_tool_calls and not _is_retry:
                logger.warning("Ответ содержит tool_calls, повторяем с skill_name='raw'")
                fallback_conv_id = await self.create_conversation(skill_name_override="raw")
                return await self.send_message(fallback_conv_id, message, _is_retry=True)

            if parse_result.has_tool_calls and _is_retry:
                return "Ошибка: API вернул tool_calls повторно после fallback на skill 'raw'"

            if parse_result.has_only_reasoning:
                return "Ошибка: API вернул только reasoning без итогового ответа"

            # Удаляем thinking-теги из ответа
            clean_text = _strip_thinking_tags(parse_result.text)

            logger.info(f"Получен ответ для дискуссии {conversation_id}")
            return clean_text

        except httpx.RequestError as e:
            raise Exception(f"Ошибка сети при отправке сообщения: {str(e)}")
        except Exception as e:
            raise Exception(f"Неожиданная ошибка при отправке сообщения: {str(e)}")

    async def _parse_sse_response(self, response: httpx.Response) -> SSEParseResult:
        """Парсинг Server-Sent Events ответа с поддержкой всех форматов."""
        result = SSEParseResult()
        accumulated_delta = ""
        has_reasoning = False
        has_content_text = False

        response.encoding = 'utf-8'

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue

            data_str = line[6:]  # Убираем "data: "
            logger.debug(f"SSE raw: {data_str[:300]}")

            # Маркер завершения — не JSON, пропускаем
            if data_str.strip() == "[DONE]":
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                logger.debug(f"SSE non-JSON: {data_str[:200]}")
                continue

            if not isinstance(data, dict):
                continue

            # Отслеживание tool_calls
            if "tool_calls" in data:
                result.has_tool_calls = True
                logger.debug("SSE chunk содержит tool_calls")

            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    delta = choice.get("delta", {})
                    if isinstance(delta, dict):
                        if "tool_calls" in delta:
                            result.has_tool_calls = True
                        if "content" in delta and delta["content"]:
                            accumulated_delta += delta["content"]
                        if delta.get("reasoning") or delta.get("reasoning_content"):
                            has_reasoning = True
                            logger.debug("SSE chunk содержит reasoning")

                    if choice.get("finish_reason") == "stop":
                        break

            # Отслеживание reasoning на верхнем уровне
            if data.get("reasoning") or data.get("reasoning_content"):
                has_reasoning = True
                logger.debug("SSE chunk содержит reasoning (top-level)")

            # Формат Legacy: content_delta (инкрементальный)
            content_delta = data.get("content_delta")
            if content_delta:
                if isinstance(content_delta, str):
                    accumulated_delta += content_delta
                elif isinstance(content_delta, dict):
                    delta_text = content_delta.get("content", "")
                    if delta_text:
                        accumulated_delta += delta_text

            # Формат Completed: content.text или content.content (финальный — перезаписывает)
            content = data.get("content", {})
            if isinstance(content, dict):
                text = content.get("text", "") or content.get("content", "")
                if text:
                    has_content_text = True
                    result.text = text
                # Отслеживание tool_calls внутри content
                if content.get("tool_calls"):
                    result.has_tool_calls = True
                # Reasoning внутри content
                if content.get("reasoning_content"):
                    has_reasoning = True
                    logger.debug("SSE chunk содержит reasoning_content в content")

            # Маркер завершения — только для ответа ассистента, не для echo юзера
            if data.get("finished", False) and data.get("role") != "user":
                break

        # Приоритет: финальный content.text > накопленные дельты
        if has_content_text and result.text:
            pass  # уже установлен
        elif accumulated_delta:
            result.text = accumulated_delta

        result.text = result.text.strip()

        # Определяем has_only_reasoning
        if has_reasoning and not result.text:
            result.has_only_reasoning = True

        return result

    async def get_or_create_session(
        self,
        create_new: bool = False,
        programming_language: Optional[str] = None
    ) -> str:
        """Получить существующую сессию или создать новую."""

        await self._cleanup_old_sessions()

        if create_new or not self.sessions:
            return await self.create_conversation(programming_language)

        if len(self.sessions) >= self.max_active_sessions:
            oldest_session_id = min(
                self.sessions.keys(),
                key=lambda k: self.sessions[k].last_used
            )
            del self.sessions[oldest_session_id]
            logger.info(f"Удалена старая сессия: {oldest_session_id}")

        recent_session_id = max(
            self.sessions.keys(),
            key=lambda k: self.sessions[k].last_used
        )

        return recent_session_id

    async def _cleanup_old_sessions(self):
        """Очистка устаревших сессий."""
        current_time = datetime.now()
        ttl_delta = timedelta(seconds=self.session_ttl)

        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if current_time - session.last_used > ttl_delta
        ]

        for session_id in expired_sessions:
            del self.sessions[session_id]
            logger.info(f"Удалена устаревшая сессия: {session_id}")

    async def close(self):
        """Закрыть HTTP клиент."""
        await self.client.aclose()
