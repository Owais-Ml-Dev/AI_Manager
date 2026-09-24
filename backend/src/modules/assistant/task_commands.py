"""Backward-compatible imports for assistant task command execution.

Task parsing now lives in :mod:`task_parser` and has no database access.
Execution lives in :mod:`command_executor` and never calls Gemini.
"""

from src.modules.assistant.command_executor import (
    MUTATING_ACTIONS,
    TaskCommandError,
    execute_task_command,
    normalize_executable_command,
    validate_executable_command,
)

__all__ = [
    "MUTATING_ACTIONS",
    "TaskCommandError",
    "execute_task_command",
    "normalize_executable_command",
    "validate_executable_command",
]
