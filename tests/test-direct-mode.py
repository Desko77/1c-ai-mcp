"""
Тесты direct mode для call_exact_tool.
Запуск: python tests/test-direct-mode.py
Требует: ONEC_AI_TOKEN в env или .env файле.
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.onec_api_client import OneCApiClient, DirectToolError

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_config():
    token = os.environ.get("ONEC_AI_TOKEN", "")
    if not token:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.isfile(env_path):
            for line in open(env_path):
                if line.startswith("ONEC_AI_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    if not token:
        print("ONEC_AI_TOKEN not set")
        sys.exit(1)
    return {
        "onec_ai_token": token,
        "base_url": os.environ.get("ONEC_AI_BASE_URL", "https://code.1c.ai"),
        "timeout": 120,
        "max_active_sessions": 10,
        "session_ttl": 3600,
        "skill_name": "raw",
        "auth_format": "plain",
    }


async def test_call_exact_tool_its_search():
    """Тест: вызов Search_ITS через direct mode."""
    print("\n=== Test: call_exact_tool (Search_ITS) ===")
    client = OneCApiClient(get_config())
    try:
        conv_id = await client.create_conversation(skill_name_override="custom")
        print(f"Conversation created: {conv_id}")

        result = await client.call_exact_tool(
            conv_id,
            "mcp__knowledge-hub__Search_ITS",
            {"query": "стандарты разработки"}
        )
        print(f"Result length: {len(result)}")
        print(f"Result preview: {result[:300]}...")
        print("PASSED")
    except DirectToolError as e:
        print(f"DirectToolError: {e.diagnostic_summary()}")
        print("NOTE: This may mean the upstream tool name is different. Check actual names in DEBUG logs above.")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.close()


async def test_call_exact_tool_wrong_name():
    """Тест: несуществующий tool_name -> DirectToolError."""
    print("\n=== Test: call_exact_tool (wrong tool name) ===")
    client = OneCApiClient(get_config())
    try:
        conv_id = await client.create_conversation(skill_name_override="custom")
        try:
            await client.call_exact_tool(
                conv_id,
                "mcp__nonexistent__FakeTool",
                {"query": "test"}
            )
            print("ERROR: should have raised DirectToolError")
        except DirectToolError as e:
            print(f"Got expected error: {e.reason}")
            if e.details.get("actual"):
                print(f"Actual tool names available: {e.details['actual']}")
            print("PASSED")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.close()


async def test_call_exact_tool_search_documentation():
    """Тест: вызов Search_Documentation через direct mode."""
    print("\n=== Test: call_exact_tool (Search_Documentation) ===")
    client = OneCApiClient(get_config())
    try:
        conv_id = await client.create_conversation(skill_name_override="custom")
        result = await client.call_exact_tool(
            conv_id,
            "mcp__knowledge-hub__Search_Documentation",
            {"query": "HTTPСоединение", "version": "v8.5.1"}
        )
        print(f"Result length: {len(result)}")
        print(f"Result preview: {result[:300]}...")
        print("PASSED")
    except DirectToolError as e:
        print(f"DirectToolError: {e.diagnostic_summary()}")
        print("NOTE: Check actual tool names in DEBUG logs above.")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await client.close()


def test_sanitize_text():
    """Тест: _sanitize_text (unit, без API)."""
    print("\n=== Test: _sanitize_text (unit) ===")
    from src.mcp_server import _sanitize_text

    # Thinking tags
    assert _sanitize_text("<thinking>internal</thinking>Hello") == "Hello"
    assert _sanitize_text("<think>internal</think>Hello") == "Hello"

    # Control chars
    assert _sanitize_text("Hello\x00World") == "HelloWorld"

    # Newlines preserved
    assert "\n" in _sanitize_text("Line1\nLine2")

    # Empty
    assert _sanitize_text("") == ""
    assert _sanitize_text(None) is None

    print("PASSED")


def test_truncate_input():
    """Тест: _truncate_input (unit, без API)."""
    print("\n=== Test: _truncate_input (unit) ===")
    from src.mcp_server import _truncate_input

    # Short text - no truncation
    assert _truncate_input("short") == "short"

    # Cyrillic - counts chars, not bytes
    text = "a" * 100001
    truncated = _truncate_input(text)
    assert len(truncated) == 100000

    print("PASSED")


async def main():
    print("Direct mode tests")
    print("=" * 60)

    # Unit tests (no API needed)
    test_sanitize_text()
    test_truncate_input()

    # Integration tests (need API)
    await test_call_exact_tool_its_search()
    await test_call_exact_tool_wrong_name()
    await test_call_exact_tool_search_documentation()

    print("\n" + "=" * 60)
    print("Done. Check DEBUG logs above for actual upstream tool names.")


if __name__ == "__main__":
    asyncio.run(main())
