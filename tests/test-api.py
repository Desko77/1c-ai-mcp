"""Тестовый скрипт для проверки API 1C.ai из контейнера."""

import asyncio
import json
import os
import httpx

async def test_api():
    """Тестирование API 1C.ai."""
    
    token = os.environ.get("ONEC_AI_TOKEN", "REDACTED_ONEC_AI_TOKEN")
    base_url = "https://code.1c.ai"
    
    print(f"Тестирование API: {base_url}")
    print(f"Токен: {token[:20]}...")
    print()
    
    # Создаем клиент
    client = httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Accept": "*/*",
            "Accept-Charset": "utf-8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "ru-ru,en-us;q=0.8,en;q=0.7",
            "Authorization": token,
            "Content-Type": "application/json; charset=utf-8",
            "Origin": base_url,
            "Referer": f"{base_url}/chat/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/620.1 (KHTML, like Gecko) JavaFX/22 Safari/620.1",
        }
    )
    
    try:
        # Тест 1: Создание дискуссии
        print("=" * 60)
        print("Тест 1: Создание дискуссии")
        print("=" * 60)
        
        request_data = {
            "tool_name": "custom",
            "ui_language": "russian",
            "programming_language": "",
            "script_language": ""
        }
        
        print(f"URL: {base_url}/chat_api/v1/conversations/")
        print(f"Данные: {json.dumps(request_data, ensure_ascii=False, indent=2)}")
        print()
        
        response = await client.post(
            f"{base_url}/chat_api/v1/conversations/",
            json=request_data,
            headers={"Session-Id": ""}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            print("✓ Успешно!")
            print(f"Response: {response.text}")
        else:
            print("✗ Ошибка!")
            print(f"Response: {response.text}")
            print()
            
            # Попробуем другие варианты запроса
            print("Пробуем альтернативные варианты...")
            print()
            
            # Вариант 2: Без пустых строк
            request_data2 = {
                "tool_name": "custom",
                "ui_language": "russian"
            }
            print("Вариант 2 (без пустых полей):")
            response2 = await client.post(
                f"{base_url}/chat_api/v1/conversations/",
                json=request_data2,
                headers={"Session-Id": ""}
            )
            print(f"Status: {response2.status_code}, Response: {response2.text[:200]}")
            print()
            
            # Вариант 3: С другими значениями
            request_data3 = {
                "tool_name": "custom",
                "ui_language": "russian",
                "programming_language": "1c",
                "script_language": "1c"
            }
            print("Вариант 3 (с языками):")
            response3 = await client.post(
                f"{base_url}/chat_api/v1/conversations/",
                json=request_data3,
                headers={"Session-Id": ""}
            )
            print(f"Status: {response3.status_code}, Response: {response3.text[:200]}")
            
    except Exception as e:
        print(f"Исключение: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_api())

