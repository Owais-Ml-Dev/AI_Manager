from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit('Usage: python apply_frontend_task_control_step3b.py <frontend_dir>')

frontend = Path(sys.argv[1]).resolve()
intent = frontend / 'lib/features/assistant/domain/assistant_intent.dart'
repo = frontend / 'lib/features/assistant/data/assistant_repository.dart'
screen = frontend / 'lib/features/assistant/presentation/assistant_screen.dart'
test = frontend / 'test/assistant_task_control_intent_test.dart'

for path in (intent, repo, screen):
    if not path.exists():
        raise RuntimeError(f'Missing expected file: {path}')
    backup = path.with_name(path.name + '.before_task_control_step3b.bak')
    if not backup.exists():
        shutil.copy2(path, backup)


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f'Could not find expected block for {label}.')
    return text.replace(old, new, 1)


# =====================================================================
# 1) Deterministic natural-language task-control intent classifier.
# =====================================================================
intent_text = read(intent)
if 'enum ActiveTaskControlIntent {' not in intent_text:
    intent_text = intent_text.rstrip() + r'''


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
  final allReference = RegExp(
    r'\b(all|everything|remaining|rest)\b',
  );
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
  if (RegExp(
    r'\b(discard|drop|remove|delete)\b.*\b(this|current)\b.*\btask\b',
  ).hasMatch(text) ||
      RegExp(
        r'\b(discard|drop|remove|delete)\b.*\bthis one\b',
      ).hasMatch(text)) {
    return ActiveTaskControlIntent.discardCurrent;
  }

  // Explicit skip/defer language.
  if (RegExp(
    r'\b(skip|defer|postpone)\b.*\b(this|current)?\s*task\b',
  ).hasMatch(text) ||
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
    r'(cancel|stop|quit|exit|abort|leave|never mind|nevermind|give up)"
    r'( this| this task| the task| current task)?$",
  ).hasMatch(text)) {
    return ActiveTaskControlIntent.ambiguousStop;
  }

  return ActiveTaskControlIntent.none;
}
'''
    write(intent, intent_text)


# =====================================================================
# 2) Repository calls for Skip for Now and Discard Remaining.
# =====================================================================
repo_text = read(repo)
repo_anchor = '  Future<AssistantCommandPreview> previewTaskCommand(\n'
if 'Future<AssistantTaskBatchResolutionResult> deferTaskBatch(' not in repo_text:
    methods = r'''  Future<AssistantTaskBatchResolutionResult> deferTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/defer',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch skip result.',
      );
    }

    return resolution;
  }

  Future<Map<String, dynamic>> abortTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/abort',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final data = _asMap(result);
    if (data['batch_id']?.toString().isEmpty != false ||
        data['batch_status']?.toString() != 'aborted') {
      throw const ApiException(
        message: 'The backend returned an invalid batch discard result.',
      );
    }

    return data;
  }

'''
    if repo_anchor not in repo_text:
        raise RuntimeError('Could not find previewTaskCommand repository anchor.')
    repo_text = repo_text.replace(repo_anchor, methods + repo_anchor, 1)
    write(repo, repo_text)


# =====================================================================
# 3) Assistant screen state + interception before task answers reach backend.
# =====================================================================
screen_text = read(screen)

# Ensure we retain the active Task N / total for dynamic confirmation labels,
# even if the optional Step 2F polish patch was not applied.
if '_activeBatchTaskNumber' not in screen_text:
    state_anchor = '  String? _activeBatchId;\n'
    if state_anchor not in screen_text:
        raise RuntimeError('Could not find _activeBatchId state field.')
    screen_text = screen_text.replace(
        state_anchor,
        state_anchor + '  int? _activeBatchTaskNumber;\n  int? _activeBatchTotalTasks;\n',
        1,
    )

    apply_anchor = '    _activeBatchId = batchId;\n    _activeDraftId = preview.draftId;\n'
    if apply_anchor not in screen_text:
        raise RuntimeError('Could not find _applyBatchDraft state anchor.')
    screen_text = screen_text.replace(
        apply_anchor,
        '    _activeBatchId = batchId;\n'
        '    _activeBatchTaskNumber = currentTaskNumber;\n'
        '    _activeBatchTotalTasks = totalTasks;\n'
        '    _activeDraftId = preview.draftId;\n',
        1,
    )

