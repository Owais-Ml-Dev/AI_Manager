class AssistantMessage {
  final String text;
  final bool fromUser;
  final String? provider;
  final String? model;
  final bool fallbackUsed;

  /// True only for user messages that can safely become a new top-level
  /// request when edited. Follow-up answers inside a server-owned task draft
  /// deliberately keep this false.
  final bool allowEdit;

  /// Original user text that may safely be retried for a normal AI reply.
  /// Task-flow messages do not populate this because retrying them blindly
  /// can advance a server-side draft twice.
  final String? retryText;

  const AssistantMessage({
    required this.text,
    required this.fromUser,
    this.provider,
    this.model,
    this.fallbackUsed = false,
    this.allowEdit = false,
    this.retryText,
  });
}
