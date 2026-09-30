from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
repo = root / 'lib/features/assistant/data/assistant_repository.dart'
screen = root / 'lib/features/assistant/presentation/assistant_screen.dart'
test = root / 'test/assistant_batch_resolution_model_test.dart'

for p in (repo, screen):
    if not p.exists():
        raise SystemExit(f'Missing expected file: {p}')
    backup = p.with_name(p.name + '.before_step2c.bak')
    if not backup.exists():
        shutil.copy2(p, backup)


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f'Expected block not found in {path}:\n{old[:260]}')
    write(path, text.replace(old, new, 1))


# ============================================================
# 1. Repository: parse confirm/cancel response and add endpoints.
# ============================================================
repo_text = read(repo)

if 'class AssistantTaskBatchResolutionResult' not in repo_text:
    anchor = 'class AssistantRepository {'
    if anchor not in repo_text:
        raise RuntimeError('Could not find AssistantRepository anchor.')

    model = r'''class AssistantTaskBatchResolutionResult {
  final String batchId;
  final String batchStatus;
  final int resolvedTaskNumber;
  final String resolution;
  final int? currentTaskNumber;
  final int totalTasks;
  final bool allDone;
  final AssistantTaskBatchActiveResult? nextTask;
  final String? nextTaskError;

  const AssistantTaskBatchResolutionResult({
    required this.batchId,
    required this.batchStatus,
    required this.resolvedTaskNumber,
    required this.resolution,
    required this.currentTaskNumber,
    required this.totalTasks,
    required this.allDone,
    required this.nextTask,
    required this.nextTaskError,
  });

  factory AssistantTaskBatchResolutionResult.fromMap(
    Map<String, dynamic> data,
  ) {
    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    int? asNullableInt(dynamic value) {
      if (value == null) return null;
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value.toString());
    }

    final nextTaskMap = _assistantMap(data['next_task']);
    final nextTaskErrorMap = _assistantMap(data['next_task_error']);

    return AssistantTaskBatchResolutionResult(
      batchId: data['batch_id']?.toString() ?? '',
      batchStatus: data['batch_status']?.toString() ?? '',
      resolvedTaskNumber: asInt(data['resolved_task_number']),
      resolution: data['resolution']?.toString() ?? '',
      currentTaskNumber: asNullableInt(data['current_task_number']),
      totalTasks: asInt(data['total_tasks']),
      allDone: data['all_done'] == true,
      nextTask: nextTaskMap.isEmpty
          ? null
          : AssistantTaskBatchActiveResult.fromMap(nextTaskMap),
      nextTaskError: nextTaskErrorMap['message']?.toString(),
    );
  }
}

'''
    repo_text = repo_text.replace(anchor, model + anchor, 1)

if 'Future<AssistantTaskBatchActiveResult> getActiveTaskBatch(' not in repo_text:
    anchor = '  Future<AssistantTaskBatchActiveResult> continueTaskBatch('
    if anchor not in repo_text:
        raise RuntimeError('Could not find continueTaskBatch anchor.')
    method = r'''  Future<AssistantTaskBatchActiveResult> getActiveTaskBatch(
    String batchId,
  ) async {
    final result = await _apiClient.get(
      '/api/assistant/task-batch/$batchId/active',
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

if 'Future<AssistantTaskBatchResolutionResult> confirmTaskBatch(' not in repo_text:
    anchor = '  Future<AssistantCommandPreview> previewTaskCommand('
    if anchor not in repo_text:
        raise RuntimeError('Could not find previewTaskCommand anchor.')
    methods = r'''  Future<AssistantTaskBatchResolutionResult> confirmTaskBatch({
    required String batchId,
    required String draftId,
    String? duplicateDecision,
    String? candidateId,
  }) async {
    final payload = <String, dynamic>{
      'draft_id': draftId,
    };

    if (duplicateDecision != null) {
      payload['duplicate_decision'] = duplicateDecision;
    }
    if (candidateId != null) {
      payload['candidate_id'] = candidateId;
    }

    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/confirm',
      data: payload,
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch confirmation result.',
      );
    }

    return resolution;
  }

  Future<AssistantTaskBatchResolutionResult> cancelTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/cancel',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch cancellation result.',
      );
    }

    return resolution;
  }