if '_pendingTaskControlIntent' not in screen_text:
    field_anchor = '  int? _activeBatchTotalTasks;\n'
    if field_anchor not in screen_text:
        raise RuntimeError('Could not find active batch total field.')
    screen_text = screen_text.replace(
        field_anchor,
        field_anchor +
        '  ActiveTaskControlIntent? _pendingTaskControlIntent;\n',
        1,
    )

# Remove the old exact-word cancellation shortcut. It changed local state
# immediately and therefore violated the new confirmation requirement.
legacy_cancel = '''    final normalized = message.toLowerCase();
    if (_activeBatchId == null &&
        _activeDraftId != null &&
        const {
          'cancel',
          'never mind',
          'nevermind',
          'stop',
        }.contains(normalized)) {
      _messageController.clear();
      _cancelCommand();
      return;
    }

'''
if legacy_cancel in screen_text:
    screen_text = screen_text.replace(legacy_cancel, '', 1)

# Detect task-control before clearing the current suggestion chips. Continue
# must restore the exact UI state the user was in.
send_marker = '''    setState(() {
      _suggestions = const [];
'''
if 'final taskControlIntent =' not in screen_text:
    if send_marker not in screen_text:
        raise RuntimeError('Could not find Assistant send-state block.')
    send_replacement = '''    final taskControlIntent =
        (_activeBatchId != null || _activeDraftId != null)
        ? detectActiveTaskControlIntent(message)
        : ActiveTaskControlIntent.none;
    final preserveTaskFlowUi =
        taskControlIntent != ActiveTaskControlIntent.none;

    setState(() {
      if (!preserveTaskFlowUi) {
        _suggestions = const [];
      }
'''
    screen_text = screen_text.replace(send_marker, send_replacement, 1)

route_anchor = '''    if (_activeBatchId != null) {
      await _continueTaskBatch(message);
'''
if 'if (taskControlIntent != ActiveTaskControlIntent.none)' not in screen_text:
    if route_anchor not in screen_text:
        raise RuntimeError('Could not find active batch routing block.')
    intercept = '''    if (taskControlIntent != ActiveTaskControlIntent.none) {
      _presentTaskControlConfirmation(taskControlIntent);
      _finishSending();
      return;
    }

'''
    screen_text = screen_text.replace(route_anchor, intercept + route_anchor, 1)


