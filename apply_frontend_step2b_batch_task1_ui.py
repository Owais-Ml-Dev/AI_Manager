from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()

screen = root / 'lib/features/assistant/presentation/assistant_screen.dart'
intent = root / 'lib/features/assistant/domain/assistant_intent.dart'
repo = root / 'lib/features/assistant/data/assistant_repository.dart'
test = root / 'test/assistant_intent_test.dart'

for p in (screen, intent, repo, test):
    if not p.exists():
        raise SystemExit(f'Missing expected file: {p}')
    backup = p.with_name(p.name + '.before_step2b.bak')
    if not backup.exists():
        shutil.copy2(p, backup)


def replace_once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f'Expected block not found in {path}:\n{old[:220]}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')

# ============================================================
# 1. Domain routing helper
#    Route NEW create requests to the batch endpoint.
#    The backend decides whether there is 1 task or many.
# ============================================================
text = intent.read_text(encoding='utf-8-sig')
marker = 'bool shouldInterruptTaskDraft(String message) {'
if 'bool looksLikeCreateTaskAction(String message)' not in text:
    if marker not in text:
        raise RuntimeError('Could not find shouldInterruptTaskDraft anchor.')
    helper = r'''bool looksLikeCreateTaskAction(String message) {
  final text = message.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

  if (text.isEmpty) {
    return false;
  }

  // General explanation questions must stay normal chat.
  if (RegExp(r'^(how do i|how can i|why|explain|tell me about)\b')
      .hasMatch(text)) {
    return false;
  }

  // Never route non-create task operations into the batch-create API.
  if (RegExp(
    r'\b(edit|update|change|rename|reschedule|move|complete|finish|delete|remove|cancel|stop|show|list|display)\b',
  ).hasMatch(text)) {
    return false;
  }

  if (RegExp(r'\bmark\b.*\b(done|complete|completed)\b').hasMatch(text)) {
    return false;
  }

  // Explicit create language.
  if (RegExp(r'^(create|add|schedule|make|set|plan)\b').hasMatch(text) ||
      RegExp(r'\bremind me\b').hasMatch(text) ||
      RegExp(r'\bset (a )?reminder\b').hasMatch(text)) {
    return true;
  }

  // Preserve the existing "Gym task" / "Medicine reminder" shorthand.
  // At this point known read/update/delete/complete verbs were excluded above.
  return RegExp(r'\btasks?\b').hasMatch(text) ||
      RegExp(r'\breminders?\b').hasMatch(text);
}

'''
    intent.write_text(text.replace(marker, helper + marker, 1), encoding='utf-8')

# ============================================================
# 2. Repository active-batch model + continue endpoint
# ============================================================
repo_text = repo.read_text(encoding='utf-8-sig')
if 'class AssistantTaskBatchActiveResult' not in repo_text:
    anchor = 'class AssistantRepository {'
    if anchor not in repo_text:
        raise RuntimeError('Could not find AssistantRepository anchor.')
    model = r'''class AssistantTaskBatchActiveResult {
  final String batchId;
  final String batchStatus;
  final int totalTasks;
  final int currentTaskNumber;
  final String itemStatus;
  final AssistantCommandPreview activeDraft;

  const AssistantTaskBatchActiveResult({
    required this.batchId,
    required this.batchStatus,
    required this.totalTasks,
    required this.currentTaskNumber,
    required this.itemStatus,
    required this.activeDraft,
  });

  factory AssistantTaskBatchActiveResult.fromMap(Map<String, dynamic> data) {
    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    return AssistantTaskBatchActiveResult(
      batchId: data['batch_id']?.toString() ?? '',
      batchStatus: data['batch_status']?.toString() ?? '',
      totalTasks: asInt(data['total_tasks']),
      currentTaskNumber: asInt(data['current_task_number']),
      itemStatus: data['item_status']?.toString() ?? '',
      activeDraft: _assistantPreviewFromMap(_assistantMap(data['draft'])),
    );
  }
}

'''
    repo_text = repo_text.replace(anchor, model + anchor, 1)

