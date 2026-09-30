import 'package:flutter_test/flutter_test.dart';
import 'package:ai_task_manager/features/assistant/domain/assistant_intent.dart';

void main() {
  group('active task-control intent', () {
    test('detects explicit current discard', () {
      expect(
        detectActiveTaskControlIntent('Can we discard this task?'),
        ActiveTaskControlIntent.discardCurrent,
      );
      expect(
        detectActiveTaskControlIntent('Please delete this current task'),
        ActiveTaskControlIntent.discardCurrent,
      );
    });

    test('detects discard remaining/all', () {
      expect(
        detectActiveTaskControlIntent('Can we discard all the tasks?'),
        ActiveTaskControlIntent.discardRemaining,
      );
      expect(
        detectActiveTaskControlIntent('Abort everything'),
        ActiveTaskControlIntent.discardRemaining,
      );
      expect(
        detectActiveTaskControlIntent('Discard the remaining tasks'),
        ActiveTaskControlIntent.discardRemaining,
      );
    });

    test('detects skip for now', () {
      expect(
        detectActiveTaskControlIntent('Can we skip this task?'),
        ActiveTaskControlIntent.skipCurrent,
      );
      expect(
        detectActiveTaskControlIntent("I don't want to do this task now."),
        ActiveTaskControlIntent.skipCurrent,
      );
    });

    test('start-new request interrupts unfinished flow', () {
      expect(
        detectActiveTaskControlIntent('I want to start a new task.'),
        ActiveTaskControlIntent.startNewTask,
      );
    });

    test('generic stop and cancel remain ambiguous', () {
      expect(
        detectActiveTaskControlIntent("Let's stop this task."),
        ActiveTaskControlIntent.ambiguousStop,
      );
      expect(
        detectActiveTaskControlIntent('Cancel this.'),
        ActiveTaskControlIntent.ambiguousStop,
      );
      expect(
        detectActiveTaskControlIntent('exit'),
        ActiveTaskControlIntent.ambiguousStop,
      );
    });

    test('does not steal named task operations or normal answers', () {
      expect(
        detectActiveTaskControlIntent('cancel dentist task tomorrow'),
        ActiveTaskControlIntent.none,
      );
      expect(
        detectActiveTaskControlIntent('stop gym reminders'),
        ActiveTaskControlIntent.none,
      );
      expect(detectActiveTaskControlIntent('2'), ActiveTaskControlIntent.none);
      expect(
        detectActiveTaskControlIntent('Every day'),
        ActiveTaskControlIntent.none,
      );
    });
  });
}