# =====================================================================
# 4) Confirmation/action handlers.
# =====================================================================
if 'void _presentTaskControlConfirmation(' not in screen_text:
    method_anchor = '  void _finishSending() {\n'
    if method_anchor not in screen_text:
        raise RuntimeError('Could not find _finishSending method anchor.')

    methods = r'''  void _presentTaskControlConfirmation(
    ActiveTaskControlIntent intent,
  ) {
    var effectiveIntent = intent;
    String prompt;

    // Skip-for-now requires another unresolved task to move to. For legacy
    // non-batch drafts, offer a safe choice instead of silently converting
    // "skip" into "discard".
    if (intent == ActiveTaskControlIntent.skipCurrent &&
        _activeBatchId == null) {
      effectiveIntent = ActiveTaskControlIntent.ambiguousStop;
      prompt =
          'This task is not part of a multi-task batch. What would you like to do?';
    } else if (intent == ActiveTaskControlIntent.discardRemaining &&
        _activeBatchId == null) {
      effectiveIntent = ActiveTaskControlIntent.discardCurrent;
      prompt = 'Do you want to discard this task?';
    } else {
      prompt = switch (intent) {
        ActiveTaskControlIntent.discardCurrent =>
          'Do you want to discard this task?',
        ActiveTaskControlIntent.discardRemaining =>
          'Do you want to discard all remaining tasks?',
        ActiveTaskControlIntent.skipCurrent =>
          'Do you want to skip this task?',
        ActiveTaskControlIntent.startNewTask => _activeBatchId != null
            ? 'You still have unfinished tasks. Do you want to discard all remaining tasks and start a new task?'
            : 'Do you want to discard this task and start a new task?',
        ActiveTaskControlIntent.ambiguousStop =>
          'What would you like to do?',
        ActiveTaskControlIntent.none => '',
      };
    }

    if (prompt.isEmpty || !mounted) return;

    setState(() {
      _pendingTaskControlIntent = effectiveIntent;
      _messages.add(
        AssistantMessage(
          text: prompt,
          fromUser: false,
        ),
      );
    });
    _scrollToBottom();
  }

  void _continueTaskAfterControlPrompt() {
    if (_sending) return;

    final current = _activeBatchTaskNumber;
    final total = _activeBatchTotalTasks;

    setState(() {
      _pendingTaskControlIntent = null;
      _messages.add(
        AssistantMessage(
          text: current != null && total != null
              ? 'Continuing Task $current of $total.'
              : 'Continuing the current task.',
          fromUser: false,
        ),
      );
    });
    _scrollToBottom();
  }

  Future<void> _handleTaskControlResolution(
    AssistantTaskBatchResolutionResult resolution, {
    required String message,
  }) async {
    if (!mounted) return;

    setState(() {
      _pendingTaskControlIntent = null;
      _pendingCommand = null;
      _selectedMatchId = null;
      _suggestions = const [];
      _activeDraftId = null;
      _messages.add(
        AssistantMessage(
          text: message,
          fromUser: false,
        ),
      );
    });

    if (resolution.allDone) {
      await _forgetActiveBatch();
      if (!mounted) return;

      setState(() {
        _activeBatchId = null;
        _activeBatchTaskNumber = null;
        _activeBatchTotalTasks = null;
        _activeDraftId = null;
        _pendingCommand = null;
        _selectedMatchId = null;
        _suggestions = const [];
        _messages.add(
          const AssistantMessage(
            text: 'The task batch is complete.',
            fromUser: false,
          ),
        );
      });
      _scrollToBottom();
      return;
    }

    await _rememberActiveBatch(resolution.batchId);
    if (!mounted) return;

    var nextTask = resolution.nextTask;
    if (nextTask == null) {
      try {
        nextTask = await ref
            .read(assistantRepositoryProvider)
            .getActiveTaskBatch(resolution.batchId);
      } on ApiException catch (error) {
        _activeBatchId = resolution.batchId;
        _addError(
          'The current task was updated, but the next task could not be loaded: '
          '${error.message}',
        );
        return;
      } catch (_) {
        _activeBatchId = resolution.batchId;
        _addError(
          'The current task was updated, but the next task could not be loaded.',
        );
        return;
      }
    }

    if (!mounted) return;

    _applyBatchDraft(
      batchId: nextTask.batchId,
      currentTaskNumber: nextTask.currentTaskNumber,
      totalTasks: nextTask.totalTasks,
      preview: nextTask.activeDraft,
    );
  }

  Future<void> _confirmSkipCurrentTask() async {
    final batchId = _activeBatchId;
    final draftId = _activeDraftId;
    if (_sending || batchId == null || draftId == null) return;

    setState(() => _sending = true);
    try {
      final resolution = await ref
          .read(assistantRepositoryProvider)
          .deferTaskBatch(batchId: batchId, draftId: draftId);

      await _handleTaskControlResolution(
        resolution,
        message:
            'Skipped Task ${resolution.resolvedTaskNumber} for now. I will return to it after the other unfinished tasks.',
      );
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not skip that task for now.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _confirmDiscardCurrentTask() async {
    final batchId = _activeBatchId;
    final draftId = _activeDraftId;
    if (_sending || draftId == null) return;

    // Legacy single-command drafts are local-only flows. They still require
    // confirmation, but do not have a server-owned batch to advance.
    if (batchId == null) {
      setState(() => _pendingTaskControlIntent = null);
      _cancelCommand();
      return;
    }

    setState(() => _sending = true);
    try {
      final resolution = await ref
          .read(assistantRepositoryProvider)
          .cancelTaskBatch(batchId: batchId, draftId: draftId);

      await _handleTaskControlResolution(
        resolution,
        message:
            'Discarded Task ${resolution.resolvedTaskNumber}. No task was created from it.',
      );
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not discard that task.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _confirmDiscardRemainingTasks({
    bool startNewTask = false,
  }) async {
    final batchId = _activeBatchId;
    final draftId = _activeDraftId;
    if (_sending || draftId == null) return;

    if (batchId == null) {
      setState(() => _pendingTaskControlIntent = null);
      _cancelCommand();
      if (startNewTask && mounted) {
        setState(() {
          _messages.add(
            const AssistantMessage(
              text: 'What task would you like to create?',
              fromUser: false,
            ),
          );
        });
      }
      return;
    }

    final current = _activeBatchTaskNumber ?? 1;
    final total = _activeBatchTotalTasks ?? current;

    setState(() => _sending = true);
    try {
      await ref
          .read(assistantRepositoryProvider)
          .abortTaskBatch(batchId: batchId, draftId: draftId);

      await _forgetActiveBatch();
      if (!mounted) return;

      setState(() {
        _pendingTaskControlIntent = null;
        _activeBatchId = null;
        _activeBatchTaskNumber = null;
        _activeBatchTotalTasks = null;
        _activeDraftId = null;
        _pendingCommand = null;
        _selectedMatchId = null;
        _suggestions = const [];
        _messages.add(
          AssistantMessage(
            text: current <= 1
                ? 'Discarded all remaining tasks. Previously saved tasks were not changed.'
                : 'Discarded the remaining unfinished tasks (Tasks $current-$total). Previously saved tasks were not changed.',
            fromUser: false,
          ),
        );
        if (startNewTask) {
          _messages.add(
            const AssistantMessage(
              text: 'What task would you like to create?',
              fromUser: false,
            ),
          );
        }
      });
      _scrollToBottom();
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not discard the remaining tasks.');
    } finally {
      _finishSending();
    }
  }

'''
    screen_text = screen_text.replace(method_anchor, methods + method_anchor, 1)