'''
    repo_text = repo_text.replace(anchor, methods + anchor, 1)

write(repo, repo_text)


# ============================================================
# 2. AssistantScreen: resolve Task N through batch endpoints,
#    then render Task N+1 returned by backend.
# ============================================================
screen_text = read(screen)

if 'Future<void> _handleBatchResolution(' not in screen_text:
    anchor = '  Future<void> _previewTaskCommand(String message) async {'
    if anchor not in screen_text:
        raise RuntimeError('Could not find _previewTaskCommand anchor.')

    block = r'''  Future<void> _handleBatchResolution(
    AssistantTaskBatchResolutionResult resolution, {
    required AssistantCommandPreview resolvedPreview,
    required bool confirmed,
  }) async {
    if (!mounted) return;

    final resolvedNumber = resolution.resolvedTaskNumber;
    final totalTasks = resolution.totalTasks;

    setState(() {
      _pendingCommand = null;
      _selectedMatchId = null;
      _suggestions = const [];
      _activeDraftId = null;
      _messages.add(
        AssistantMessage(
          text: confirmed
              ? 'Done. Task $resolvedNumber of $totalTasks. '
                    '${resolvedPreview.summary}'
              : 'Skipped Task $resolvedNumber of $totalTasks. '
                    'No changes were made for this task.',
          fromUser: false,
          model: resolvedPreview.model,
        ),
      );
    });

    if (resolution.allDone) {
      setState(() {
        _activeBatchId = null;
        _activeDraftId = null;
        _pendingCommand = null;
        _selectedMatchId = null;
        _suggestions = const [];
        _messages.add(
          AssistantMessage(
            text: 'Batch complete. All $totalTasks task requests were reviewed.',
            fromUser: false,
          ),
        );
      });
      _scrollToBottom();
      return;
    }

    var nextTask = resolution.nextTask;

    // The backend normally returns the already-prepared next task. If that
    // preparation failed after the previous task was safely resolved, recover
    // through the idempotent /active endpoint instead of misreporting the
    // confirmed task as failed.
    if (nextTask == null) {
      try {
        nextTask = await ref
            .read(assistantRepositoryProvider)
            .getActiveTaskBatch(resolution.batchId);
      } on ApiException catch (error) {
        if (!mounted) return;
        _activeBatchId = resolution.batchId;
        _addError(
          'Task $resolvedNumber was ${confirmed ? 'saved' : 'skipped'}, '
          'but the next task could not be loaded: ${error.message}',
        );
        return;
      } catch (_) {
        if (!mounted) return;
        _activeBatchId = resolution.batchId;
        _addError(
          'Task $resolvedNumber was ${confirmed ? 'saved' : 'skipped'}, '
          'but the next task could not be loaded.',
        );
        return;
      }
    }

    if (!mounted) return;

    _applyBatchDraft(
      batchId: nextTask.batchId,
      currentTaskNumber: nextTask.currentTaskNumber,
      totalTasks: nextTask.totalTasks,
      preview: nextTask.activeDraft,
    );
  }

  Future<void> _confirmBatchCommand({
    String? duplicateDecision,
    String? candidateId,
  }) async {
    final batchId = _activeBatchId;
    final preview = _pendingCommand;

    if (batchId == null ||
        batchId.isEmpty ||
        preview == null ||
        _sending) {
      return;
    }

    setState(() => _sending = true);

    try {
      final resolution = await ref
          .read(assistantRepositoryProvider)
          .confirmTaskBatch(
            batchId: batchId,
            draftId: preview.draftId,
            duplicateDecision: duplicateDecision,
            candidateId: candidateId,
          );

      _refreshTaskScreens();

      await _handleBatchResolution(
        resolution,
        resolvedPreview: preview,
        confirmed: true,
      );
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not confirm that batch task.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _cancelBatchCommand() async {
    final batchId = _activeBatchId;
    final preview = _pendingCommand;

    if (batchId == null ||
        batchId.isEmpty ||
        preview == null ||
        _sending) {
      return;
    }

    setState(() => _sending = true);

    try {
      final resolution = await ref
          .read(assistantRepositoryProvider)
          .cancelTaskBatch(
            batchId: batchId,
            draftId: preview.draftId,
          );

      await _handleBatchResolution(
        resolution,
        resolvedPreview: preview,
        confirmed: false,
      );
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not skip that batch task.');
    } finally {
      _finishSending();
    }
  }

'''
    screen_text = screen_text.replace(anchor, block + anchor, 1)

# Route review-card buttons to batch endpoints when a batch is active.
old = '''              onConfirm: () => _confirmCommand(),
              onCreateNew: () =>
                  _confirmCommand(duplicateDecision: 'create_new'),
              onUpdateExisting: () => _confirmCommand(
                duplicateDecision: 'update_existing',
                candidateId: _selectedMatchId,
              ),
              onCancel: _cancelCommand,
              busy: _sending || _activeBatchId != null,
'''
new = '''              onConfirm: () => _activeBatchId != null
                  ? _confirmBatchCommand()
                  : _confirmCommand(),
              onCreateNew: () => _activeBatchId != null
                  ? _confirmBatchCommand(duplicateDecision: 'create_new')
                  : _confirmCommand(duplicateDecision: 'create_new'),
              onUpdateExisting: () => _activeBatchId != null
                  ? _confirmBatchCommand(
                      duplicateDecision: 'update_existing',
                      candidateId: _selectedMatchId,
                    )
                  : _confirmCommand(
                      duplicateDecision: 'update_existing',
                      candidateId: _selectedMatchId,
                    ),
              onCancel: _activeBatchId != null
                  ? _cancelBatchCommand
                  : _cancelCommand,
              busy: _sending,
'''
if new not in screen_text:
    if old not in screen_text:
        raise RuntimeError('Could not find Step 2B review-card callback block.')
    screen_text = screen_text.replace(old, new, 1)

write(screen, screen_text)


# ============================================================
# 3. Pure model tests for confirm/cancel response contract.
# ============================================================
test.write_text(r'''import 'package:flutter_test/flutter_test.dart';

import 'package:ai_task_manager/features/assistant/data/assistant_repository.dart';

void main() {
  group('Assistant batch resolution model', () {
    test('parses confirmed Task 1 and prepared Task 2', () {
      final result = AssistantTaskBatchResolutionResult.fromMap({
        'batch_id': 'batch-1',
        'batch_status': 'in_progress',
        'resolved_task_number': 1,
        'resolution': 'executed',
        'current_task_number': 2,
        'total_tasks': 3,
        'all_done': false,
        'next_task': {
          'batch_id': 'batch-1',
          'batch_status': 'in_progress',
          'total_tasks': 3,
          'current_task_number': 2,
          'item_status': 'active',
          'draft': {
            'draft_id': 'draft-2',
            'status': 'needs_input',
            'question': 'What are the start and end dates?',
            'missing_fields': ['duration'],
            'command': <String, dynamic>{},
            'duplicate_matches': <dynamic>[],
            'target_matches': <dynamic>[],
            'suggestions': <dynamic>[],
          },
        },
        'next_task_error': null,
      });

      expect(result.batchId, 'batch-1');
      expect(result.resolution, 'executed');
      expect(result.resolvedTaskNumber, 1);
      expect(result.currentTaskNumber, 2);
      expect(result.allDone, isFalse);
      expect(result.nextTask, isNotNull);
      expect(result.nextTask!.currentTaskNumber, 2);
      expect(result.nextTask!.activeDraft.draftId, 'draft-2');
      expect(result.nextTask!.activeDraft.needsInput, isTrue);
    });

    test('parses skipped task with review-ready next task', () {
      final result = AssistantTaskBatchResolutionResult.fromMap({
        'batch_id': 'batch-2',
        'batch_status': 'in_progress',
        'resolved_task_number': 1,
        'resolution': 'skipped',
        'current_task_number': 2,
        'total_tasks': 2,
        'all_done': false,
        'next_task': {
          'batch_id': 'batch-2',
          'batch_status': 'in_progress',
          'total_tasks': 2,
          'current_task_number': 2,
          'item_status': 'active',
          'draft': {
            'draft_id': 'draft-ready',
            'status': 'ready',
            'missing_fields': <dynamic>[],
            'command': {
              'action': 'create_recurring_task',
              'summary': 'Create recurring task "Call John"',
              'requires_confirmation': true,
              'arguments': <String, dynamic>{},
            },
            'duplicate_matches': <dynamic>[],
            'target_matches': <dynamic>[],
            'suggestions': <dynamic>[],
          },
        },
      });

      expect(result.resolution, 'skipped');
      expect(result.nextTask, isNotNull);
      expect(result.nextTask!.activeDraft.ready, isTrue);
      expect(
        result.nextTask!.activeDraft.summary,
        'Create recurring task "Call John"',
      );
    });

    test('parses completed batch with no next task', () {
      final result = AssistantTaskBatchResolutionResult.fromMap({
        'batch_id': 'batch-final',
        'batch_status': 'completed',
        'resolved_task_number': 3,
        'resolution': 'executed',
        'current_task_number': null,
        'total_tasks': 3,
        'all_done': true,
        'next_task': null,
        'next_task_error': null,
      });

      expect(result.allDone, isTrue);
      expect(result.currentTaskNumber, isNull);
      expect(result.nextTask, isNull);
      expect(result.nextTaskError, isNull);
    });

    test('keeps next-task preparation error available for recovery UI', () {
      final result = AssistantTaskBatchResolutionResult.fromMap({
        'batch_id': 'batch-recover',
        'batch_status': 'in_progress',
        'resolved_task_number': 1,
        'resolution': 'executed',
        'current_task_number': 2,
        'total_tasks': 2,
        'all_done': false,
        'next_task': null,
        'next_task_error': {
          'message': 'Could not prepare the next task.',
          'status_code': 409,
        },
      });

      expect(result.nextTask, isNull);
      expect(result.nextTaskError, 'Could not prepare the next task.');
    });
  });
}
''', encoding='utf-8')

print('Frontend Step 2C applied successfully.')
print('Changes:')
print('  - batch review Confirm uses /task-batch/<id>/confirm')
print('  - batch review Cancel uses /task-batch/<id>/cancel')
print('  - duplicate decisions are preserved for batch confirmation')
print('  - Task N+1 is rendered immediately from backend next_task')
print('  - /active recovery is used if next-task preparation needs retry')
print('  - completed batches clear local batch state')
