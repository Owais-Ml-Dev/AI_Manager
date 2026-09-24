import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client_provider.dart';
import '../../../core/security/gemini_api_key_store_provider.dart';
import '../data/assistant_repository.dart';

final assistantRepositoryProvider = Provider<AssistantRepository>((ref) {
  return AssistantRepository(
    ref.watch(apiClientProvider),
    ref.watch(geminiApiKeyStoreProvider),
  );
});
