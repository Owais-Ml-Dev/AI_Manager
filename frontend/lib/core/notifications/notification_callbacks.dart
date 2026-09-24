import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../network/api_client.dart';
import 'notification_service.dart';
import 'notification_sync_service.dart';

void handleNotificationResponse(NotificationResponse response) async {
  await _handleNotificationAction(response);
}

@pragma('vm:entry-point')
void notificationBackgroundHandler(NotificationResponse response) async {
  await _handleNotificationAction(response);
}

Future<void> _handleNotificationAction(NotificationResponse response) async {
  final actionId = response.actionId;

  if (actionId == null || actionId.isEmpty) {
    // Normal notification tap.
    return;
  }

  final rawPayload = response.payload;

  if (rawPayload == null || rawPayload.isEmpty) {
    debugPrint(
      'Notification action ignored: '
      'missing payload.',
    );

    return;
  }

  Map<String, dynamic> payload;

  try {
    final decoded = jsonDecode(rawPayload);

    if (decoded is! Map) {
      return;
    }

    payload = decoded.map((key, value) => MapEntry(key.toString(), value));
  } catch (error) {
    debugPrint(
      'Invalid notification payload: '
      '$error',
    );

    return;
  }

  if (actionId == 'snooze_10') {
    await _snooze(payload, rawPayload);

    return;
  }

  if (actionId == 'done') {
    await _completeTask(payload);
  }
}

Future<void> _snooze(Map<String, dynamic> payload, String rawPayload) async {
  final title = payload['title']?.toString() ?? 'Task reminder';

  final body = payload['body']?.toString() ?? 'Task reminder';

  try {
    await NotificationService.instance.snoozeTenMinutes(
      title: title,
      body: body,
      payload: rawPayload,
    );
  } catch (error, stackTrace) {
    debugPrint(
      'Could not snooze notification: '
      '$error',
    );

    debugPrint('$stackTrace');
  }
}

Future<void> _completeTask(Map<String, dynamic> payload) async {
  final type = payload['type']?.toString();

  final apiClient = ApiClient();

  try {
    switch (type) {
      case 'recurring':
        final occurrenceId = payload['occurrence_id']?.toString();

        if (occurrenceId == null || occurrenceId.isEmpty) {
          throw StateError(
            'Recurring notification '
            'has no occurrence ID.',
          );
        }

        await apiClient.patch(
          '/api/tasks/recurring/'
          'occurrences/'
          '$occurrenceId/complete',
        );

        debugPrint(
          'Recurring occurrence '
          'completed from notification.',
        );

        break;

      case 'repeat_until_done':
        final taskId = payload['task_id']?.toString();

        if (taskId == null || taskId.isEmpty) {
          throw StateError(
            'Repeat Until Done '
            'notification has no task ID.',
          );
        }

        await apiClient.patch(
          '/api/tasks/'
          'repeat-until-done/'
          '$taskId/complete',
        );

        debugPrint(
          'Repeat Until Done task '
          'completed from notification.',
        );

        break;

      default:
        throw StateError(
          'Unknown notification '
          'task type: $type',
        );
    }

    // Rebuild all pending reminders.
    // This removes future reminders for
    // the task/occurrence just completed.
    await NotificationSyncService.instance.syncFromBackend();
  } catch (error, stackTrace) {
    debugPrint(
      'Could not complete task '
      'from notification: $error',
    );

    debugPrint('$stackTrace');
  }
}