# =====================================================================
# 5) Confirmation action card. Existing review/suggestion UI is temporarily
#    hidden so the destructive action cannot race with a task answer.
# =====================================================================
if '_taskControlConfirmationCard()' not in screen_text:
    build_anchor = '          if (_pendingCommand != null)\n'
    if build_anchor not in screen_text:
        raise RuntimeError('Could not find command preview build anchor.')
    screen_text = screen_text.replace(
        build_anchor,
        '          if (_pendingTaskControlIntent != null)\n'
        '            _taskControlConfirmationCard(),\n'
        '          if (_pendingTaskControlIntent == null && _pendingCommand != null)\n',
        1,
    )

# Hide quick replies while the control confirmation is open.
suggestion_old = 'if (_suggestions.isNotEmpty && !_sending && _pendingCommand == null)'
if suggestion_old in screen_text:
    screen_text = screen_text.replace(
        suggestion_old,
        'if (_pendingTaskControlIntent == null &&\n'
        '              _suggestions.isNotEmpty &&\n'
        '              !_sending &&\n'
        '              _pendingCommand == null)',
        1,
    )

if 'Widget _taskControlConfirmationCard() {' not in screen_text:
    widget_anchor = '  Widget _batchProgressBanner() {\n'
    if widget_anchor not in screen_text:
        # Step 2F may not exist; _emptyState is present in every known version.
        widget_anchor = '  Widget _emptyState() {\n'
    if widget_anchor not in screen_text:
        raise RuntimeError('Could not find widget insertion anchor.')

    widget = r'''  Widget _taskControlConfirmationCard() {
    final intent = _pendingTaskControlIntent;
    if (intent == null) return const SizedBox.shrink();

    final colors = AppColors.of(context);
    final current = _activeBatchTaskNumber ?? 1;
    final total = _activeBatchTotalTasks ?? current;
    final inBatch = _activeBatchId != null;

    final buttons = <Widget>[];

    void addButton(
      String label,
      VoidCallback onPressed, {
      bool primary = false,
    }) {
      buttons.add(
        primary
            ? FilledButton(
                onPressed: _sending ? null : onPressed,
                child: Text(label),
              )
            : OutlinedButton(
                onPressed: _sending ? null : onPressed,
                child: Text(label),
              ),
      );
    }

    switch (intent) {
      case ActiveTaskControlIntent.discardCurrent:
        addButton('Keep Task', _continueTaskAfterControlPrompt);
        addButton(
          inBatch ? 'Discard Task $current' : 'Discard Task',
          () => _confirmDiscardCurrentTask(),
          primary: true,
        );
        break;
      case ActiveTaskControlIntent.discardRemaining:
        addButton('Keep Tasks', _continueTaskAfterControlPrompt);
        addButton(
          current <= 1
              ? 'Discard Remaining Tasks'
              : 'Discard Tasks $current-$total',
          () => _confirmDiscardRemainingTasks(),
          primary: true,
        );
        break;
      case ActiveTaskControlIntent.skipCurrent:
        addButton('Continue Task', _continueTaskAfterControlPrompt);
        addButton(
          'Skip Task $current for Now',
          () => _confirmSkipCurrentTask(),
          primary: true,
        );
        break;
      case ActiveTaskControlIntent.startNewTask:
        addButton('Continue Current Tasks', _continueTaskAfterControlPrompt);
        addButton(
          inBatch
              ? 'Discard Remaining & Start New'
              : 'Discard Task & Start New',
          () => _confirmDiscardRemainingTasks(startNewTask: true),
          primary: true,
        );
        break;
      case ActiveTaskControlIntent.ambiguousStop:
        addButton('Continue Task', _continueTaskAfterControlPrompt);
        if (inBatch) {
          addButton(
            'Skip Task $current for Now',
            () => _confirmSkipCurrentTask(),
          );
        }
        addButton(
          inBatch ? 'Discard Task $current' : 'Discard Current Task',
          () => _confirmDiscardCurrentTask(),
        );
        if (inBatch) {
          addButton(
            current <= 1
                ? 'Discard Remaining Tasks'
                : 'Discard Tasks $current-$total',
            () => _confirmDiscardRemainingTasks(),
            primary: true,
          );
        }
        break;
      case ActiveTaskControlIntent.none:
        break;
    }

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.surfaceElevated,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.border),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        alignment: WrapAlignment.end,
        children: buttons,
      ),
    );
  }

'''
    screen_text = screen_text.replace(widget_anchor, widget + widget_anchor, 1)

