bool looksLikeTaskAction(String message) {
  final text = message
      .trim()
      .toLowerCase()
      .replaceAll(
        RegExp(r'\s+'),
        ' ',
      );

  if (text.isEmpty) {
    return false;
  }

  // ------------------------------------------------------
  // NORMAL EXPLANATION / INFORMATION QUESTIONS
  // ------------------------------------------------------

  final normalQuestion = RegExp(
    r'^(how do i|how can i|why|explain|tell me about)\b',
  );

  if (normalQuestion.hasMatch(text) &&
      !text.contains('my task') &&
      !text.contains('my tasks')) {
    return false;
  }

  // ------------------------------------------------------
  // EXPLICIT TASK COMMANDS
  // ------------------------------------------------------

  final commandPatterns = <RegExp>[
    // Create
    RegExp(
      r'^(create|add|schedule|make|set|plan)\b',
    ),

    RegExp(
      r'\bremind me\b',
    ),

    RegExp(
      r'\bset (a )?reminder\b',
    ),

    // Update
    RegExp(
      r'^(edit|update|change|rename|reschedule|move)\b',
    ),

    // Complete / Delete
    RegExp(
      r'^(complete|finish|delete|remove|cancel|stop)\b',
    ),

    RegExp(
      r'\bmark\b.*\b(done|complete|completed)\b',
    ),

    // Read/list
    RegExp(
      r'\b(show|list)\b.*\btasks?\b',
    ),

    RegExp(
      r'\bwhat\b.*\bmy tasks?\b',
    ),

    RegExp(
      r'\bhow many\b.*\btasks?\b',
    ),
  ];

  if (commandPatterns.any(
    (pattern) => pattern.hasMatch(text),
  )) {
    return true;
  }

  // ------------------------------------------------------
  // NATURAL TASK PHRASES
  // ------------------------------------------------------
  //
  // Examples:
  //
  // "Swimming task"
  // "Gym task"
  // "Morning workout task"
  // "Medicine reminder"
  // "Call mom reminder"
  //
  // These should enter the structured task-command flow
  // even when the user does not explicitly say "create".
  //

  if (RegExp(
    r'\btasks?\b',
  ).hasMatch(text)) {
    return true;
  }

  if (RegExp(
    r'\breminders?\b',
  ).hasMatch(text)) {
    return true;
  }

  return false;
}
