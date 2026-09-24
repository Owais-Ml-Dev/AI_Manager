"""Automatic Gemini reasoning policy.

Simple chat and straightforward task CRUD use the minimum reasoning possible.
More complex analysis/planning uses a moderate amount of reasoning.
"""


def get_reasoning_mode(message):
    text = str(message or "").strip().lower()

    if not text:
        return "fast"

    words = text.split()
    score = 0

    if len(words) >= 35:
        score += 1

    if len(words) >= 70:
        score += 1

    complex_phrases = (
        "analyze",
        "compare",
        "pros and cons",
        "tradeoff",
        "trade-off",
        "debug",
        "troubleshoot",
        "root cause",
        "step by step",
        "in detail",
        "detailed plan",
        "strategy",
        "optimize",
        "evaluate",
        "reason about",
        "multiple options",
    )

    if any(phrase in text for phrase in complex_phrases):
        score += 1

    padded = f" {text} "
    action_words = (
        " create ",
        " update ",
        " edit ",
        " complete ",
        " delete ",
        " compare ",
        " analyze ",
        " plan ",
    )

    action_count = sum(
        1
        for action in action_words
        if action in padded
    )

    if action_count >= 2:
        score += 1

    return "balanced" if score >= 2 else "fast"


def gemini_thinking_level(message):
    """Use no thinking for simple requests and medium for complex ones."""
    return (
        "medium"
        if get_reasoning_mode(message) == "balanced"
        else "off"
    )
