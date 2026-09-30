from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python fix_single_task_skip.py <frontend_dir>")

frontend = Path(sys.argv[1]).resolve()
screen = frontend / "lib/features/assistant/presentation/assistant_screen.dart"

if not screen.exists():
    raise RuntimeError(f"Could not find {screen}")

text = screen.read_text(encoding="utf-8-sig")

pattern = re.compile(
    r"  Future<void> _confirmSkipCurrentTask\(\) async \{.*?"
    r"(?=  Future<void> _confirmDiscardCurrentTask\(\) async \{)",
    re.DOTALL,
)

replacement = '''  Future<void> _confirmSkipCurrentTask() async {
    final batchId = _activeBatchId;
    final draftId = _activeDraftId;
    if (_sending || batchId == null || draftId == null) return;

    final totalTasks = _activeBatchTotalTasks ?? 1;
    final isOnlyTask = totalTasks <= 1;

    setState(() => _sending = true);
    try {
      // "Skip for now" requires another unfinished task to move to.
      //
      // For a one-task batch, use the existing batch-cancel endpoint instead:
      // it resolves the only item as skipped, creates nothing, and completes
      // the batch cleanly.
      final resolution = isOnlyTask
          ? await ref
              .read(assistantRepositoryProvider)
              .cancelTaskBatch(
                batchId: batchId,
                draftId: draftId,
              )
          : await ref
              .read(assistantRepositoryProvider)
              .deferTaskBatch(
                batchId: batchId,
                draftId: draftId,
              );

      await _handleTaskControlResolution(
        resolution,
        message: isOnlyTask
            ? 'Skipped Task ${resolution.resolvedTaskNumber}. No task was created from it.'
            : 'Skipped Task ${resolution.resolvedTaskNumber} for now. I will return to it after the other unfinished tasks.',
      );
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError(
        isOnlyTask
            ? 'Could not skip that task.'
            : 'Could not skip that task for now.',
      );
    } finally {
      _finishSending();
    }
  }

'''

text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError(
        "Could not locate the current _confirmSkipCurrentTask() method. "
        "Do not make manual edits; send me that method if this occurs."
    )

old_label = "'Skip Task $current for Now'"
new_label = "total <= 1 ? 'Skip Task $current' : 'Skip Task $current for Now'"

label_count = text.count(old_label)
if label_count == 0:
    if new_label not in text:
        raise RuntimeError("Could not find the Skip button labels.")
else:
    text = text.replace(old_label, new_label)

screen.write_text(text, encoding="utf-8")

print("Fixed single-task Skip behavior.")
print("- Task 1 of 1: Skip uses /cancel and completes the batch.")
print("- Task N of M (M > 1): Skip uses /defer and is revisited later.")
print("- Single-task button now says 'Skip Task 1' instead of 'for Now'.")
