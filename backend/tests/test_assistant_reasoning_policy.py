from src.modules.assistant.providers.reasoning_policy import (
    gemini_thinking_level,
    get_reasoning_mode,
)


def test_simple_chat_uses_minimum_reasoning():
    assert get_reasoning_mode("Hi") == "fast"
    assert gemini_thinking_level("Hi") == "off"


def test_simple_task_command_uses_minimum_reasoning():
    message = "Create a gym task every weekday at 7 AM for 30 days"
    assert get_reasoning_mode(message) == "fast"
    assert gemini_thinking_level(message) == "off"


def test_complex_request_uses_medium_reasoning():
    message = (
        "Analyze my productivity pattern in detail, compare multiple options, "
        "explain the tradeoffs, and create a detailed strategy for improving "
        "my schedule over the next month while considering several changes."
    )
    assert get_reasoning_mode(message) == "balanced"
    assert gemini_thinking_level(message) == "medium"
