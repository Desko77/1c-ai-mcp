"""Тестовый скрипт для проверки API 1C.ai с использованием реальной модели."""

import asyncio
import sys
import os

# Добавляем путь к модулю
sys.path.insert(0, '/app')

from MCP_1copilot.api_client import OneCApiClient
from MCP_1copilot.config import get_config

async def test_api():
    """Тестирование API через реальный клиент."""
    
    try:
        print("Инициализация конфигурации...")
        config = get_config()
        print(f"✓ Конфигурация загружена")
        print(f"  Base URL: {config.base_url}")
        print(f"  Token: {config.onec_ai_token[:20]}...")
        print()
        
        print("Создание API клиента...")
        client = OneCApiClient(config)
        print("✓ Клиент создан")
        print()
        
        print("=" * 60)
        print("Тест: Создание дискуссии")
        print("=" * 60)
        
        conversation_id = await client.create_conversation()
        print(f"✓ Дискуссия создана: {conversation_id}")
        print()
        
        print("=" * 60)
        print("Тест: Отправка сообщения")
        print("=" * 60)
        
        test_message = "Привет! Это тестовое сообщение."
        answer = await client.send_message(conversation_id, test_message)
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
    asyncio.run(test_api())

