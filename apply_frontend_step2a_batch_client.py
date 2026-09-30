from pathlib import Path
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def backup(path: Path) -> None:
    target = path.with_name(path.name + '.before_step2a.bak')
    if not target.exists():
        shutil.copy2(path, target)


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        print(f'Already updated: {path}')
        return
    if old not in text:
        raise RuntimeError(f'Expected block not found in {path}')
    backup(path)
    write(path, text.replace(old, new, 1))
    print(f'Updated: {path}')


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            'Usage: python apply_frontend_step2a_batch_client.py <frontend_dir>'
        )

    frontend = Path(sys.argv[1]).resolve()
    repo = frontend / 'lib/features/assistant/data/assistant_repository.dart'
    test = frontend / 'test/assistant_batch_client_model_test.dart'

    if not repo.exists():
        raise RuntimeError(f'Missing expected file: {repo}')

    # ------------------------------------------------------------------
    # 1. Add a typed model for POST /task-batch/start.
    #    We deliberately reuse AssistantCommandPreview for the nested
    #    Task-1 draft so the future UI can use the same review card.
    # ------------------------------------------------------------------
    anchor = '''class AssistantRepository {\n'''
    model_block = r'''Map<String, dynamic> _assistantMap(dynamic value) {
  if (value is! Map) return <String, dynamic>{};
  return value.map((key, value) => MapEntry(key.toString(), value));
}

List<dynamic> _assistantList(dynamic value) {
  if (value is! List) return const <dynamic>[];
  return value;
}

AssistantCommandPreview _assistantPreviewFromMap(Map<String, dynamic> data) {
  return AssistantCommandPreview(
    model: data['model']?.toString() ?? '',
    timezone: data['timezone']?.toString() ?? '',
    draftId: data['draft_id']?.toString() ?? '',
    status: data['status']?.toString() ?? '',
    question: data['question']?.toString(),
    missingFields: _assistantList(data['missing_fields'])
        .map((value) => value.toString())
        .toList(),
    command: _assistantMap(data['command']),
    duplicateMatches: _assistantList(data['duplicate_matches'])
        .map(_assistantMap)
        .map(AssistantTaskMatch.fromMap)
        .where((match) => match.id.isNotEmpty)
        .toList(),
    targetMatches: _assistantList(data['target_matches'])
        .map(_assistantMap)
        .map(AssistantTaskMatch.fromMap)
        .where((match) => match.id.isNotEmpty)
        .toList(),
    suggestions: _assistantList(data['suggestions'])
        .map((value) => value.toString())
        .where((value) => value.isNotEmpty)
        .toList(),
  );
}

class AssistantTaskBatchStartResult {
  final String batchId;
  final int totalTasks;
  final int currentTaskNumber;
  final String provider;
  final String model;
  final bool fallbackUsed;
  final AssistantCommandPreview activeDraft;

  const AssistantTaskBatchStartResult({
    required this.batchId,
    required this.totalTasks,
    required this.currentTaskNumber,
    required this.provider,
    required this.model,
    required this.fallbackUsed,
    required this.activeDraft,
  });

  bool get hasMultipleTasks => totalTasks > 1;

  factory AssistantTaskBatchStartResult.fromMap(Map<String, dynamic> data) {
    final activeTask = _assistantMap(data['active_task']);
    final draft = _assistantMap(activeTask['draft']);

    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    return AssistantTaskBatchStartResult(
      batchId: data['batch_id']?.toString() ?? '',
      totalTasks: asInt(data['total_tasks']),
      currentTaskNumber: asInt(data['current_task_number']),
      provider: data['provider']?.toString() ?? '',
      model: data['model']?.toString() ?? '',
      fallbackUsed: data['fallback_used'] == true,
      activeDraft: _assistantPreviewFromMap(draft),
    );
  }
}

'''

    text = read(repo)
    if 'class AssistantTaskBatchStartResult {' not in text:
        if anchor not in text:
            raise RuntimeError('Could not find AssistantRepository class anchor.')
        backup(repo)
        write(repo, text.replace(anchor, model_block + anchor, 1))
        print(f'Updated: {repo}')
    else:
        print(f'Already updated: {repo}')

    # ------------------------------------------------------------------
    # 2. Add the network call. No AssistantScreen routing is changed yet.
    # ------------------------------------------------------------------
    method_anchor = '''  Future<AssistantCommandPreview> previewTaskCommand(\n'''
    method = r'''  Future<AssistantTaskBatchStartResult> startTaskBatch(
    String message, {
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();

    final result = await _apiClient.post(
      '/api/assistant/task-batch/start',
      data: <String, dynamic>{
        'message': message,
        'timezone': _deviceUtcOffset(),
      },
      cancelToken: cancelToken,
      headers: headers,
    );

    final batch = AssistantTaskBatchStartResult.fromMap(_asMap(result));

    if (batch.batchId.isEmpty || batch.activeDraft.draftId.isEmpty) {
      throw const ApiException(
        message: 'The backend returned an invalid task batch.',
      );
    }

    return batch;
  }

'''

    text = read(repo)
    if 'Future<AssistantTaskBatchStartResult> startTaskBatch(' not in text:
        if method_anchor not in text:
            raise RuntimeError('Could not find previewTaskCommand method anchor.')
        backup(repo)
        write(repo, text.replace(method_anchor, method + method_anchor, 1))
        print(f'Updated: {repo}')
    else:
        print(f'Already updated: {repo}')

    # ------------------------------------------------------------------
    # 3. Pure Flutter unit tests for the response contract. These do not
    #    touch the network and therefore are stable/fast.
    # ------------------------------------------------------------------
    test.write_text(r'''import 'package:flutter_test/flutter_test.dart';

import 'package:ai_task_manager/features/assistant/data/assistant_repository.dart';

void main() {
  group('Assistant task batch start model', () {
    test('parses Task 1 missing-information response', () {
      final result = AssistantTaskBatchStartResult.fromMap({
        'batch_id': 'batch-123',
        'total_tasks': 3,
        'current_task_number': 1,
        'provider': 'groq',
        'model': 'openai/gpt-oss-20b',
        'fallback_used': false,
        'active_task': {
          'draft': {
            'draft_id': 'draft-1',
            'status': 'needs_input',
            'question': 'What are the start and end dates?',
            'missing_fields': ['duration'],
            'command': <String, dynamic>{},
            'duplicate_matches': <dynamic>[],
            'target_matches': <dynamic>[],
            'suggestions': <dynamic>[],
          },
        },
      });

      expect(result.batchId, 'batch-123');
      expect(result.totalTasks, 3);
      expect(result.currentTaskNumber, 1);
      expect(result.hasMultipleTasks, isTrue);
      expect(result.activeDraft.draftId, 'draft-1');
      expect(result.activeDraft.needsInput, isTrue);
      expect(result.activeDraft.missingFields, ['duration']);
      expect(result.activeDraft.question, 'What are the start and end dates?');
    });

    test('parses Task 1 review-ready response', () {
      final result = AssistantTaskBatchStartResult.fromMap({
        'batch_id': 'batch-456',
        'total_tasks': 2,
        'current_task_number': 1,
        'provider': 'gemini',
        'model': 'gemini-test',
        'fallback_used': true,
        'active_task': {
          'draft': {
            'draft_id': 'draft-review',
            'status': 'ready',
            'missing_fields': <dynamic>[],
            'command': {
              'action': 'create_recurring_task',
              'summary': 'Create recurring task "Gym"',
              'requires_confirmation': true,
              'arguments': <String, dynamic>{},
            },
            'duplicate_matches': <dynamic>[],
            'target_matches': <dynamic>[],
            'suggestions': <dynamic>[],
          },
        },
      });

      expect(result.currentTaskNumber, 1);
      expect(result.activeDraft.ready, isTrue);
      expect(result.activeDraft.requiresConfirmation, isTrue);
      expect(result.activeDraft.summary, 'Create recurring task "Gym"');
      expect(result.fallbackUsed, isTrue);
    });

    test('single-task batch is represented without pretending it is multi-task', () {
      final result = AssistantTaskBatchStartResult.fromMap({
        'batch_id': 'batch-single',
        'total_tasks': 1,
        'current_task_number': 1,
        'active_task': {
          'draft': {
            'draft_id': 'draft-single',
            'status': 'needs_input',
            'missing_fields': ['repeat'],
            'command': <String, dynamic>{},
            'duplicate_matches': <dynamic>[],
            'target_matches': <dynamic>[],
            'suggestions': <dynamic>[],
          },
        },
      });

      expect(result.hasMultipleTasks, isFalse);
      expect(result.totalTasks, 1);
      expect(result.activeDraft.draftId, 'draft-single');
    });
  });
}
''', encoding='utf-8')
    print(f'Updated: {test}')

    print('\nFRONTEND STEP 2A APPLIED')
    print('Added typed task-batch start response + repository startTaskBatch().')
    print('AssistantScreen behavior is intentionally unchanged in this step.')


if __name__ == '__main__':
    main()
