import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/gemini_api_key_store.dart';
import '../domain/assistant_settings_data.dart';

class AssistantSettingsRepository {
  final ApiClient _apiClient;
  final GeminiApiKeyStore _keyStore;

  AssistantSettingsRepository(this._apiClient, this._keyStore);

  static const _providerModels = <String, String>{
    'gemini': 'gemini-3.8-flash',
    'groq': 'openai/gpt-oss-20b',
    'cloudflare': '@cf/openai/gpt-oss-20b',
    'openrouter': 'openrouter/free',
  };

  static const _providerLabels = <String, String>{
    'gemini': 'Gemini',
    'groq': 'Groq',
    'cloudflare': 'Cloudflare Workers AI',
    'openrouter': 'OpenRouter Free',
  };

  Future<AssistantSettingsData> fetch() async {
    final providers = <AssistantProviderSettings>[];
    final cloudflareAccountId =
        await _keyStore.readCloudflareAccountId();

    final autoFallback =
        await _keyStore.readAutoFallback();

    for (final provider in _providerModels.keys) {
      final key = await _keyStore.readProviderApiKey(provider);
      providers.add(
        AssistantProviderSettings(
          provider: provider,
          label: _providerLabels[provider]!,
          model: _providerModels[provider]!,
          configured:
              key != null &&
              (provider != 'cloudflare' || cloudflareAccountId != null),
          keyHint: key == null ? null : _keyHint(key),
          accountId: provider == 'cloudflare' ? cloudflareAccountId : null,
          requiresAccountId: provider == 'cloudflare',
        ),
      );
    }

    return AssistantSettingsData(
      providers: providers,
      autoFallback: autoFallback,
      message: providers.any((item) => item.configured)
          ? autoFallback
              ? 'Automatic fallback is enabled.'
              : 'Automatic fallback is disabled.'
          : 'Add at least one provider API key to use the AI Assistant.',
    );
  }

  Future<void> saveAutoFallback(
    bool enabled,
  ) {
    return _keyStore.saveAutoFallback(
      enabled,
    );
  }

  Future<void> testAndSaveProvider(
    String provider,
    String apiKey, {
    String? accountId,
  }) async {
    final normalized = apiKey.trim();
    if (normalized.isEmpty) {
      throw ApiException(
        message:
            '${_providerLabels[provider] ?? provider} API key is required.',
      );
    }

    final headers = <String, dynamic>{};
    switch (provider) {
      case 'gemini':
        headers['X-Gemini-Api-Key'] = normalized;
        break;
      case 'groq':
        headers['X-Groq-Api-Key'] = normalized;
        break;
      case 'cloudflare':
        var normalizedAccountId = (accountId ?? '').trim();
        if (normalizedAccountId.isEmpty) {
          normalizedAccountId =
              (await _keyStore.readCloudflareAccountId()) ?? '';
        }
        if (normalizedAccountId.isEmpty) {
          throw const ApiException(
            message: 'Cloudflare Account ID is required.',
          );
        }
        headers['X-Cloudflare-Api-Token'] = normalized;
        headers['X-Cloudflare-Account-Id'] = normalizedAccountId;
        accountId = normalizedAccountId;
        break;
      case 'openrouter':
        headers['X-OpenRouter-Api-Key'] = normalized;
        break;
      default:
        throw ApiException(message: 'Unsupported AI provider: $provider');
    }

    final health = _asMap(
      await _apiClient.get(
        '/api/assistant/health',
        queryParameters: {'provider': provider},
        headers: headers,
      ),
    );

    if (health['available'] != true) {
      throw ApiException(
        message:
            health['message']?.toString() ??
            '${_providerLabels[provider] ?? provider} rejected these credentials.',
      );
    }

    await _keyStore.saveProviderApiKey(provider, normalized);
    if (provider == 'cloudflare') {
      await _keyStore.saveCloudflareAccountId((accountId ?? '').trim());
    }
  }

  Future<void> deleteProvider(String provider) async {
    await _keyStore.deleteProviderApiKey(provider);
    if (provider == 'cloudflare') {
      await _keyStore.deleteCloudflareAccountId();
    }
  }

  // Existing Gemini API remains available for older callers.
  Future<void> saveApiKey(String apiKey) =>
      testAndSaveProvider('gemini', apiKey);
  Future<void> deleteApiKey() => deleteProvider('gemini');

  String _keyHint(String apiKey) {
    if (apiKey.length <= 4) return '****';
    return '****${apiKey.substring(apiKey.length - 4)}';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}
