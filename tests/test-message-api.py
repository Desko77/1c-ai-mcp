"""Тест формата запроса для отправки сообщения."""

import asyncio
import json
import os
import httpx

async def test_message_api():
    """Тестирование API отправки сообщения."""
    
    token = os.environ.get("ONEC_AI_TOKEN", "REDACTED_ONEC_AI_TOKEN")
    base_url = "https://code.1c.ai"
    conversation_id = "9b857f9e-dfa1-422c-b2c7-64aa71ee93fa"  # Используем созданную ранее
    
    client = httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Accept": "text/event-stream",
            "Authorization": token,
            "Content-Type": "application/json; charset=utf-8",
            "Origin": base_url,
            "Referer": f"{base_url}/chat/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/620.1",
        }
    )
    
    try:
        # Вариант 1: Текущий формат
        print("Вариант 1: Текущий формат (tool_content)")
        request_data1 = {
            "parent_uuid": None,
            "tool_content": {
                "instruction": "Тест"
            }
        }
        
        url = f"{base_url}/chat_api/v1/conversations/{conversation_id}/messages"
        print(f"URL: {url}")
        print(f"Data: {json.dumps(request_data1, ensure_ascii=False, indent=2)}")
        
        async with client.stream("POST", url, json=request_data1) as response:
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                text = await response.aread()
                print(f"Error: {text.decode('utf-8')[:500]}")
            else:
                print("✓ Успешно!")
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        print(f"Data: {line[:100]}...")
                        break
        
        print()
        
        # Вариант 2: Без parent_uuid
        print("Вариант 2: Без parent_uuid")
        request_data2 = {
            "tool_content": {
                "instruction": "Тест"
            }
        }
        
        async with client.stream("POST", url, json=request_data2) as response:
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                text = await response.aread()
                print(f"Error: {text.decode('utf-8')[:500]}")
            else:
                print("✓ Успешно!")
        
        print()
        
        # Вариант 3: С message вместо instruction
        print("Вариант 3: С message")
        request_data3 = {
            "message": "Тест"
        }
        
        async with client.stream("POST", url, json=request_data3) as response:
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                text = await response.aread()
                print(f"Error: {text.decode('utf-8')[:500]}")
            else:
                print("✓ Успешно!")
        
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_message_api())

