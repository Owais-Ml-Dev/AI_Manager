import 'package:intl/intl.dart';

import '../../../core/network/api_client.dart';
import '../domain/home_task_item.dart';

class HomeRepository {
  final ApiClient _apiClient;

  HomeRepository(this._apiClient);

  Future<HomeData> fetchHome() async {
    final responses = await Future.wait([
      _apiClient.get('/api/tasks/recurring'),
      _apiClient.get('/api/tasks/repeat-until-done'),
      _apiClient.get('/api/tasks/repeat-until-done/history'),
    ]);

    final recurringParents = _asList(responses[0]);

    final activeRepeatTasks = _asList(responses[1]);

    final repeatHistory = _asList(responses[2]);

    final recurringTasks = await _loadTodayRecurring(recurringParents);

    final repeatUntilDoneTasks = _loadRepeatUntilDone(
      activeRepeatTasks,
      repeatHistory,
    );

    final allTasks = [...recurringTasks, ...repeatUntilDoneTasks];

    final completedCount = allTasks.where((task) => task.isCompleted).length;

    return HomeData(
      recurringTasks: recurringTasks,
      repeatUntilDoneTasks: repeatUntilDoneTasks,
      completedCount: completedCount,
      totalCount: allTasks.length,
    );
  }

  Future<List<HomeTaskItem>> _loadTodayRecurring(
    List<Map<String, dynamic>> parents,
  ) async {
    final futures = parents.map((task) async {
      final id = task['id']?.toString();

      if (id == null || id.isEmpty) {
        return null;
      }

      final result = await _apiClient.get('/api/tasks/recurring/$id/details');

      final details = _asMap(result);

      final occurrence = _nullableMap(details['today_occurrence']);

      if (occurrence == null) {
        return null;
      }

      final parent = _asMap(details['task']);

      final status = _statusFrom(occurrence['status']?.toString());

      String subtitle;

      if (status == HomeTaskStatus.completed) {
        subtitle = _completedText(occurrence['completed_at']?.toString());
      } else if (status == HomeTaskStatus.missed) {
        subtitle = 'Missed';
      } else {
        subtitle = _reminderText(
          occurrence['reminders'],
          fallback: _repeatText(parent['repeat']),
        );
      }

      return HomeTaskItem(
        taskId: id,
        occurrenceId: occurrence['id']?.toString(),
        kind: HomeTaskKind.recurring,
        title: parent['title']?.toString() ?? 'Untitled task',
        priority: parent['priority']?.toString() ?? '',
        status: status,
        subtitle: subtitle,
      );
    });

    final results = await Future.wait(futures);

    final tasks = results.whereType<HomeTaskItem>().toList();

    _sortTasks(tasks);

    return tasks;
  }

  List<HomeTaskItem> _loadRepeatUntilDone(
    List<Map<String, dynamic>> active,
    List<Map<String, dynamic>> history,
  ) {
    final result = <HomeTaskItem>[];

    for (final task in active) {
      if (!_isDueToday(task['repeat'])) {
        continue;
      }

      final id = task['id']?.toString();

      if (id == null) {
        continue;
      }

      result.add(
        HomeTaskItem(
          taskId: id,
          kind: HomeTaskKind.repeatUntilDone,
          title: task['title']?.toString() ?? 'Untitled task',
          priority: task['priority']?.toString() ?? '',
          status: HomeTaskStatus.pending,
          subtitle: _reminderText(
            task['reminders'],
            fallback: _repeatText(task['repeat']),
          ),
        ),
      );
    }

    // Completed Repeat Until Done tasks disappear
    // from the active endpoint, so we also read
    // today's completed history.
    for (final task in history) {
      final completedAt = task['completed_at']?.toString();

      if (!_isToday(completedAt)) {
        continue;
      }

      final id = task['id']?.toString();

      if (id == null) {
        continue;
      }

      result.add(
        HomeTaskItem(
          taskId: id,
          kind: HomeTaskKind.repeatUntilDone,
          title: task['title']?.toString() ?? 'Untitled task',
          priority: task['priority']?.toString() ?? '',
          status: HomeTaskStatus.completed,
          subtitle: _completedText(completedAt),
        ),
      );
    }

    _sortTasks(result);

    return result;
  }

