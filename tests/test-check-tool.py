"""Тестовый скрипт для проверки инструмента check_1c_code."""

import asyncio
import sys
import os

sys.path.insert(0, '/app')

from src.onec_api_client import OneCApiClient, MessageRequest
import json

async def test_check_tool():
    """Тестирование инструмента check_1c_code."""
    
    token = os.environ.get("ONEC_AI_TOKEN", "REDACTED_ONEC_AI_TOKEN")
    
    config = {
        "onec_ai_token": token,
        "base_url": "https://code.1c.ai",
        "timeout": 30,
    }
    
    client = OneCApiClient(config)
    
    try:
        print("=" * 60)
        print("Тест 1: Создание дискуссии")
        print("=" * 60)
        
        conversation_id = await client.create_conversation()
        print(f"✓ Дискуссия создана: {conversation_id}")
        print()
        
        print("=" * 60)
        print("Тест 2: Проверка формата MessageRequest")
        print("=" * 60)
        
        msg = MessageRequest.create("Тест")
        print("Формат запроса:")
        print(json.dumps(msg.model_dump(), ensure_ascii=False, indent=2))
        print()
        
        print("=" * 60)
        print("Тест 3: Отправка сообщения")
        print("=" * 60)
        
        test_code = "Процедура Тест()\nКонецПроцедуры"
        question = f"Проверь этот код 1С на синтаксические ошибки:\n\n```1c\n{test_code}\n```"
        
        answer = await client.send_message(conversation_id, question)
        print(f"✓ Получен ответ (длина: {len(answer)} символов)")
        print(f"Ответ: {answer[:200]}...")
        print()
        
        print("=" * 60)
        print("✓ Все тесты пройдены успешно!")
        print("=" * 60)
        
        await client.close()
        
    except Exception as e:
        print(f"✗ Ошибка: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_check_tool())

