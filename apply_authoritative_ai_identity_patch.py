from pathlib import Path
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one matching block in {path}, found {count}. "
            "The file may differ from the reviewed 2026-09-29 version."
        )
    write(path, text.replace(old, new, 1))


def backup(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".before_identity_fix.bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python apply_authoritative_ai_identity_patch.py <backend_dir> <frontend_dir>"
        )

    backend = Path(sys.argv[1]).resolve()
    frontend = Path(sys.argv[2]).resolve()

    service = backend / "src/modules/assistant/service.py"
    prompt = backend / "src/modules/assistant/prompts/chat_prompt.py"
    screen = frontend / "lib/features/assistant/presentation/assistant_screen.dart"
    test_file = backend / "tests/test_assistant_identity.py"

    for path in (service, prompt, screen):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")
        backup(path)

    # ---------------------------------------------------------
    # 1. Backend: authoritative runtime identity response.
    # ---------------------------------------------------------
    replace_once(
        service,
        '"""Multi-provider assistant service.\n\nCloud models interpret chat/task language. Draft validation, confirmation,\nexecution and persistence remain deterministic backend concerns.\n"""\n\n',
        '"""Multi-provider assistant service.\n\nCloud models interpret chat/task language. Draft validation, confirmation,\nexecution and persistence remain deterministic backend concerns.\n"""\n\nimport re\n\n',
    )

    replace_once(
        service,
        'from src.modules.assistant.providers.provider_router import (\n    chat_with_fallback,\n    provider_health,\n)\n\n\n',
        'from src.modules.assistant.providers.provider_registry import get_provider_spec\nfrom src.modules.assistant.providers.provider_router import (\n    chat_with_fallback,\n    provider_health,\n)\n\n\n_RUNTIME_IDENTITY_PATTERNS = (\n    re.compile(\n        r"^(?:what|which)\\s+(?:ai|ai\\s+model|model|provider)"\n        r"(?:\\s+(?:are|is)\\s+(?:you|this))?(?:\\s+using)?$",\n        re.IGNORECASE,\n    ),\n    re.compile(\n        r"^(?:what|which)\\s+(?:ai|ai\\s+model|model|provider)"\n        r"\\s+(?:do|does)\\s+(?:you|this)\\s+use$",\n        re.IGNORECASE,\n    ),\n    re.compile(\n        r"^(?:what|which)\\s+(?:ai|model|provider)"\n        r"\\s+(?:is\\s+)?(?:running|active|answering|being\\s+used)$",\n        re.IGNORECASE,\n    ),\n    re.compile(\n        r"^(?:are\\s+you|is\\s+this)\\s+(?:using\\s+)?"\n        r"(?:gemini|groq|cloudflare|openrouter|cerebras|mistral|nvidia)"\n        r"(?:\\s+ai)?$",\n        re.IGNORECASE,\n    ),\n)\n\n\ndef _normalize_identity_question(message):\n    text = str(message or "").strip().lower()\n    text = re.sub(r"[^a-z0-9@./_-]+", " ", text)\n    return " ".join(text.split())\n\n\ndef _is_runtime_identity_question(message):\n    text = _normalize_identity_question(message)\n    if not text:\n        return False\n\n    if text in {\n        "which ai",\n        "what ai",\n        "which model",\n        "what model",\n        "which provider",\n        "what provider",\n        "which ai is this",\n        "what ai is this",\n        "which model is this",\n        "what model is this",\n        "which provider is this",\n        "what provider is this",\n    }:\n        return True\n\n    return any(\n        pattern.fullmatch(text)\n        for pattern in _RUNTIME_IDENTITY_PATTERNS\n    )\n\n\ndef _provider_label(provider_name):\n    try:\n        return get_provider_spec(provider_name).label\n    except (TypeError, ValueError):\n        value = str(provider_name or "").strip()\n        return value or "AI provider"\n\n\ndef _authoritative_identity_reply(routed):\n    provider_name = str(routed.get("provider") or "").strip()\n    provider_label = _provider_label(provider_name)\n    model = str(routed.get("model") or "").strip() or "Unknown"\n    fallback_used = bool(routed.get("fallback_used"))\n\n    lines = [\n        "You are currently using:",\n        f"Provider: {provider_label}",\n        f"Model: {model}",\n        f"Fallback: {\'Yes\' if fallback_used else \'No\'}",\n    ]\n\n    attempted = routed.get("attempted_providers") or []\n    if fallback_used and isinstance(attempted, (list, tuple)):\n        attempted_labels = [\n            _provider_label(name)\n            for name in attempted\n            if str(name or "").strip()\n        ]\n        if len(attempted_labels) > 1:\n            lines.append(\n                "Route: " + " -> ".join(attempted_labels)\n            )\n\n    return "\\n".join(lines)\n\n\n',
    )

    replace_once(
        service,
        'def send_chat(message, api_key=None, credentials=None):\n    routed = chat_with_fallback(\n        message=message,\n        system_prompt=CHAT_SYSTEM_PROMPT,\n        credentials=credentials,\n        api_key=api_key,\n    )\n    return {\n        "provider": routed["provider"],\n        "type": routed["type"],\n        "model": routed["model"],\n        "reply": routed["result"],\n        "fallback_used": routed["fallback_used"],\n        "attempted_providers": routed["attempted_providers"],\n    }\n',
        'def send_chat(message, api_key=None, credentials=None):\n    routed = chat_with_fallback(\n        message=message,\n        system_prompt=CHAT_SYSTEM_PROMPT,\n        credentials=credentials,\n        api_key=api_key,\n    )\n\n    reply = routed["result"]\n\n    # Provider/model identity is runtime routing metadata, not something\n    # the language model can reliably self-report. The request still goes\n    # through the normal router first so fallback/provider/model reflect\n    # the provider that actually handled this request.\n    if _is_runtime_identity_question(message):\n        reply = _authoritative_identity_reply(routed)\n\n    return {\n        "provider": routed["provider"],\n        "type": routed["type"],\n        "model": routed["model"],\n        "reply": reply,\n        "fallback_used": routed["fallback_used"],\n        "attempted_providers": routed["attempted_providers"],\n    }\n',
    )

    # ---------------------------------------------------------
    # 2. Prompt: defense in depth if a wording misses detection.
    # ---------------------------------------------------------
    replace_once(
        prompt,
        'Do not say that the task-command system is "coming later", "not active",\nor "not implemented", because it is already available.\n',
        'Do not say that the task-command system is "coming later", "not active",\nor "not implemented", because it is already available.\n\nNever invent or guess your current AI provider or model identity. Runtime\nprovider/model identity is authoritative backend routing metadata. If a\nprovider/model identity question reaches this prompt, say that the app\nshould use the backend routing metadata rather than claiming an identity.\n',
    )

    # ---------------------------------------------------------
    # 3. Flutter: fix malformed provider footer separator.
    # ---------------------------------------------------------
    replace_once(
        screen,
        "    return parts.join(' ? ');\n",
        "    return parts.join(' · ');\n",
    )

    # ---------------------------------------------------------
    # 4. Focused unit tests for the deterministic override.
    # ---------------------------------------------------------
    test_file.write_text(
        '''"""Tests for authoritative provider/model identity replies."""\n\nimport src.modules.assistant.service as service\n\n\ndef _routed(**overrides):\n    value = {\n        "provider": "groq",\n        "type": "api",\n        "model": "openai/gpt-oss-20b",\n        "result": "I am definitely some other model.",\n        "fallback_used": False,\n        "attempted_providers": ["groq"],\n    }\n    value.update(overrides)\n    return value\n\n\ndef test_identity_question_uses_backend_metadata(monkeypatch):\n    monkeypatch.setattr(\n        service,\n        "chat_with_fallback",\n        lambda **kwargs: _routed(),\n    )\n\n    result = service.send_chat("Which AI is this?")\n\n    assert result["provider"] == "groq"\n    assert result["model"] == "openai/gpt-oss-20b"\n    assert result["fallback_used"] is False\n    assert "Provider: Groq" in result["reply"]\n    assert "Model: openai/gpt-oss-20b" in result["reply"]\n    assert "Fallback: No" in result["reply"]\n    assert "some other model" not in result["reply"]\n\n\ndef test_identity_question_reports_actual_fallback_route(monkeypatch):\n    monkeypatch.setattr(\n        service,\n        "chat_with_fallback",\n        lambda **kwargs: _routed(\n            provider="cloudflare",\n            model="@cf/openai/gpt-oss-20b",\n            fallback_used=True,\n            attempted_providers=["groq", "gemini", "cloudflare"],\n        ),\n    )\n\n    result = service.send_chat("What model are you using?")\n\n    assert "Provider: Cloudflare Workers AI" in result["reply"]\n    assert "Model: @cf/openai/gpt-oss-20b" in result["reply"]\n    assert "Fallback: Yes" in result["reply"]\n    assert "Route: Groq -> Gemini -> Cloudflare Workers AI" in result["reply"]\n\n\ndef test_direct_provider_question_is_detected(monkeypatch):\n    monkeypatch.setattr(\n        service,\n        "chat_with_fallback",\n        lambda **kwargs: _routed(),\n    )\n\n    result = service.send_chat("Are you Gemini?")\n\n    assert "Provider: Groq" in result["reply"]\n    assert "Model: openai/gpt-oss-20b" in result["reply"]\n\n\ndef test_normal_chat_keeps_model_generated_reply(monkeypatch):\n    monkeypatch.setattr(\n        service,\n        "chat_with_fallback",\n        lambda **kwargs: _routed(result="Normal assistant answer."),\n    )\n\n    result = service.send_chat("Explain recurring tasks")\n\n    assert result["reply"] == "Normal assistant answer."\n\n\ndef test_model_recommendation_question_is_not_identity_query():\n    assert service._is_runtime_identity_question(\n        "What model should I use for image classification?"\n    ) is False\n''',
        encoding="utf-8",
    )

    print("Patch applied successfully.")
    print(f"Updated: {service}")
    print(f"Updated: {prompt}")
    print(f"Updated: {screen}")
    print(f"Added:   {test_file}")


if __name__ == "__main__":
    main()
