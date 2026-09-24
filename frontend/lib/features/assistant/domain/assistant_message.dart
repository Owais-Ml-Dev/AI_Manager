class AssistantMessage {
  final String text;
  final bool fromUser;
  final String? model;

  const AssistantMessage({
    required this.text,
    required this.fromUser,
    this.model,
  });
}
