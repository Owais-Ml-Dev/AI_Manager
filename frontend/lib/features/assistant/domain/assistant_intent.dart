bool looksLikeTaskAction(String message) {
  final text = message.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

  if (text.isEmpty) {
    return false;
  }

  // Questions asking for an explanation should stay
  // as normal chat.
  final normalQuestion = RegExp(
    r'^(how do i|how can i|why|explain|tell me about)\b',
  );

  if (normalQuestion.hasMatch(text) &&
      !text.contains('my task') &&
      !text.contains('my tasks')) {
    return false;
  }

  final patterns = [
    // Creating tasks.
    RegExp(r'^(create|add|schedule|make)\b'),

    RegExp(r'\bremind me\b'),

    RegExp(r'\bset (a )?reminder\b'),

    // Editing tasks.
    RegExp(r'^(edit|update|change|rename|reschedule)\b'),

    // Completing/deleting tasks.
    RegExp(r'^(complete|finish|delete|remove|cancel)\b'),

    RegExp(r'\bmark\b.*\b(done|complete|completed)\b'),

    // Reading task data.
    RegExp(r'\b(show|list)\b.*\btasks?\b'),

    RegExp(r'\bwhat\b.*\bmy tasks?\b'),

    RegExp(r'\bhow many\b.*\btasks?\b'),
  ];

  return patterns.any((pattern) => pattern.hasMatch(text));
}
