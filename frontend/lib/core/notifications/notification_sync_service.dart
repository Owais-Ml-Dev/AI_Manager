import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../network/api_client.dart';
import 'notification_service.dart';

class NotificationSyncService {
  NotificationSyncService._();

  static final NotificationSyncService instance = NotificationSyncService._();

  final ApiClient _apiClient = ApiClient();

  static const int _maxScheduled = 450;

  // Repeat Until Done has no end date,
  // so maintain a rolling future window.
  static const int _repeatUntilDoneHorizonDays = 60;

  Future<void> syncFromBackend() async {
    try {
      await NotificationService.instance.prepareTimeZone();

      final candidates = <_ReminderCandidate>[];

      await _loadRecurring(candidates);

      await _loadRepeatUntilDone(candidates);

      candidates.sort((a, b) => a.when.compareTo(b.when));

      await NotificationService.instance.cancelPendingTaskNotifications();

      final limited = candidates.take(_maxScheduled).toList();

      var notificationId = 10000;

      for (final candidate in limited) {
        await NotificationService.instance.scheduleTaskReminder(
          id: notificationId,
          title: candidate.title,
          body: candidate.body,
          localDateTime: candidate.when,
          payload: jsonEncode(candidate.payload),
        );

        notificationId++;
      }

      final pendingCount = await NotificationService.instance.pendingCount();

      debugPrint(
        'Task notification sync complete. '
        'Candidates: ${candidates.length}, '
        'scheduled: $pendingCount.',
      );

      if (candidates.length > _maxScheduled) {
        debugPrint(
          'Notification queue capped at '
          '$_maxScheduled reminders.',
        );
      }
    } catch (error, stackTrace) {
      // Notification synchronization must
      // never stop the whole application.
      debugPrint(
        'Task notification sync failed: '
        '$error',
      );

      debugPrint('$stackTrace');
    }
  }

  // =======================================================
  // RECURRING
  // =======================================================

  Future<void> _loadRecurring(List<_ReminderCandidate> candidates) async {
    final rawParents = await _apiClient.get('/api/tasks/recurring');

    final parents = _asList(rawParents);

    for (final parent in parents) {
      final taskId = parent['id']?.toString();

      if (taskId == null || taskId.isEmpty) {
        continue;
      }

      final rawDetails = await _apiClient.get(
        '/api/tasks/recurring/'
        '$taskId/details',
      );

      final details = _asMap(rawDetails);

      final task = _asMap(details['task']);

      final title =
          task['title']?.toString() ??
          parent['title']?.toString() ??
          'Task reminder';

      final occurrences = _asList(details['occurrences']);

      for (final occurrence in occurrences) {
        if (occurrence['status']?.toString() != 'pending') {
          continue;
        }

        if (occurrence['reminders_cancelled'] == true) {
          continue;
        }

        final occurrenceId = occurrence['id']?.toString();

        final scheduledDate = occurrence['scheduled_date']?.toString();

        if (occurrenceId == null || scheduledDate == null) {
          continue;
        }

        final times = _generatedTimes(occurrence['reminders']);

        for (final time in times) {
          final when = _combineDateAndTime(scheduledDate, time);

          if (when == null || !when.isAfter(DateTime.now())) {
            continue;
          }

          candidates.add(
            _ReminderCandidate(
              when: when,
              title: title,
              body: 'Recurring task reminder',
              payload: {
                'type': 'recurring',
                'task_id': taskId,
                'occurrence_id': occurrenceId,
                'scheduled_date': scheduledDate,
                'title': title,
                'body': 'Recurring task reminder',
              },
            ),
          );
        }
      }
    }
  }

  // =======================================================
  // REPEAT UNTIL DONE
  // =======================================================

