import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class GeminiApiKeyStore {
  static const _geminiKey = 'gemini_api_key';
  static const _groqKey = 'groq_api_key';
  static const _cloudflareTokenKey = 'cloudflare_api_token';
  static const _cloudflareAccountIdKey = 'cloudflare_account_id';
  static const _openRouterKey = 'openrouter_api_key';

  static const _cerebrasKey = 'cerebras_api_key';

  static const _mistralKey = 'mistral_api_key';

  static const _nvidiaKey = 'nvidia_api_key';
  static const _autoFallbackKey = 'ai_auto_fallback';

  static const _preferredProviderKey = 'ai_preferred_provider';

  final FlutterSecureStorage _storage;

  const GeminiApiKeyStore({this._storage = const FlutterSecureStorage()});

  String _storageKey(String provider) {
    switch (provider) {
      case 'gemini':
        return _geminiKey;
      case 'groq':
        return _groqKey;
      case 'cloudflare':
        return _cloudflareTokenKey;
      case 'openrouter':
        return _openRouterKey;

      case 'cerebras':
        return _cerebrasKey;

      case 'mistral':
        return _mistralKey;

      case 'nvidia':
        return _nvidiaKey;
      default:
        throw ArgumentError('Unsupported AI provider: $provider');
    }
  }

  Future<String?> _readKey(String key) async {
    final value = await _storage.read(key: key);
    final normalized = value?.trim();
    return normalized == null || normalized.isEmpty ? null : normalized;
  }

  Future<String?> readProviderApiKey(String provider) {
    return _readKey(_storageKey(provider));
  }

  Future<void> saveProviderApiKey(String provider, String apiKey) async {
    final normalized = apiKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError('API key is required.');
    }
    await _storage.write(key: _storageKey(provider), value: normalized);
  }

  Future<void> deleteProviderApiKey(String provider) {
    return _storage.delete(key: _storageKey(provider));
  }

  Future<String?> readCloudflareAccountId() {
    return _readKey(_cloudflareAccountIdKey);
  }

  Future<void> saveCloudflareAccountId(String accountId) async {
    final normalized = accountId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError('Cloudflare Account ID is required.');
    }
    await _storage.write(key: _cloudflareAccountIdKey, value: normalized);
  }

  Future<void> deleteCloudflareAccountId() {
    return _storage.delete(key: _cloudflareAccountIdKey);
  }

  Future<bool> readAutoFallback() async {
    final value = await _storage.read(key: _autoFallbackKey);

    // Default to ON for existing installations.
    if (value == null) {
      return true;
    }

    return value.trim().toLowerCase() != 'false';
  }

  Future<void> saveAutoFallback(bool enabled) {
    return _storage.write(
      key: _autoFallbackKey,
      value: enabled ? 'true' : 'false',
    );
  }

  Future<String> readPreferredProvider() async {
    final value = await _storage.read(key: _preferredProviderKey);

    const supported = {
      'gemini',
      'groq',
      'cloudflare',
      'openrouter',
      'cerebras',
      'mistral',
      'nvidia',
    };

    final normalized = value?.trim().toLowerCase();

    if (normalized == null || !supported.contains(normalized)) {
      return 'gemini';
    }

    return normalized;
  }

  Future<void> savePreferredProvider(String provider) async {
    final normalized = provider.trim().toLowerCase();

    const supported = {
      'gemini',
      'groq',
      'cloudflare',
      'openrouter',
      'cerebras',
      'mistral',
      'nvidia',
    };

    if (!supported.contains(normalized)) {
      throw ArgumentError('Unsupported AI provider: $provider');
    }

    await _storage.write(key: _preferredProviderKey, value: normalized);
  }

  // Backward-compatible Gemini helpers used by Live Voice and older tests.
  Future<String?> read() => readProviderApiKey('gemini');
  Future<void> save(String apiKey) => saveProviderApiKey('gemini', apiKey);
  Future<void> delete() => deleteProviderApiKey('gemini');
}