if 'Future<AssistantTaskBatchActiveResult> continueTaskBatch(' not in repo_text:
    anchor = '  Future<AssistantCommandPreview> previewTaskCommand('
    if anchor not in repo_text:
        raise RuntimeError('Could not find previewTaskCommand anchor.')
    method = r'''  Future<AssistantTaskBatchActiveResult> continueTaskBatch({
    required String batchId,
    required String message,
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();

    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/continue',
      data: <String, dynamic>{'message': message},
      cancelToken: cancelToken,
      headers: headers,
    );

    final active = AssistantTaskBatchActiveResult.fromMap(_asMap(result));

    if (active.batchId.isEmpty || active.activeDraft.draftId.isEmpty) {
      throw const ApiException(
        message: 'The backend returned an invalid active batch task.',
      );
    }

    return active;
  }

'''
    repo_text = repo_text.replace(anchor, method + anchor, 1)

repo.write_text(repo_text, encoding='utf-8')

# ============================================================
# 3. AssistantScreen state
# ============================================================
replace_once(
    screen,
    '  String? _selectedMatchId;\n\n  // Quick-reply chips for the question currently being asked.',
    '''  String? _selectedMatchId;\n\n  // Ordered multi-task creation state.\n  String? _activeBatchId;\n  int? _activeBatchTaskNumber;\n  int? _activeBatchTotalTasks;\n\n  // Quick-reply chips for the question currently being asked.''',
)

# Do not use the legacy local-cancel path while a server-owned batch is active.
replace_once(
    screen,
    '''    if (_activeDraftId != null &&\n        const {\n          'cancel',\n          'never mind',\n          'nevermind',\n          'stop',\n        }.contains(normalized)) {''',
    '''    if (_activeBatchId == null &&\n        _activeDraftId != null &&\n        const {\n          'cancel',\n          'never mind',\n          'nevermind',\n          'stop',\n        }.contains(normalized)) {''',
)

# A read-only command must not silently discard a server-owned batch.
replace_once(
    screen,
    '''    final interruptDraft =\n        _activeDraftId != null && shouldInterruptTaskDraft(message);''',
    '''    final interruptDraft =\n        _activeBatchId == null &&\n        _activeDraftId != null &&\n        shouldInterruptTaskDraft(message);''',
)

# Route active batch answers to /continue; route new creates to /start.
replace_once(
    screen,
    '''    if (_activeDraftId != null || looksLikeTaskAction(message)) {\n      await _previewTaskCommand(message);\n    } else {\n      await _sendChat(message);\n    }''',
    '''    if (_activeBatchId != null) {\n      await _continueTaskBatch(message);\n    } else if (_activeDraftId == null && looksLikeCreateTaskAction(message)) {\n      await _startTaskBatch(message);\n    } else if (_activeDraftId != null || looksLikeTaskAction(message)) {\n      await _previewTaskCommand(message);\n    } else {\n      await _sendChat(message);\n    }''',
)

