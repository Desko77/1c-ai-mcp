"""Тестирование MCP инструментов через реальные вызовы."""

import asyncio
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, '/app')

from src.mcp_server import check_1c_code, ask_1c_ai, explain_1c_syntax

async def test_tools():
    """Тестирование всех MCP инструментов."""
    
    print("=" * 60)
    print("Тест 1: check_1c_code (syntax)")
    print("=" * 60)
    try:
        result = await check_1c_code("Процедура Тест()\nКонецПроцедуры", "syntax")
        print(f"✓ Успешно: {result[:200]}...")
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    print()
    
    print("=" * 60)
    print("Тест 2: ask_1c_ai")
    print("=" * 60)
    try:
        result = await ask_1c_ai("Что такое процедура в 1С?")
        print(f"✓ Успешно: {result[:200]}...")
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    print()
    
    print("=" * 60)
    print("Тест 3: explain_1c_syntax")
    print("=" * 60)
    try:
        result = await explain_1c_syntax("Процедура")
        print(f"✓ Успешно: {result[:200]}...")
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    print()

if __name__ == "__main__":
    asyncio.run(test_tools())

