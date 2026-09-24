import '../../../core/network/api_client.dart';
import '../domain/dashboard_data.dart';

class DashboardRepository {
  final ApiClient _apiClient;

  DashboardRepository(this._apiClient);

  Future<DashboardData> fetchDashboard() async {
    final result = await _apiClient.get('/api/dashboard');

    final data = _asMap(result);

    final week = _asMap(data['week']);

    final thisWeek = _asMap(data['this_week']);

    final priority = _asMap(data['priority_matrix']);

    final daily = <DashboardDay>[];

    final rawDaily = data['daily_completion'];

    if (rawDaily is List) {
      for (final raw in rawDaily) {
        final item = _asMap(raw);

        daily.add(
          DashboardDay(
            date: item['date']?.toString() ?? '',
            day: item['day']?.toString() ?? '',
            completed: _toInt(item['completed']),
          ),
        );
      }
    }

    DashboardInsight? insight;

    if (data['insight'] is Map) {
      final rawInsight = _asMap(data['insight']);

      insight = DashboardInsight(
        taskTitle: rawInsight['task_title']?.toString() ?? '',
        weekday: rawInsight['weekday']?.toString() ?? '',
        missedCount: _toInt(rawInsight['missed_count']),
        message: rawInsight['message']?.toString() ?? '',
      );
    }

    return DashboardData(
      weekStart: week['start_date']?.toString() ?? '',
      weekEnd: week['end_date']?.toString() ?? '',
      done: _toInt(thisWeek['done']),
      missed: _toInt(thisWeek['missed']),
      streak: _toInt(thisWeek['streak']),
      dailyCompletion: daily,
      importantUrgent: _toInt(priority['important_urgent']),
      importantNotUrgent: _toInt(priority['important_not_urgent']),
      notImportantUrgent: _toInt(priority['not_important_urgent']),
      notImportantNotUrgent: _toInt(priority['not_important_not_urgent']),
      insight: insight,
    );
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

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) {
      return {};
    }

    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}
