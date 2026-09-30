import 'package:flutter_test/flutter_test.dart';

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
