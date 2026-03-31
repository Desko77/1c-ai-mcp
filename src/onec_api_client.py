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
    tool_calls_data: Optional[List[Dict[str, Any]]] = None
    assistant_uuid: Optional[str] = None


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


class DirectToolError(Exception):
    """Ошибка при прямом вызове upstream-инструмента."""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.tool_name = tool_name
        self.reason = reason
        self.details = details or {}
        super().__init__(f"Direct call to '{tool_name}' failed: {reason}")

    def diagnostic_summary(self) -> str:
        parts = [f"tool={self.tool_name}", f"reason={self.reason}"]
        if self.details:
            parts.append(f"details={self.details}")
        return " | ".join(parts)


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
        skill_name_override: Optional[str] = None,
        tool_name: Optional[str] = None
    ) -> str:
        """Создать новую дискуссию."""
        try:
            effective_skill = skill_name_override or self.skill_name
            effective_tool = tool_name or "custom"

            request_dict = {
                "tool_name": effective_tool,
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

            # Захват assistant UUID
            if data.get("role") == "assistant" and data.get("uuid"):
                result.assistant_uuid = data["uuid"]

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
                tc = content.get("tool_calls")
                if tc:
                    result.has_tool_calls = True
                    result.tool_calls_data = tc
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

    def _parse_sse_text(self, text: str) -> SSEParseResult:
        """Парсинг SSE из текстовой строки (не-стриминговый ответ)."""
        result = SSEParseResult()
        accumulated_delta = ""
        has_content_text = False

        for line in text.split("\n"):
            if not line.startswith("data: "):
                continue

            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            # Захват assistant UUID
            if data.get("role") == "assistant" and data.get("uuid"):
                result.assistant_uuid = data["uuid"]

            # Top-level tool_calls (аналогично _parse_sse_response)
            if "tool_calls" in data and not isinstance(data.get("content"), dict):
                result.has_tool_calls = True
                if isinstance(data["tool_calls"], list):
                    result.tool_calls_data = data["tool_calls"]

            # Формат content_delta
            content_delta = data.get("content_delta")
            if content_delta:
                if isinstance(content_delta, str):
                    accumulated_delta += content_delta
                elif isinstance(content_delta, dict):
                    delta_text = content_delta.get("content", "")
                    if delta_text:
                        accumulated_delta += delta_text

            # Формат content (финальный)
            content = data.get("content", {})
            if isinstance(content, dict):
                text_val = content.get("text", "") or content.get("content", "")
                if text_val:
                    has_content_text = True
                    result.text = text_val
                tc = content.get("tool_calls")
                if tc:
                    result.has_tool_calls = True
                    result.tool_calls_data = tc

        if has_content_text and result.text:
            pass
        elif accumulated_delta:
            result.text = accumulated_delta

        result.text = result.text.strip()
        return result

    async def send_message_with_tool_chain(
        self,
        conversation_id: str,
        message: str,
        max_tool_rounds: int = 10
    ) -> str:
        """Отправить сообщение и следовать цепочке tool_calls до текстового ответа.

        Используется для инструментов документации (ИТС, справка платформы).
        API 1С:Напарник с skill_name='custom' возвращает tool_calls для серверных
        инструментов (Search_ITS, Fetch_ITS и т.д.). Клиент подтверждает каждый
        вызов (status='accepted'), сервер выполняет поиск, модель формирует ответ.
        """
        url = f"{self.base_url}/chat_api/v1/conversations/{conversation_id}/messages"

        # Шаг 1: отправить пользовательское сообщение
        request_data = MessageRequest.create(message)
        response = await self.client.post(
            url,
            json=request_data.model_dump(),
            headers={"Accept": "text/event-stream"}
        )
        if response.status_code != 200:
            raise Exception(f"Ошибка отправки: {response.status_code} - {response.text[:500]}")

        result = self._parse_sse_text(response.text)

        # Шаг 2: следовать цепочке tool_calls
        for i in range(max_tool_rounds):
            if not result.tool_calls_data or not result.assistant_uuid:
                break

            call_id = result.tool_calls_data[0].get("id")
            fn = result.tool_calls_data[0].get("function", {})
            logger.info(f"Tool chain step {i+1}: {fn.get('name')}({fn.get('arguments', '')})")

            if not call_id:
                logger.warning("tool_call без id, прерываем цепочку")
                break

            # Подтвердить вызов серверного инструмента
            ack_payload = {
                "parent_uuid": result.assistant_uuid,
                "role": "tool",
                "content": [{
                    "tool_call_id": call_id,
                    "status": "accepted",
                    "content": None
                }]
            }

            response = await self.client.post(
                url,
                json=ack_payload,
                headers={"Accept": "text/event-stream"}
            )
            if response.status_code != 200:
                logger.error(f"Ошибка ACK tool_call: {response.status_code} - {response.text[:300]}")
                break

            result = self._parse_sse_text(response.text)

        clean_text = _strip_thinking_tags(result.text)
        if not clean_text:
            return "Ошибка: API не вернул текстовый ответ после цепочки tool_calls"
        return clean_text

    async def call_exact_tool(
        self,
        conversation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """Вызвать конкретный upstream-инструмент напрямую (direct mode).

        Отправляет сообщение, ожидает tool_calls, матчит по имени, ACK-ает,
        возвращает текстовый результат. При сбое - DirectToolError.
        """
        url = f"{self.base_url}/chat_api/v1/conversations/{conversation_id}/messages"

        # Шаг 1: отправить сообщение с подсказкой вызвать конкретный инструмент
        args_json = json.dumps(arguments, ensure_ascii=False)
        instruction = (
            f"Call tool {tool_name} with arguments: {args_json}\n"
            f"Use ONLY this tool. Do not search or reason, just call the tool."
        )
        request_data = MessageRequest.create(instruction)

        response = await self.client.post(
            url,
            json=request_data.model_dump(),
            headers={"Accept": "text/event-stream"}
        )
        if response.status_code != 200:
            raise DirectToolError(
                tool_name, f"HTTP {response.status_code}",
                {"body": response.text[:500]}
            )

        result = self._parse_sse_text(response.text)

        # Шаг 2: найти ожидаемый tool_call по имени
        if not result.tool_calls_data:
            raise DirectToolError(
                tool_name, "no_tool_calls",
                {"text": result.text[:200]}
            )

        matched_call = None
        for tc in result.tool_calls_data:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            logger.debug(f"Direct mode: tool_call found: {fn_name}")
            if fn_name == tool_name:
                matched_call = tc
                break

        if not matched_call:
            actual_names = [
                tc.get("function", {}).get("name", "?")
                for tc in result.tool_calls_data
            ]
            raise DirectToolError(
                tool_name, "tool_name_mismatch",
                {"expected": tool_name, "actual": actual_names}
            )

        call_id = matched_call.get("id")
        if not call_id or not result.assistant_uuid:
            raise DirectToolError(tool_name, "missing_call_id_or_uuid")

        logger.debug(
            f"Direct tool call matched: tool={tool_name}, "
            f"call_id={call_id}, conversation={conversation_id}"
        )

        # Шаг 3: ACK tool_call
        ack_payload = {
            "parent_uuid": result.assistant_uuid,
            "role": "tool",
            "content": [{
                "tool_call_id": call_id,
                "status": "accepted",
                "content": None
            }]
        }

        response = await self.client.post(
            url,
            json=ack_payload,
            headers={"Accept": "text/event-stream"}
        )
        if response.status_code != 200:
            raise DirectToolError(
                tool_name, f"ACK HTTP {response.status_code}",
                {"body": response.text[:300]}
            )

        result = self._parse_sse_text(response.text)

        # Шаг 4: следовать дальнейшим tool_calls (цепочка)
        for i in range(9):
            if not result.tool_calls_data or not result.assistant_uuid:
                break

            next_call = result.tool_calls_data[0]
            next_id = next_call.get("id")
            if not next_id:
                break

            fn = next_call.get("function", {})
            logger.debug(f"Direct mode chain step {i+1}: {fn.get('name')}")

            ack_payload = {
                "parent_uuid": result.assistant_uuid,
                "role": "tool",
                "content": [{
                    "tool_call_id": next_id,
                    "status": "accepted",
                    "content": None
                }]
            }

            response = await self.client.post(
                url,
                json=ack_payload,
                headers={"Accept": "text/event-stream"}
            )
            if response.status_code != 200:
                logger.warning(
                    f"Direct mode chain ACK failed: step={i+1}, "
                    f"status={response.status_code}"
                )
                break

            result = self._parse_sse_text(response.text)

        # Шаг 5: извлечь текст
        final_text = _strip_thinking_tags(result.text)
        if not final_text:
            raise DirectToolError(tool_name, "empty_response_after_tool_chain")

        return final_text

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
