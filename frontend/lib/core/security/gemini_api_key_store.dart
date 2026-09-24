import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class GeminiApiKeyStore {
  static const _storageKey = 'gemini_api_key';

  final FlutterSecureStorage _storage;

  const GeminiApiKeyStore({this._storage = const FlutterSecureStorage()});

  Future<String?> read() async {
    final value = await _storage.read(key: _storageKey);

    final normalized = value?.trim();

    if (normalized == null || normalized.isEmpty) {
      return null;
    }

    return normalized;
  }

  Future<void> save(String apiKey) async {
    final normalized = apiKey.trim();

    if (normalized.isEmpty) {
      throw ArgumentError('Gemini API key is required.');
    }

    await _storage.write(key: _storageKey, value: normalized);
  }

  Future<void> delete() {
    return _storage.delete(key: _storageKey);
  }
}
