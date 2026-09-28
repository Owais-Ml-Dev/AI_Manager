class AssistantProviderSettings {
  final String provider;
  final String label;
  final String model;
  final bool configured;
  final String? keyHint;
  final String? accountId;
  final bool requiresAccountId;

  const AssistantProviderSettings({
    required this.provider,
    required this.label,
    required this.model,
    required this.configured,
    required this.keyHint,
    this.accountId,
    this.requiresAccountId = false,
  });
}

class AssistantSettingsData {
  final List<AssistantProviderSettings> providers;
  final String message;

  const AssistantSettingsData({required this.providers, this.message = ''});

  AssistantProviderSettings? provider(String name) {
    for (final item in providers) {
      if (item.provider == name) return item;
    }
    return null;
  }

  bool get anyProviderConfigured => providers.any((item) => item.configured);

  // Compatibility getters for existing callers.
  String get model => provider('gemini')?.model ?? 'gemini-3.8-flash';
  bool get configured => anyProviderConfigured;
  bool get available => anyProviderConfigured;
  bool get storedKeyConfigured => provider('gemini')?.configured ?? false;
  String? get keyHint => provider('gemini')?.keyHint;
}