# Insert batch rendering/start/continue before legacy preview method.
screen_text = screen.read_text(encoding='utf-8-sig')
if 'Future<void> _startTaskBatch(String message)' not in screen_text:
    anchor = '  Future<void> _previewTaskCommand(String message) async {'
    if anchor not in screen_text:
        raise RuntimeError('Could not find _previewTaskCommand anchor.')
    block = r'''  void _applyBatchDraft({
    required String batchId,
    required int currentTaskNumber,
    required int totalTasks,
    required AssistantCommandPreview preview,
    String? provider,
    String? model,
    bool fallbackUsed = false,
  }) {
    _activeBatchId = batchId;
    _activeBatchTaskNumber = currentTaskNumber;
    _activeBatchTotalTasks = totalTasks;
    _activeDraftId = preview.draftId;

    final position = 'Task $currentTaskNumber of $totalTasks';

    if (preview.needsInput) {
      setState(() {
        _pendingCommand = null;
        _selectedMatchId = null;
        _suggestions = preview.suggestions;
        _messages.add(
          AssistantMessage(
            text: '$position\n\n${preview.question ?? 'I need a little more information.'}',
            fromUser: false,
            provider: provider,
            model: (model ?? '').isNotEmpty ? model : preview.model,
            fallbackUsed: fallbackUsed,
          ),
        );
      });
      _scrollToBottom();
      return;
    }

    setState(() {
      _pendingCommand = preview;
      _selectedMatchId = null;
      _suggestions = const [];
      _messages.add(
        AssistantMessage(
          text: '$position is ready for review.',
          fromUser: false,
          provider: provider,
          model: (model ?? '').isNotEmpty ? model : preview.model,
          fallbackUsed: fallbackUsed,
        ),
      );
    });
    _scrollToBottom();
  }

  Future<void> _startTaskBatch(String message) async {
    try {
      final batch = await ref
          .read(assistantRepositoryProvider)
          .startTaskBatch(message, cancelToken: _activeCancelToken);

      if (!mounted) return;

      _applyBatchDraft(
        batchId: batch.batchId,
        currentTaskNumber: batch.currentTaskNumber,
        totalTasks: batch.totalTasks,
        preview: batch.activeDraft,
        provider: batch.provider,
        model: batch.model,
        fallbackUsed: batch.fallbackUsed,
      );
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) return;
      rethrow;
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not start that task request.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _continueTaskBatch(String message) async {
    final batchId = _activeBatchId;
    if (batchId == null || batchId.isEmpty) {
      _addError('The active task batch could not be recovered.');
      _finishSending();
      return;
    }

    try {
      final active = await ref
          .read(assistantRepositoryProvider)
          .continueTaskBatch(
            batchId: batchId,
            message: message,
            cancelToken: _activeCancelToken,
          );

      if (!mounted) return;

      _applyBatchDraft(
        batchId: active.batchId,
        currentTaskNumber: active.currentTaskNumber,
        totalTasks: active.totalTasks,
        preview: active.activeDraft,
      );
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) return;
      rethrow;
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not continue that task.');
    } finally {
      _finishSending();
    }
  }

'''
    screen.write_text(screen_text.replace(anchor, block + anchor, 1), encoding='utf-8')

# Disable legacy confirm/cancel actions for a batch-owned review until Step 2C.
replace_once(
    screen,
    '              busy: _sending,\n            ),',
    '              busy: _sending || _activeBatchId != null,\n            ),',
)

# ============================================================
# 4. Intent tests
# ============================================================
test_text = test.read_text(encoding='utf-8-sig')
if "group('Assistant create routing'" not in test_text:
    insert = r'''

  group('Assistant create routing', () {
    test('new create requests use the batch creation path', () {
      expect(
        looksLikeCreateTaskAction(
          'Create a gym task and call Mom on Sunday',
        ),
        isTrue,
      );
      expect(looksLikeCreateTaskAction('Remind me to pay rent tomorrow'), isTrue);
      expect(looksLikeCreateTaskAction('Gym task'), isTrue);
    });

    test('non-create task actions do not use batch creation', () {
      expect(looksLikeCreateTaskAction('Update my gym task'), isFalse);
      expect(looksLikeCreateTaskAction('Complete my gym task'), isFalse);
      expect(looksLikeCreateTaskAction('Delete my gym task'), isFalse);
      expect(looksLikeCreateTaskAction('Show my tasks'), isFalse);
    });

    test('general questions do not use batch creation', () {
      expect(looksLikeCreateTaskAction('How do I create better habits?'), isFalse);
    });
  });
'''
    idx = test_text.rfind('\n}')
    if idx == -1:
        raise RuntimeError('Could not find end of assistant_intent_test.dart')
    test_text = test_text[:idx] + insert + test_text[idx:]
    test.write_text(test_text, encoding='utf-8')

print('Frontend Step 2B applied successfully.')
print('Changes:')
print('  - create-task requests start the server-owned batch workflow')
print('  - Task 1 follow-up answers use /task-batch/<id>/continue')
print('  - Task 1 question/review is rendered in AssistantScreen')
print('  - batch_id/current task position are stored in screen state')
print('  - legacy confirmation buttons are disabled for batch reviews')
print('  - no Task 1 -> Task 2 confirmation/advancement UI yet')
