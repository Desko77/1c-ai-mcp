"""Тестирование различных форматов content для API 1C.ai."""

import asyncio
import json
import os
import httpx

async def test_formats():
    """Тестирование различных форматов content."""
    
    token = os.environ.get("ONEC_AI_TOKEN", "REDACTED_ONEC_AI_TOKEN")
    base_url = "https://code.1c.ai"
    conversation_id = None
    
    client = httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Accept": "*/*",
            "Authorization": token,
            "Content-Type": "application/json; charset=utf-8",
            "Origin": base_url,
            "Referer": f"{base_url}/chat/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/620.1",
        }
    )
    
    try:
        # Создаем дискуссию
        conv_response = await client.post(
            f"{base_url}/chat_api/v1/conversations/",
            json={
                "tool_name": "custom",
                "skill_name": "custom",
                "ui_language": "russian",
                "script_language": "ru",
                "is_chat": True
            },
            headers={"Session-Id": ""}
        )
        
        if conv_response.status_code == 200:
            conversation_id = conv_response.json().get("uuid")
            print(f"✓ Дискуссия создана: {conversation_id}\n")
        else:
            print(f"✗ Ошибка создания дискуссии: {conv_response.status_code}")
            print(conv_response.text)
            return
        
        # Тестируем различные форматы
        formats = [
            {
                "name": "Формат 1: content.content.instruction",
                "data": {
                    "parent_uuid": None,
                    "role": "user",
                    "content": {
                        "content": {
                            "instruction": "Тест"
                        }
                    }
                }
            },
            {
                "name": "Формат 2: content как массив ToolContent",
                "data": {
                    "parent_uuid": None,
                    "role": "user",
                    "content": [
                        {
                            "type": "tool",
                            "content": "Тест",
                            "tool_call_id": "test-123"
                        }
                    ]
                }
            },
            {
                "name": "Формат 3: content.content.text",
                "data": {
                    "parent_uuid": None,
                    "role": "user",
                    "content": {
                        "content": {
                            "text": "Тест"
                        }
                    }
                }
            },
            {
                "name": "Формат 4: content как строка",
                "data": {
                    "parent_uuid": None,
                    "role": "user",
                    "content": "Тест"
                }
            }
        ]
        
        url = f"{base_url}/chat_api/v1/conversations/{conversation_id}/messages"
        
        for fmt in formats:
            print("=" * 60)
            print(fmt["name"])
            print("=" * 60)
            print(f"Данные: {json.dumps(fmt['data'], ensure_ascii=False, indent=2)}")
            
            async with client.stream("POST", url, json=fmt["data"], headers={"Accept": "text/event-stream"}) as response:
                if response.status_code == 200:
                    print(f"✓ Успешно! Status: {response.status_code}")
                    # Читаем первый чанк
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            print(f"Получен ответ: {line[:100]}...")
                            break
                    break
                else:
                    error_text = await response.aread()
                    error_details = error_text.decode('utf-8', errors='ignore')[:300]
                    print(f"✗ Ошибка {response.status_code}: {error_details}")
            print()
        
    except Exception as e:
        print(f"Исключение: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_formats())

