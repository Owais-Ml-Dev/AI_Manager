import '../../../core/network/api_client.dart';
import '../domain/history_item.dart';

class HistoryRepository {
  final ApiClient _apiClient;

  HistoryRepository(this._apiClient);

  Future<Map<String, dynamic>> getRecurringDetails(String taskId) async {
    final result = await _apiClient.get('/api/tasks/recurring/$taskId/details');

    return _asMap(result);
  }

  Future<Map<String, dynamic>> getRepeatUntilDoneDetails(String taskId) async {
    final result = await _apiClient.get('/api/tasks/repeat-until-done/$taskId');

    return _asMap(result);
  }

  Future<void> deleteHistoryItems(Iterable<HistoryItem> items) async {
    for (final item in items) {
      switch (item.kind) {
        case HistoryTaskKind.recurring:
          await _apiClient.delete('/api/tasks/recurring/${item.taskId}');
          break;

        case HistoryTaskKind.repeatUntilDone:
          await _apiClient.delete(
            '/api/tasks/repeat-until-done/${item.taskId}',
          );
          break;
      }
    }
  }

  Future<HistoryData> fetchHistory() async {
    final results = await Future.wait([
      _apiClient.get('/api/tasks/recurring/history'),
      _apiClient.get('/api/tasks/repeat-until-done/history'),
    ]);

    final recurring = _parseRecurringHistory(results[0]);

    final repeatUntilDone = _parseRepeatUntilDoneHistory(results[1]);

    return HistoryData(recurring: recurring, repeatUntilDone: repeatUntilDone);
  }

  List<HistoryItem> _parseRecurringHistory(dynamic raw) {
    final items = <HistoryItem>[];

    for (final value in _asList(raw)) {
      final task = _asMap(value['task']);

      final summary = _asMap(value['summary']);

      final id = task['id']?.toString();

      if (id == null || id.isEmpty) {
        continue;
      }

      final duration = _asMap(task['duration']);

      items.add(
        HistoryItem(
          taskId: id,
          kind: HistoryTaskKind.recurring,
          title: task['title']?.toString() ?? 'Untitled task',
          description: task['description']?.toString(),
          priority: task['priority']?.toString() ?? '',
          date: _parseDateTime(task['ended_at']),
          startDate: duration['start_date']?.toString(),
          endDate: duration['end_date']?.toString(),
          done: _toInt(summary['done']),
          missed: _toInt(summary['missed']),
          completionRate: _toInt(summary['completion_rate']),
        ),
      );
    }

    items.sort((a, b) => _compareDates(b.date, a.date));

    return items;
  }

  List<HistoryItem> _parseRepeatUntilDoneHistory(dynamic raw) {
    final items = <HistoryItem>[];

    for (final task in _asList(raw)) {
      final id = task['id']?.toString();

      if (id == null || id.isEmpty) {
        continue;
      }

      items.add(
        HistoryItem(
          taskId: id,
          kind: HistoryTaskKind.repeatUntilDone,
          title: task['title']?.toString() ?? 'Untitled task',
          description: task['description']?.toString(),
          priority: task['priority']?.toString() ?? '',
          date: _parseDateTime(task['completed_at']),
        ),
      );
    }

    items.sort((a, b) => _compareDates(b.date, a.date));

    return items;
  }

  int _compareDates(DateTime? a, DateTime? b) {
    if (a == null && b == null) {
      return 0;
    }

    if (a == null) {
      return -1;
    }

    if (b == null) {
      return 1;
    }

    return a.compareTo(b);
  }

  DateTime? _parseDateTime(dynamic value) {
    if (value == null) {
      return null;
    }

    return DateTime.tryParse(value.toString())?.toLocal();
  }

  int _toInt(dynamic value) {
    if (value is int) {
      return value;
    }

    if (value is num) {
      return value.round();
    }

    return int.tryParse(value?.toString() ?? '') ?? 0;
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
