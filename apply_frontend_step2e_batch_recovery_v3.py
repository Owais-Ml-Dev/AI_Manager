from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply_frontend_step2e_batch_recovery.py <frontend_dir>')

frontend = Path(sys.argv[1]).resolve()
screen = frontend / 'lib/features/assistant/presentation/assistant_screen.dart'
store = frontend / 'lib/features/assistant/data/assistant_batch_session_store.dart'
test = frontend / 'test/assistant_batch_session_store_test.dart'

if not screen.exists():
    raise RuntimeError(f'Could not find {screen}')

text = screen.read_text(encoding='utf-8-sig')

# Backup once.
backup = screen.with_name(screen.name + '.before_step2e.bak')
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

# 1. Import session store.
anchor = "import '../data/assistant_repository.dart';\n"
replacement = anchor + "import '../data/assistant_batch_session_store.dart';\n"
if "assistant_batch_session_store.dart" not in text:
    if anchor not in text:
        raise RuntimeError('Could not find assistant repository import anchor.')
    text = text.replace(anchor, replacement, 1)

# 2. Add store field next to active batch state.
field_anchor = "  // Ordered multi-task creation state.\n  String? _activeBatchId;\n"
field_replacement = (
    "  // Ordered multi-task creation state.\n"
    "  String? _activeBatchId;\n"
    "  final AssistantBatchSessionStore _batchSessionStore =\n"
    "      const AssistantBatchSessionStore();\n"
)
if "_batchSessionStore" not in text:
    if field_anchor not in text:
        raise RuntimeError('Could not find active batch field anchor.')
    text = text.replace(field_anchor, field_replacement, 1)

# 3. Add initState + recovery helpers before dispose.
dispose_anchor = "  @override\n  void dispose() {\n"
recovery_block = r'''  @override
  void initState() {
    super.initState();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _recoverPersistedTaskBatch();
    });
  }

  Future<void> _rememberActiveBatch(String batchId) async {
    try {
      await _batchSessionStore.saveActiveBatchId(batchId);
    } catch (error) {
      debugPrint('[BATCH] Could not persist active batch id: $error');
    }
  }

  Future<void> _forgetActiveBatch() async {
    try {
      await _batchSessionStore.clearActiveBatchId();
    } catch (error) {
      debugPrint('[BATCH] Could not clear persisted batch id: $error');
    }
  }

  Future<void> _recoverPersistedTaskBatch() async {
    String? batchId;

    try {
      batchId = await _batchSessionStore.loadActiveBatchId();
    } catch (error) {
      debugPrint('[BATCH] Could not read persisted batch id: $error');
      return;
    }

    if (!mounted || batchId == null || batchId.isEmpty) {
      return;
    }

    // Claim the recovered batch locally before the network request so a
    // temporary backend outage cannot accidentally start a second batch.
    setState(() {
      _activeBatchId = batchId;
      _sending = true;
    });

    try {
      final active = await ref
          .read(assistantRepositoryProvider)
          .getActiveTaskBatch(batchId);

      if (!mounted) return;

      _applyBatchDraft(
        batchId: active.batchId,
        currentTaskNumber: active.currentTaskNumber,
        totalTasks: active.totalTasks,
        preview: active.activeDraft,
      );
    } on ApiException catch (error) {
      if (!mounted) return;

      // The stored id can outlive the server-side batch TTL or a batch that
      // completed immediately before the app was terminated. In those cases
      // remove only the stale local pointer.
      if (error.statusCode == 404 || error.statusCode == 409) {
        await _forgetActiveBatch();
        if (!mounted) return;
        setState(() {
          _activeBatchId = null;
          _activeDraftId = null;
          _pendingCommand = null;
          _selectedMatchId = null;
          _suggestions = const [];
        });
        return;
      }

      setState(() {
        _messages.add(
          const AssistantMessage(
            text: 'Your unfinished task batch is still saved, but it could '
                'not be restored right now. Reopen Assistant when the '
                'backend is available.',
            fromUser: false,
          ),
        );
      });
    } catch (error) {
      if (!mounted) return;
      debugPrint('[BATCH] Recovery failed: $error');
      setState(() {
        _messages.add(
          const AssistantMessage(
            text: 'Your unfinished task batch is still saved, but it could '
                'not be restored right now. Reopen Assistant and try again.',
            fromUser: false,
          ),
        );
      });
    } finally {
      _finishSending();
    }
  }

'''
if "_recoverPersistedTaskBatch" not in text:
    if dispose_anchor not in text:
        raise RuntimeError('Could not find dispose anchor.')
    text = text.replace(dispose_anchor, recovery_block + dispose_anchor, 1)