# Disable typed answers while confirmation buttons are waiting. This prevents
# "yes" or another phrase from accidentally reaching /continue.
text_field_anchor = '                controller: _messageController,\n'
if 'enabled: _pendingTaskControlIntent == null,' not in screen_text:
    if text_field_anchor not in screen_text:
        raise RuntimeError('Could not find Assistant composer TextField.')
    screen_text = screen_text.replace(
        text_field_anchor,
        text_field_anchor +
        '                enabled: _pendingTaskControlIntent == null,\n',
        1,
    )

write(screen, screen_text)


# =====================================================================
# 6) Focused classifier tests.
# =====================================================================
test.parent.mkdir(parents=True, exist_ok=True)
test.write_text(r'''import 'package:flutter_test/flutter_test.dart';
import 'package:ai_task_manager/features/assistant/domain/assistant_intent.dart';

void main() {
  group('active task-control intent', () {
    test('detects explicit current discard', () {
      expect(
        detectActiveTaskControlIntent('Can we discard this task?'),
        ActiveTaskControlIntent.discardCurrent,
      );
      expect(
        detectActiveTaskControlIntent('Please delete this current task'),
        ActiveTaskControlIntent.discardCurrent,
      );
    });

    test('detects discard remaining/all', () {
      expect(
        detectActiveTaskControlIntent('Can we discard all the tasks?'),
        ActiveTaskControlIntent.discardRemaining,
      );
      expect(
        detectActiveTaskControlIntent('Abort everything'),
        ActiveTaskControlIntent.discardRemaining,
      );
      expect(
        detectActiveTaskControlIntent('Discard the remaining tasks'),
        ActiveTaskControlIntent.discardRemaining,
      );
    });

    test('detects skip for now', () {
      expect(
        detectActiveTaskControlIntent('Can we skip this task?'),
        ActiveTaskControlIntent.skipCurrent,
      );
      expect(
        detectActiveTaskControlIntent("I don't want to do this task now."),
        ActiveTaskControlIntent.skipCurrent,
      );
    });

    test('start-new request interrupts unfinished flow', () {
      expect(
        detectActiveTaskControlIntent('I want to start a new task.'),
        ActiveTaskControlIntent.startNewTask,
      );
    });

    test('generic stop and cancel remain ambiguous', () {
      expect(
        detectActiveTaskControlIntent("Let's stop this task."),
        ActiveTaskControlIntent.ambiguousStop,
      );
      expect(
        detectActiveTaskControlIntent('Cancel this.'),
        ActiveTaskControlIntent.ambiguousStop,
      );
      expect(
        detectActiveTaskControlIntent('exit'),
        ActiveTaskControlIntent.ambiguousStop,
      );
    });

    test('does not steal named task operations or normal answers', () {
      expect(
        detectActiveTaskControlIntent('cancel dentist task tomorrow'),
        ActiveTaskControlIntent.none,
      );
      expect(
        detectActiveTaskControlIntent('stop gym reminders'),
        ActiveTaskControlIntent.none,
      );
      expect(
        detectActiveTaskControlIntent('2'),
        ActiveTaskControlIntent.none,
      );
      expect(
        detectActiveTaskControlIntent('Every day'),
        ActiveTaskControlIntent.none,
      );
    });
  });
}
''', encoding='utf-8')

print('Frontend Step 3B applied successfully.')
print('Added: natural-language task control + confirmation UI.')
print('No task state changes occur until a confirmation button is pressed.')
print('Added repository calls for /defer and /abort.')
print('Added focused intent tests.')
