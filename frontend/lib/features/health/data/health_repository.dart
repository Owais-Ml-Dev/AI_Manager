import '../../../core/network/api_client.dart';

class HealthRepository {
  final ApiClient _apiClient;

  HealthRepository(this._apiClient);

  Future<Map<String, dynamic>> checkBackend() async {
    final result = await _apiClient.get('/health');

    if (result is Map<String, dynamic>) {
      return result;
    }

    return {'status': 'ok'};
  }

  Future<Map<String, dynamic>> checkDatabase() async {
    final result = await _apiClient.get('/health/database');

    if (result is Map<String, dynamic>) {
      return result;
    }

    return {'status': 'ok'};
  }
}
