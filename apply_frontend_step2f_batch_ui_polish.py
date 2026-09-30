from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python apply_frontend_step2f_batch_ui_polish.py <frontend_dir>")

frontend = Path(sys.argv[1]).resolve()
path = frontend / "lib/features/assistant/presentation/assistant_screen.dart"

if not path.exists():
    raise SystemExit(f"Could not find: {path}")

text = path.read_text(encoding="utf-8-sig")
backup = path.with_suffix(path.suffix + ".before_step2f.bak")
if not backup.exists():
    shutil.copy2(path, backup)


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise RuntimeError(f"Step 2F could not find expected block: {label}")
    text = text.replace(old, new, 1)

# 1) Restore task position fields, now actually used by the UI.
replace_once(
    "  // Ordered multi-task creation state.\n"
    "  String? _activeBatchId;\n"
    "  final AssistantBatchSessionStore _batchSessionStore =\n",
    "  // Ordered multi-task creation state.\n"
    "  String? _activeBatchId;\n"
    "  int? _activeBatchTaskNumber;\n"
    "  int? _activeBatchTotalTasks;\n"
    "  final AssistantBatchSessionStore _batchSessionStore =\n",
    "batch state fields",
)

# 2) Clear progress state when a recovered batch is stale/completed.
replace_once(
    "          _activeBatchId = null;\n"
    "          _activeDraftId = null;\n"
    "          _pendingCommand = null;\n",
    "          _activeBatchId = null;\n"
    "          _activeBatchTaskNumber = null;\n"
    "          _activeBatchTotalTasks = null;\n"
    "          _activeDraftId = null;\n"
    "          _pendingCommand = null;\n",
    "stale recovery cleanup",
)

# 3) Keep the current position whenever a batch draft is applied/recovered.
replace_once(
    "    _activeBatchId = batchId;\n"
    "    _activeDraftId = preview.draftId;\n\n"
    "    final position = 'Task $currentTaskNumber of $totalTasks';\n",
    "    _activeBatchId = batchId;\n"
    "    _activeBatchTaskNumber = currentTaskNumber;\n"
    "    _activeBatchTotalTasks = totalTasks;\n"
    "    _activeDraftId = preview.draftId;\n\n"
    "    final position = 'Task $currentTaskNumber of $totalTasks';\n",
    "apply batch position",
)

# 4) Make resolution messages visually distinct without changing behavior.
replace_once(
    "          text: confirmed\n"
    "              ? 'Done. Task $resolvedNumber of $totalTasks. '\n"
    "                    '${resolvedPreview.summary}'\n"
    "              : 'Skipped Task $resolvedNumber of $totalTasks. '\n"
    "                    'No changes were made for this task.',\n",
    "          text: confirmed\n"
    "              ? '✓ Saved Task $resolvedNumber of $totalTasks\\n'\n"
    "                    '${resolvedPreview.summary}'\n"
    "              : '→ Skipped Task $resolvedNumber of $totalTasks\\n'\n"
    "                    'No changes were made for this task.',\n",
    "resolution message",
)

# 5) Clear progress state and improve final batch summary.
replace_once(
    "        _activeBatchId = null;\n"
    "        _activeDraftId = null;\n"
    "        _pendingCommand = null;\n"
    "        _selectedMatchId = null;\n"
    "        _suggestions = const [];\n"
    "        _messages.add(\n"
    "          AssistantMessage(\n"
    "            text: 'Batch complete. All $totalTasks task requests were reviewed.',\n"
    "            fromUser: false,\n"
    "          ),\n"
    "        );\n",
    "        _activeBatchId = null;\n"
    "        _activeBatchTaskNumber = null;\n"
    "        _activeBatchTotalTasks = null;\n"
    "        _activeDraftId = null;\n"
    "        _pendingCommand = null;\n"
    "        _selectedMatchId = null;\n"
    "        _suggestions = const [];\n"
    "        _messages.add(\n"
    "          AssistantMessage(\n"
    "            text: '✓ Batch complete\\n'\n"
    "                '$totalTasks of $totalTasks task requests reviewed.',\n"
    "            fromUser: false,\n"
    "          ),\n"
    "        );\n",
    "batch completion cleanup",
)

# 6) Add persistent progress banner below the Assistant header.
replace_once(
    "          _header(),\n"
    "          const Divider(height: 1),\n"
    "          Expanded(\n",
    "          _header(),\n"
    "          const Divider(height: 1),\n"
    "          if (_activeBatchId != null &&\n"
    "              _activeBatchTaskNumber != null &&\n"
    "              _activeBatchTotalTasks != null)\n"
    "            _batchProgressBanner(),\n"
    "          Expanded(\n",
    "batch banner insertion",
)

# 7) Add progress widget immediately before _emptyState().
replace_once(
    "  Widget _emptyState() {\n",
    "  Widget _batchProgressBanner() {\n"
    "    final colors = AppColors.of(context);\n"
    "    final current = _activeBatchTaskNumber ?? 1;\n"
    "    final total = _activeBatchTotalTasks ?? 1;\n"
    "    final reviewed = (current - 1).clamp(0, total);\n"
    "    final progress = total <= 0 ? 0.0 : reviewed / total;\n\n"
    "    return Container(\n"
    "      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),\n"
    "      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),\n"
    "      decoration: BoxDecoration(\n"
    "        color: colors.surfaceElevated,\n"
    "        borderRadius: BorderRadius.circular(14),\n"
    "        border: Border.all(color: colors.border),\n"
    "      ),\n"
    "      child: Column(\n"
    "        crossAxisAlignment: CrossAxisAlignment.start,\n"
    "        children: [\n"
    "          Row(\n"
    "            children: [\n"
    "              Expanded(\n"
    "                child: Text(\n"
    "                  'Task $current of $total',\n"
    "                  style: const TextStyle(\n"
    "                    fontSize: 12,\n"
    "                    fontWeight: FontWeight.w700,\n"
    "                  ),\n"
    "                ),\n"
    "              ),\n"
    "              Text(\n"
    "                '$reviewed of $total reviewed',\n"
    "                style: TextStyle(\n"
    "                  color: colors.textSecondary,\n"
    "                  fontSize: 10,\n"
    "                  fontWeight: FontWeight.w600,\n"
    "                ),\n"
    "              ),\n"
    "            ],\n"
    "          ),\n"
    "          const SizedBox(height: 9),\n"
    "          ClipRRect(\n"
    "            borderRadius: BorderRadius.circular(999),\n"
    "            child: LinearProgressIndicator(\n"
    "              value: progress,\n"
    "              minHeight: 5,\n"
    "              backgroundColor: colors.border,\n"
    "            ),\n"
    "          ),\n"
    "        ],\n"
    "      ),\n"
    "    );\n"
    "  }\n\n"
    "  Widget _emptyState() {\n",
    "batch progress widget",
)

path.write_text(text, encoding="utf-8")
print("Frontend Step 2F applied successfully.")
print(f"Backup: {backup}")
print("Changed only assistant_screen.dart; task/batch behavior is unchanged.")
