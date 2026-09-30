import 'package:flutter_test/flutter_test.dart';

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
