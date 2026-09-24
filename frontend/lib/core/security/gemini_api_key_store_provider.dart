import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'gemini_api_key_store.dart';

final geminiApiKeyStoreProvider = Provider<GeminiApiKeyStore>((ref) {
  return const GeminiApiKeyStore();
});
