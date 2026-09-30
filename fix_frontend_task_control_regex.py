from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python fix_frontend_task_control_regex.py <frontend_dir>")

frontend = Path(sys.argv[1]).resolve()
path = frontend / "lib/features/assistant/domain/assistant_intent.dart"

if not path.exists():
    raise RuntimeError(f"Could not find {path}")

text = path.read_text(encoding="utf-8-sig")

broken_variants = [
    """    r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)"
    r'( this| this task| the task| current task)?$",
""",
    """    r'^(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)"
    r'( this| this task| the task| current task)?$",
""",
]

fixed_without_caret = """    r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)'
    r'( this| this task| the task| current task)?$',
"""

fixed_with_caret = """    r'^(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)'
    r'( this| this task| the task| current task)?$',
"""

changed = False

if broken_variants[1] in text:
    text = text.replace(broken_variants[1], fixed_with_caret, 1)
    changed = True
elif broken_variants[0] in text:
    text = text.replace(broken_variants[0], fixed_without_caret, 1)
    changed = True
else:
    # Safer fallback for the exact malformed quote sequence.
    old1 = "r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)\""
    old2 = "r'( this| this task| the task| current task)?$\","
    if old1 in text and old2 in text:
        text = text.replace(
            old1,
            "r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)'",
            1,
        )
        text = text.replace(
            old2,
            "r'( this| this task| the task| current task)?$',",
            1,
        )
        changed = True

if not changed:
    print("The malformed regex was not found. It may already be fixed.")
    raise SystemExit(0)

path.write_text(text, encoding="utf-8")
print(f"Fixed: {path}")
print("Corrected the two raw-string closing quotes in the ambiguous-stop RegExp.")
