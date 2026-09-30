import 'package:flutter_test/flutter_test.dart';

import 'package:ai_task_manager/features/assistant/domain/assistant_intent.dart';

void main() {
  group('Assistant automatic routing', () {
    test('normal conversation stays in chat', () {
      expect(looksLikeTaskAction('Hi, is this Gemini?'), isFalse);

      expect(looksLikeTaskAction('Give me a productivity tip'), isFalse);
    });

    test('task creation is detected', () {
      expect(
        looksLikeTaskAction(
          'Create a recurring gym task every weekday at 7 AM',
        ),
        isTrue,
      );
    });

    test('task completion is detected', () {
      expect(looksLikeTaskAction('Complete my gym task for today'), isTrue);
    });

    test('task listing is detected', () {
      expect(looksLikeTaskAction('Show my active tasks'), isTrue);
    });

    test('general how-to question stays chat', () {
      expect(looksLikeTaskAction('How do I create better habits?'), isFalse);
    });
  });

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

}
