"""
Small JSON helpers for LLM output.

LLMs occasionally wrap JSON in Markdown fences or add a short prefix. The
task-command layer extracts the first valid JSON object and then validates it
strictly before anything can touch the task services.
"""

import json


def extract_first_json_object(text):
    """
    Extract the first valid JSON object from model output.

    Raises:
        ValueError: when no valid JSON object can be found.
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Model response is empty.")

    cleaned = text.strip()

    # Common Markdown wrapper:
    #
    # ```json
    # {...}
    # ```
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    decoder = json.JSONDecoder()

    # Try the entire response first.
    try:
        value = json.loads(cleaned)

        if isinstance(value, dict):
            return value

    except json.JSONDecodeError:
        pass

    # Otherwise scan from each opening brace until raw_decode succeeds.
    for index, character in enumerate(cleaned):
        if character != "{":
            continue

        try:
            value, _ = decoder.raw_decode(
                cleaned[index:]
            )

        except json.JSONDecodeError:
            continue

        if isinstance(value, dict):
            return value

    raise ValueError(
        "No valid JSON object was found in the model response."
    )