# 4. Persist batch immediately after /start succeeds.
start_anchor = """      if (!mounted) return;\n\n      _applyBatchDraft(\n        batchId: batch.batchId,\n"""
start_replacement = """      await _rememberActiveBatch(batch.batchId);\n\n      if (!mounted) return;\n\n      _applyBatchDraft(\n        batchId: batch.batchId,\n"""
if "await _rememberActiveBatch(batch.batchId);" not in text:
    if start_anchor not in text:
        raise RuntimeError('Could not find batch start persistence anchor.')
    text = text.replace(start_anchor, start_replacement, 1)

# 5. Clear persisted pointer when the batch is completed.
all_done_anchor = """    if (resolution.allDone) {\n      setState(() {\n"""
all_done_replacement = """    if (resolution.allDone) {\n      await _forgetActiveBatch();\n      if (!mounted) return;\n\n      setState(() {\n"""
if "if (resolution.allDone) {\n      await _forgetActiveBatch();" not in text:
    if all_done_anchor not in text:
        raise RuntimeError('Could not find batch completion anchor.')
    text = text.replace(all_done_anchor, all_done_replacement, 1)

# 6. Refresh persistence when moving to another active task.
next_anchor = """    var nextTask = resolution.nextTask;\n"""
next_replacement = """    await _rememberActiveBatch(resolution.batchId);\n    if (!mounted) return;\n\n    var nextTask = resolution.nextTask;\n"""
if "await _rememberActiveBatch(resolution.batchId);" not in text:
    if next_anchor not in text:
        raise RuntimeError('Could not find next-task persistence anchor.')
    text = text.replace(next_anchor, next_replacement, 1)

screen.write_text(text, encoding='utf-8')

# 7. Create small persistence abstraction.
store.parent.mkdir(parents=True, exist_ok=True)
store.write_text(r'''import 'package:shared_preferences/shared_preferences.dart';

class AssistantBatchSessionStore {
  static const String activeBatchIdKey =
      'assistant_active_task_batch_id';

  const AssistantBatchSessionStore();

  Future<String?> loadActiveBatchId() async {
    final preferences = await SharedPreferences.getInstance();
    final value = preferences.getString(activeBatchIdKey)?.trim();

    if (value == null || value.isEmpty) {
      return null;
    }

    return value;
  }

  Future<void> saveActiveBatchId(String batchId) async {
    final value = batchId.trim();
    if (value.isEmpty) {
      throw ArgumentError.value(
        batchId,
        'batchId',
        'Active batch id cannot be empty.',
      );
    }

    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(activeBatchIdKey, value);
  }

  Future<void> clearActiveBatchId() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(activeBatchIdKey);
  }
}
''', encoding='utf-8')

# 8. Unit tests for persistence semantics.
test.write_text(r'''import 'package:flutter_test/flutter_test.dart';
import 'package:ai_task_manager/features/assistant/data/assistant_batch_session_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const store = AssistantBatchSessionStore();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('active batch id survives a new store instance', () async {
    await store.saveActiveBatchId('batch-123');

    const reopenedStore = AssistantBatchSessionStore();

    expect(
      await reopenedStore.loadActiveBatchId(),
      'batch-123',
    );
  });

  test('clearing active batch removes restart recovery pointer', () async {
    await store.saveActiveBatchId('batch-123');
    await store.clearActiveBatchId();

    expect(await store.loadActiveBatchId(), isNull);
  });

  test('empty batch id is rejected', () async {
    await expectLater(
      store.saveActiveBatchId('   '),
      throwsArgumentError,
    );
  });
}
''', encoding='utf-8')

print('Frontend Step 2E applied successfully.')
print('Changes:')
print('  - active batch id is persisted with SharedPreferences')
print('  - Assistant restores /task-batch/<id>/active after app/screen restart')
print('  - stale completed/expired batch pointers are cleared safely')
print('  - transient recovery failures keep the batch id for a later retry')
print('  - final batch completion clears the persisted recovery pointer')
