import '../../../core/network/api_client.dart';
import '../../../core/notifications/notification_sync_service.dart';

class TaskRepository {
  final ApiClient _apiClient;

  TaskRepository(this._apiClient);

  Future<dynamic> _mutateAndSync(Future<dynamic> Function() operation) async {
    final result = await operation();

    // Important:
    // whenever task data changes, immediately rebuild
    // Android's pending reminder queue.
    await NotificationSyncService.instance.syncFromBackend();

    return result;
  }

  Future<dynamic> createRecurringTask(Map<String, dynamic> data) {
    return _mutateAndSync(
      () => _apiClient.post('/api/tasks/recurring', data: data),
    );
  }

  Future<dynamic> createRepeatUntilDoneTask(Map<String, dynamic> data) {
    return _mutateAndSync(
      () => _apiClient.post('/api/tasks/repeat-until-done', data: data),
    );
  }

  Future<dynamic> getRecurringTask(String taskId) {
    return _apiClient.get('/api/tasks/recurring/$taskId');
  }

  Future<dynamic> getRecurringTaskDetails(String taskId) {
    return _apiClient.get('/api/tasks/recurring/$taskId/details');
  }

  Future<dynamic> getRepeatUntilDoneTask(String taskId) {
    return _apiClient.get('/api/tasks/repeat-until-done/$taskId');
  }

  Future<dynamic> updateRecurringTask(
    String taskId,
    Map<String, dynamic> data,
  ) {
    return _mutateAndSync(
      () => _apiClient.patch('/api/tasks/recurring/$taskId', data: data),
    );
  }

  Future<dynamic> updateRepeatUntilDoneTask(
    String taskId,
    Map<String, dynamic> data,
  ) {
    return _mutateAndSync(
      () =>
          _apiClient.patch('/api/tasks/repeat-until-done/$taskId', data: data),
    );
  }

  Future<dynamic> completeRecurringTask(String taskId) {
    return _mutateAndSync(
      () => _apiClient.patch(
        '/api/tasks/recurring/'
        '$taskId/complete',
      ),
    );
  }

  Future<dynamic> completeRecurringOccurrence(String occurrenceId) {
    return _mutateAndSync(
      () => _apiClient.patch(
        '/api/tasks/recurring/occurrences/'
        '$occurrenceId/complete',
      ),
    );
  }

  Future<dynamic> completeRepeatUntilDoneTask(String taskId) {
    return _mutateAndSync(
      () => _apiClient.patch(
        '/api/tasks/repeat-until-done/'
        '$taskId/complete',
      ),
    );
  }
}