  bool _isDueToday(dynamic rawRepeat) {
    final repeat = _asMap(rawRepeat);

    final type = repeat['type']?.toString();

    final now = DateTime.now();

    switch (type) {
      case 'everyday':
        return true;

      case 'weekdays':
        return now.weekday >= DateTime.monday && now.weekday <= DateTime.friday;

      case 'weekends':
        return now.weekday == DateTime.saturday ||
            now.weekday == DateTime.sunday;

      case 'custom_dates':
        final today = DateFormat('yyyy-MM-dd').format(now);

        final dates = repeat['custom_dates'];

        if (dates is! List) {
          return false;
        }

        return dates.map((date) => date.toString()).contains(today);

      default:
        return false;
    }
  }

  bool _isToday(String? value) {
    if (value == null || value.isEmpty) {
      return false;
    }

    final parsed = DateTime.tryParse(value);

    if (parsed == null) {
      return false;
    }

    final local = parsed.toLocal();

    final now = DateTime.now();

    return local.year == now.year &&
        local.month == now.month &&
        local.day == now.day;
  }

  String _completedText(String? completedAt) {
    if (completedAt == null) {
      return 'Completed';
    }

    final parsed = DateTime.tryParse(completedAt);

    if (parsed == null) {
      return 'Completed';
    }

    return 'Completed ${DateFormat('h:mm a').format(parsed.toLocal())}';
  }

  String _reminderText(dynamic rawReminders, {required String fallback}) {
    if (rawReminders is! List || rawReminders.isEmpty) {
      return fallback;
    }

    final reminders = rawReminders.whereType<Map>().toList();

    if (reminders.isEmpty) {
      return fallback;
    }

    final first = reminders.first;

    final start = first['start_time']?.toString();

    final end = first['end_time']?.toString();

    var totalCount = 0;

    for (final reminder in reminders) {
      final count = reminder['count'];

      if (count is int) {
        totalCount += count;
      }
    }

    final timeText = _timeRange(start, end);

    if (timeText.isEmpty) {
      return fallback;
    }

    if (totalCount <= 0) {
      return timeText;
    }

    final reminderWord = totalCount == 1 ? 'reminder' : 'reminders';

    return '$timeText ? '
        '$totalCount $reminderWord';
  }

  String _timeRange(String? start, String? end) {
    final startText = _formatTime(start);

    final endText = _formatTime(end);

    if (startText.isEmpty) {
      return '';
    }

    if (endText.isEmpty || start == end) {
      return startText;
    }

    return '$startText ? $endText';
  }

  String _formatTime(String? value) {
    if (value == null) {
      return '';
    }

    final parts = value.split(':');

    if (parts.length < 2) {
      return value;
    }

    final hour = int.tryParse(parts[0]);

    final minute = int.tryParse(parts[1]);

    if (hour == null || minute == null) {
      return value;
    }

    return DateFormat('h:mm a').format(DateTime(2000, 1, 1, hour, minute));
  }

  String _repeatText(dynamic rawRepeat) {
    final repeat = _asMap(rawRepeat);

    switch (repeat['type']?.toString()) {
      case 'everyday':
        return 'Every day';

      case 'weekdays':
        return 'Weekdays';

      case 'weekends':
        return 'Weekends';

      case 'custom_dates':
        return 'Custom dates';

      default:
        return 'Scheduled';
    }
  }

  HomeTaskStatus _statusFrom(String? value) {
    switch (value) {
      case 'completed':
        return HomeTaskStatus.completed;

      case 'missed':
        return HomeTaskStatus.missed;

      default:
        return HomeTaskStatus.pending;
    }
  }

  void _sortTasks(List<HomeTaskItem> tasks) {
    int rank(HomeTaskStatus status) {
      switch (status) {
        case HomeTaskStatus.pending:
          return 0;

        case HomeTaskStatus.missed:
          return 1;

        case HomeTaskStatus.completed:
          return 2;
      }
    }

    tasks.sort((a, b) => rank(a.status).compareTo(rank(b.status)));
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

  Map<String, dynamic>? _nullableMap(dynamic value) {
    if (value == null || value is! Map) {
      return null;
    }

    return _asMap(value);
  }
}