  Future<void> _loadRepeatUntilDone(List<_ReminderCandidate> candidates) async {
    final rawTasks = await _apiClient.get('/api/tasks/repeat-until-done');

    final tasks = _asList(rawTasks);

    final today = DateTime.now();

    final startDate = DateTime(today.year, today.month, today.day);

    for (final task in tasks) {
      if (task['status']?.toString() != 'pending') {
        continue;
      }

      if (task['reminders_cancelled'] == true) {
        continue;
      }

      final taskId = task['id']?.toString();

      if (taskId == null || taskId.isEmpty) {
        continue;
      }

      final title = task['title']?.toString() ?? 'Task reminder';

      final repeat = _asMap(task['repeat']);

      final times = _generatedTimes(task['reminders']);

      if (times.isEmpty) {
        continue;
      }

      for (var offset = 0; offset < _repeatUntilDoneHorizonDays; offset++) {
        final date = startDate.add(Duration(days: offset));

        if (!_repeatMatchesDate(repeat, date)) {
          continue;
        }

        final dateText = _dateText(date);

        for (final time in times) {
          final when = _combineDateAndTime(dateText, time);

          if (when == null || !when.isAfter(DateTime.now())) {
            continue;
          }

          candidates.add(
            _ReminderCandidate(
              when: when,
              title: title,
              body: 'Repeat Until Done reminder',
              payload: {
                'type': 'repeat_until_done',
                'task_id': taskId,
                'scheduled_date': dateText,
                'title': title,
                'body': 'Repeat Until Done reminder',
              },
            ),
          );
        }
      }
    }
  }

  // =======================================================
  // REPEAT RULES
  // =======================================================

  bool _repeatMatchesDate(Map<String, dynamic> repeat, DateTime date) {
    final type = repeat['type']?.toString();

    switch (type) {
      case 'everyday':
        return true;

      case 'weekdays':
        return date.weekday >= DateTime.monday &&
            date.weekday <= DateTime.friday;

      case 'weekends':
        return date.weekday == DateTime.saturday ||
            date.weekday == DateTime.sunday;

      case 'custom_dates':
        final rawDates = repeat['custom_dates'];

        if (rawDates is! List) {
          return false;
        }

        return rawDates
            .map((value) => value.toString())
            .contains(_dateText(date));

      default:
        return false;
    }
  }

  // =======================================================
  // REMINDER PARSING
  // =======================================================

  List<String> _generatedTimes(dynamic rawReminders) {
    if (rawReminders is! List) {
      return [];
    }

    final result = <String>[];

    for (final rawReminder in rawReminders) {
      if (rawReminder is! Map) {
        continue;
      }

      final reminder = rawReminder.map(
        (key, value) => MapEntry(key.toString(), value),
      );

      final generated = reminder['generated_times'];

      if (generated is List) {
        for (final value in generated) {
          final time = value.toString();

          if (time.isNotEmpty) {
            result.add(time);
          }
        }

        continue;
      }

      // Compatibility fallback.
      final start = reminder['start_time']?.toString();

      if (start != null && start.isNotEmpty) {
        result.add(start);
      }
    }

    return result;
  }

  DateTime? _combineDateAndTime(String date, String time) {
    final dateParts = date.split('-');

    final timeParts = time.split(':');

    if (dateParts.length != 3 || timeParts.length < 2) {
      return null;
    }

    final year = int.tryParse(dateParts[0]);

    final month = int.tryParse(dateParts[1]);

    final day = int.tryParse(dateParts[2]);

    final hour = int.tryParse(timeParts[0]);

    final minute = int.tryParse(timeParts[1]);

    final second = timeParts.length >= 3 ? int.tryParse(timeParts[2]) ?? 0 : 0;

    if (year == null ||
        month == null ||
        day == null ||
        hour == null ||
        minute == null) {
      return null;
    }

    return DateTime(year, month, day, hour, minute, second);
  }

  String _dateText(DateTime date) {
    final year = date.year.toString().padLeft(4, '0');

    final month = date.month.toString().padLeft(2, '0');

    final day = date.day.toString().padLeft(2, '0');

    return '$year-$month-$day';
  }

  List<Map<String, dynamic>> _asList(dynamic value) {
    if (value is! List) {
      return [];
    }

    return value
        .whereType<Map>()
        .map(
          (item) => item.map((key, value) => MapEntry(key.toString(), value)),
        )
        .toList();
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) {
      return {};
    }

    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}

class _ReminderCandidate {
  final DateTime when;
  final String title;
  final String body;
  final Map<String, dynamic> payload;

  const _ReminderCandidate({
    required this.when,
    required this.title,
    required this.body,
    required this.payload,
  });
}
