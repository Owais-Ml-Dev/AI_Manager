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
}
