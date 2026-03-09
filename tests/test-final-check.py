"""Финальный тест всех инструментов MCP сервера."""

import asyncio
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, '/app')

from src.onec_api_client import OneCApiClient

async def test_all_tools():
    """Тестирование всех инструментов."""
    
    config = {
        "onec_ai_token": os.environ.get("ONEC_AI_TOKEN", ""),
        "base_url": os.environ.get("ONEC_AI_BASE_URL", "https://code.1c.ai"),
        "timeout": 30,
    }
    
    if not config["onec_ai_token"]:
        print("✗ ONEC_AI_TOKEN не установлен")
        return
    
    client = OneCApiClient(config)
    
    try:
        print("=" * 60)
        print("Тест 1: Создание дискуссии")
        print("=" * 60)
        conv_id = await client.create_conversation()
        print(f"✓ Дискуссия создана: {conv_id}\n")
        
        print("=" * 60)
        print("Тест 2: Отправка простого сообщения")
        print("=" * 60)
        response = await client.send_message(conv_id, "Привет, это тест")
        print(f"✓ Получен ответ (длина: {len(response)} символов)")
        if response:
            print(f"Ответ: {response[:200]}...")
        print()
        
        print("=" * 60)
        print("Тест 3: Проверка кода 1С")
        print("=" * 60)
        code = """
Процедура Тест()
    Перем Переменная;
    Переменная = 10;
КонецПроцедуры
"""
        check_prompt = f"Проверь этот код 1С на синтаксические ошибки:\n\n{code}"
        response = await client.send_message(conv_id, check_prompt)
        print(f"✓ Получен ответ (длина: {len(response)} символов)")
        if response:
            print(f"Ответ: {response[:300]}...")
        print()
        
        print("=" * 60)
        print("✓ Все тесты пройдены успешно!")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_all_tools())

