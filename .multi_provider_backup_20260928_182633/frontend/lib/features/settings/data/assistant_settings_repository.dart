import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/gemini_api_key_store.dart';
import '../domain/assistant_settings_data.dart';

class AssistantSettingsRepository {
  final ApiClient _apiClient;

  final GeminiApiKeyStore _keyStore;

  AssistantSettingsRepository(this._apiClient, this._keyStore);

  Future<AssistantSettingsData> fetch() async {
    final apiKey = await _keyStore.read();

    if (apiKey == null) {
      return const AssistantSettingsData(
        model: 'gemini-3.8-flash',
        message: 'Enter your own Gemini API key to use the AI Assistant.',
        available: false,
        configured: false,
        storedKeyConfigured: false,
        keyHint: null,
      );
    }

    final health = _asMap(
      await _apiClient.get(
        '/api/assistant/health',
        headers: {'X-Gemini-Api-Key': apiKey},
      ),
    );

    return AssistantSettingsData(
      model: health['model']?.toString() ?? 'gemini-3.8-flash',
      message: health['message']?.toString() ?? '',
      available: health['available'] == true,
      configured: true,
      storedKeyConfigured: true,
      keyHint: _keyHint(apiKey),
    );
  }

  Future<void> saveApiKey(String apiKey) async {
    final normalized = apiKey.trim();

    if (normalized.isEmpty) {
      throw const ApiException(message: 'Gemini API key is required.');
    }

    final health = _asMap(
      await _apiClient.get(
        '/api/assistant/health',
        headers: {'X-Gemini-Api-Key': normalized},
      ),
    );

    if (health['available'] != true) {
      throw ApiException(
        message:
            health['message']?.toString() ?? 'Gemini rejected this API key.',
      );
    }

    await _keyStore.save(normalized);
  }

  Future<void> deleteApiKey() {
    return _keyStore.delete();
  }

  String _keyHint(String apiKey) {
    if (apiKey.length <= 4) {
      return '****';
    }

    return '****${apiKey.substring(apiKey.length - 4)}';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) {
      return {};
    }

    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}
