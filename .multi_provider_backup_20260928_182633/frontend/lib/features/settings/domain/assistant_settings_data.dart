class AssistantSettingsData {
  final String model;
  final String message;
  final bool available;
  final bool configured;
  final bool storedKeyConfigured;
  final String? keyHint;

  const AssistantSettingsData({
    required this.model,
    required this.message,
    required this.available,
    required this.configured,
    required this.storedKeyConfigured,
    required this.keyHint,
  });
}
