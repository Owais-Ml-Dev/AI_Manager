bool looksLikeTaskAction(String message) {
  final text = message.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

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
    RegExp(r'^(create|add|schedule|make|set|plan)\b'),

    RegExp(r'\bremind me\b'),

    RegExp(r'\bset (a )?reminder\b'),

    // Update
    RegExp(r'^(edit|update|change|rename|reschedule|move)\b'),

    // Complete / Delete
    RegExp(r'^(complete|finish|delete|remove|cancel|stop)\b'),

    RegExp(r'\bmark\b.*\b(done|complete|completed)\b'),

    // Read/list
    RegExp(r'\b(show|list|display)\b.*\btasks?\b'),

    RegExp(r'\bwhat\b.*\bmy tasks?\b'),

    RegExp(r'\bhow many\b.*\btasks?\b'),
  ];

  if (commandPatterns.any((pattern) => pattern.hasMatch(text))) {
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

  if (RegExp(r'\btasks?\b').hasMatch(text)) {
    return true;
  }

  if (RegExp(r'\breminders?\b').hasMatch(text)) {
    return true;
  }

  return false;
}

bool looksLikeCreateTaskAction(String message) {
  final text = message.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

  if (text.isEmpty) {
    return false;
  }

  // General explanation questions must stay normal chat.
  if (RegExp(r'^(how do i|how can i|why|explain|tell me about)\b')
      .hasMatch(text)) {
    return false;
  }

  // Never route non-create task operations into the batch-create API.
  if (RegExp(
    r'\b(edit|update|change|rename|reschedule|move|complete|finish|delete|remove|cancel|stop|show|list|display)\b',
  ).hasMatch(text)) {
    return false;
  }

  if (RegExp(r'\bmark\b.*\b(done|complete|completed)\b').hasMatch(text)) {
    return false;
  }

  // Explicit create language.
  if (RegExp(r'^(create|add|schedule|make|set|plan)\b').hasMatch(text) ||
      RegExp(r'\bremind me\b').hasMatch(text) ||
      RegExp(r'\bset (a )?reminder\b').hasMatch(text)) {
    return true;
  }

  // Preserve the existing "Gym task" / "Medicine reminder" shorthand.
  // At this point known read/update/delete/complete verbs were excluded above.
  return RegExp(r'\btasks?\b').hasMatch(text) ||
      RegExp(r'\breminders?\b').hasMatch(text);
}

bool shouldInterruptTaskDraft(String message) {
  final text = message.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');

  if (text.isEmpty) {
    return false;
  }

  // A clear read-only task command is a NEW command,
  // even if the Assistant is currently waiting for a
  // duration, repeat rule, reminder, etc.
  return RegExp(r'\b(show|list|display)\b.*\btasks?\b').hasMatch(text) ||
      RegExp(r'\bwhat\b.*\bmy tasks?\b').hasMatch(text) ||
      RegExp(r'\bhow many\b.*\btasks?\b').hasMatch(text);
}

enum ActiveTaskControlIntent {
  none,
  discardCurrent,
  discardRemaining,
  skipCurrent,
  startNewTask,
  ambiguousStop,
}

String _normalizeTaskControlIntent(String message) {
  return message
      .trim()
      .toLowerCase()
      .replaceAll(RegExp(r'[.!?]+$'), '')
      .replaceAll(RegExp(r'\s+'), ' ');
}

/// Detect conversational control requests only while the UI already owns an
/// unfinished task flow. This deliberately does NOT mutate any state.
///
/// Clear requests map to one confirmation. Generic words such as "cancel" or
/// "stop" stay ambiguous so the user chooses Skip vs Discard explicitly.
ActiveTaskControlIntent detectActiveTaskControlIntent(String message) {
  final text = _normalizeTaskControlIntent(message);
  if (text.isEmpty) return ActiveTaskControlIntent.none;

  // "I want to start a new task" must never become an answer to the current
  // draft question.
  if (RegExp(
    r'\b(start|create|make|work on)\b.*\b(new|another|different)\b.*\btask\b',
  ).hasMatch(text)) {
    return ActiveTaskControlIntent.startNewTask;
  }

  final destructiveVerb = RegExp(
    r'\b(discard|cancel|abort|drop|remove|delete)\b',
  );
  final allReference = RegExp(r'\b(all|everything|remaining|rest)\b');
  final taskReference = RegExp(r'\b(tasks?|batch|everything)\b');

  // "discard all the tasks", "abort everything", "discard the remaining
  // tasks", "cancel the rest of the batch".
  if (destructiveVerb.hasMatch(text) &&
      allReference.hasMatch(text) &&
      taskReference.hasMatch(text)) {
    return ActiveTaskControlIntent.discardRemaining;
  }

  // Also accept the natural order: "all remaining tasks can be discarded".
  if (allReference.hasMatch(text) &&
      taskReference.hasMatch(text) &&
      destructiveVerb.hasMatch(text)) {
    return ActiveTaskControlIntent.discardRemaining;
  }

  // Explicit current-task discard. Keep generic "cancel this" ambiguous.
  if (RegExp(r'\b(discard|drop|remove|delete)\b.*\b(this|current)\b.*\btask\b')
          .hasMatch(text) ||
      RegExp(r'\b(discard|drop|remove|delete)\b.*\bthis one\b')
          .hasMatch(text)) {
    return ActiveTaskControlIntent.discardCurrent;
  }

  // Explicit skip/defer language.
  if (RegExp(r'\b(skip|defer|postpone)\b.*\b(this|current)?\s*task\b')
          .hasMatch(text) ||
      RegExp(
        r"\b(i )?(do not|don't|dont) want to (do|continue|finish)\b.*\btask\b.*\b(now|right now|at the moment)\b",
      ).hasMatch(text) ||
      RegExp(r'\bdo (this|the) task later\b').hasMatch(text)) {
    return ActiveTaskControlIntent.skipCurrent;
  }

  // Generic stop/cancel language is intentionally ambiguous. It must not be
  // confused with a named task operation such as "cancel dentist task".
  if (RegExp(
    r"^(can we |could we |please |let'?s |i want to )?"
    r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)'
    r'( this| this task| the task| current task)?$',
  ).hasMatch(text)) {
    return ActiveTaskControlIntent.ambiguousStop;
  }

  return ActiveTaskControlIntent.none;
}
