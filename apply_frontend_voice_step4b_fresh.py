from pathlib import Path
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def backup(path: Path) -> None:
    target = path.with_name(path.name + '.before_voice_step4b.bak')
    if not target.exists():
        shutil.copy2(path, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f'Could not find expected block for {label}.')
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index == -1:
        raise RuntimeError(f'Could not find start of {label}.')
    end_index = text.find(end, start_index)
    if end_index == -1:
        raise RuntimeError(f'Could not find end of {label}.')
    return text[:start_index] + replacement.rstrip() + '\n\n' + text[end_index:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python apply_frontend_voice_step4b.py <frontend_dir>')

    frontend = Path(sys.argv[1]).resolve()
    screen = frontend / 'lib/features/assistant/presentation/voice_mode_screen.dart'
    intent = frontend / 'lib/features/assistant/domain/assistant_intent.dart'
    repo = frontend / 'lib/features/assistant/data/assistant_repository.dart'

    for path in (screen, intent, repo):
        if not path.exists():
            raise RuntimeError(f'Missing required file: {path}')

    intent_text = read(intent)
    required_intent_tokens = [
        'enum ActiveTaskControlIntent',
        'detectActiveTaskControlIntent',
    ]
    missing_intent = [x for x in required_intent_tokens if x not in intent_text]
    if missing_intent:
        raise RuntimeError(
            'Voice Step 4B requires Frontend Step 3B task-control intent support. '
            f'Missing: {missing_intent}'
        )

    repo_text = read(repo)
    required_repo_tokens = [
        'Future<AssistantTaskBatchResolutionResult> deferTaskBatch(',
        'Future<AssistantTaskBatchResolutionResult> cancelTaskBatch(',
        'Future<Map<String, dynamic>> abortTaskBatch(',
    ]
    missing_repo = [x for x in required_repo_tokens if x not in repo_text]
    if missing_repo:
        raise RuntimeError(
            'Voice Step 4B requires the task-control repository methods. '
            f'Missing: {missing_repo}'
        )

    backup(screen)
    text = read(screen)

    if 'Future<void> _startVoiceTaskBatch(' not in text:
        raise RuntimeError(
            'Voice Step 4A is not installed. Apply and verify Step 4A before Step 4B.'
        )

    # -------------------------------------------------------------
    # Pending spoken task-control confirmation state.
    # -------------------------------------------------------------
    old_state = '''  AssistantCommandPreview? _pendingTaskPreview;\n\n  Timer? _taskTranscriptTimer;\n'''
    new_state = '''  AssistantCommandPreview? _pendingTaskPreview;\n\n  ActiveTaskControlIntent? _pendingVoiceTaskControlIntent;\n\n  String? _voiceTaskResumePrompt;\n\n  Timer? _taskTranscriptTimer;\n'''
    text = replace_once(text, old_state, new_state, 'voice task-control state')

    # -------------------------------------------------------------
    # Spoken control helpers.
    # -------------------------------------------------------------
    helper_anchor = '  Future<void> _processTaskUtterance(String utterance) async {'
    if 'Future<void> _beginVoiceTaskControl(' not in text:
        helper_index = text.find(helper_anchor)
        if helper_index == -1:
            raise RuntimeError('Could not find _processTaskUtterance anchor.')

        helpers = r'''  bool _isContinueTaskSpeech(String value) {
    final text = _normalizeTaskSpeech(value);

    const phrases = <String>{
      'continue',
      'continue task',
      'continue the task',
      'keep task',
      'keep the task',
      'keep tasks',
      'keep the tasks',
      'resume',
      'resume task',
      'go back',
      'no',
      'no keep it',
      'dont skip',
      'do not skip',
      'dont discard',
      'do not discard',
    };

    return phrases.contains(text) ||
        text.startsWith('continue ') ||
        text.startsWith('keep ');
  }

  ActiveTaskControlIntent _voiceControlSelection(String value) {
    final detected = detectActiveTaskControlIntent(value);
    if (detected != ActiveTaskControlIntent.none &&
        detected != ActiveTaskControlIntent.ambiguousStop) {
      return detected;
    }

    final text = _normalizeTaskSpeech(value);

    if (RegExp(r'\bskip\b').hasMatch(text)) {
      return ActiveTaskControlIntent.skipCurrent;
    }

    if (RegExp(r'\b(discard|delete|drop|remove|abort|cancel)\b')
        .hasMatch(text)) {
      if (RegExp(r'\b(all|remaining|rest|everything|batch)\b')
          .hasMatch(text)) {
        return ActiveTaskControlIntent.discardRemaining;
      }

      if (RegExp(r'\b(current|this|task|one)\b').hasMatch(text)) {
        return ActiveTaskControlIntent.discardCurrent;
      }
    }

    if (RegExp(r'\b(start|create|make)\b.*\b(new|another)\b.*\btask\b')
        .hasMatch(text)) {
      return ActiveTaskControlIntent.startNewTask;
    }

    return ActiveTaskControlIntent.none;
  }

  String _voiceControlPrompt(ActiveTaskControlIntent intent) {
    final current = _taskBatchCurrentTaskNumber ?? 1;
    final total = _taskBatchTotalTasks ?? current;

    switch (intent) {
      case ActiveTaskControlIntent.skipCurrent:
        if (total <= 1) {
          return 'Do you want to skip Task $current? '
              'Say yes to skip it, or say continue to keep working on it.';
        }
        return 'Do you want to skip Task $current for now? '
            'I will return to it after the other unfinished tasks. '
            'Say yes to skip it for now, or say continue to keep working on it.';

      case ActiveTaskControlIntent.discardCurrent:
        return 'Do you want to discard Task $current? '
            'This task will not return later. '
            'Say yes to discard it, or say continue to keep it.';

      case ActiveTaskControlIntent.discardRemaining:
        return 'Do you want to discard all unfinished tasks in this batch? '
            'Tasks already saved will not be changed. '
            'Say yes to discard the unfinished tasks, or say continue to keep them.';

      case ActiveTaskControlIntent.startNewTask:
        return 'You still have an unfinished task batch. '
            'Do you want to discard all unfinished tasks and start a new task? '
            'Tasks already saved will not be changed. '
            'Say yes to discard them and start new, or say keep tasks.';

      case ActiveTaskControlIntent.ambiguousStop:
        return 'What would you like to do? '
            'Say continue task, skip current task, discard current task, '
            'or discard remaining tasks.';

      case ActiveTaskControlIntent.none:
        return 'Please continue with the current task.';
    }
  }

  Future<void> _beginVoiceTaskControl(
    ActiveTaskControlIntent intent,
  ) async {
    if (_taskBatchId == null) {
      return;
    }

    // Snapshot the last task question/review text before the control prompt
    // replaces the visible/spoken assistant transcript.
    final previous = _assistantTranscript.trim();
    if (_pendingVoiceTaskControlIntent == null && previous.isNotEmpty) {
      _voiceTaskResumePrompt = previous;
    }

    _pendingVoiceTaskControlIntent = intent;
    await _speakBackendText(_voiceControlPrompt(intent));
  }

  Future<void> _resumeVoiceTaskAfterControl() async {
    _pendingVoiceTaskControlIntent = null;

    final progress = _voiceTaskProgress();
    final previous = _voiceTaskResumePrompt?.trim();
    _voiceTaskResumePrompt = null;

    final parts = <String>[];
    if (progress.isNotEmpty) {
      parts.add('Continuing $progress');
    } else {
      parts.add('Continuing the current task.');
    }

    if (previous != null && previous.isNotEmpty) {
      parts.add(previous);
    } else {
      parts.add('Please continue with the current task.');
    }

    await _speakBackendText(parts.join(' '));
  }

  Future<void> _executeVoiceTaskControl(
    ActiveTaskControlIntent intent,
  ) async {
    final batchId = _taskBatchId;
    final draftId = _taskDraftId;

    if (batchId == null || draftId == null) {
      _pendingVoiceTaskControlIntent = null;
      _voiceTaskResumePrompt = null;
      await _speakBackendText(
        'I could not find an active task to change. Please try again.',
      );
      return;
    }

    _pendingVoiceTaskControlIntent = null;
    _voiceTaskResumePrompt = null;

    switch (intent) {
      case ActiveTaskControlIntent.skipCurrent:
        final total = _taskBatchTotalTasks ?? 1;
        final resolution = total <= 1
            ? await ref
                .read(assistantRepositoryProvider)
                .cancelTaskBatch(
                  batchId: batchId,
                  draftId: draftId,
                )
            : await ref
                .read(assistantRepositoryProvider)
                .deferTaskBatch(
                  batchId: batchId,
                  draftId: draftId,
                );

        await _handleVoiceBatchResolution(
          resolution,
          lead: total <= 1
              ? 'Skipped Task ${resolution.resolvedTaskNumber}. '
                  'No task was created from it.'
              : 'Skipped Task ${resolution.resolvedTaskNumber} for now. '
                  'I will return to it after the other unfinished tasks.',
        );
        return;

      case ActiveTaskControlIntent.discardCurrent:
        final resolution = await ref
            .read(assistantRepositoryProvider)
            .cancelTaskBatch(
              batchId: batchId,
              draftId: draftId,
            );

        await _handleVoiceBatchResolution(
          resolution,
          lead: 'Discarded Task ${resolution.resolvedTaskNumber}. '
              'No task was created from it.',
        );
        return;

      case ActiveTaskControlIntent.discardRemaining:
      case ActiveTaskControlIntent.startNewTask:
        await ref
            .read(assistantRepositoryProvider)
            .abortTaskBatch(
              batchId: batchId,
              draftId: draftId,
            );

        await _forgetVoiceBatch();
        final startNew = intent == ActiveTaskControlIntent.startNewTask;
        _clearTaskFlow();

        await _speakBackendText(
          startNew
              ? 'Discarded all unfinished tasks in the previous batch. '
                  'Tasks already saved were not changed. '
                  'What new task would you like to create?'
              : 'Discarded all unfinished tasks in this batch. '
                  'Tasks already saved were not changed.',
        );
        return;

      case ActiveTaskControlIntent.ambiguousStop:
      case ActiveTaskControlIntent.none:
        await _speakBackendText(
          'No task changes were made. Please continue with the current task.',
        );
        return;
    }
  }

  Future<void> _handlePendingVoiceTaskControl(String utterance) async {
    final pending = _pendingVoiceTaskControlIntent;
    if (pending == null) {
      return;
    }

    // "continue", "keep it", or "no" always means cancel the pending
    // control operation and return to the exact task flow.
    if (_isContinueTaskSpeech(utterance) ||
        (pending != ActiveTaskControlIntent.ambiguousStop &&
            _isCancelSpeech(utterance))) {
      await _resumeVoiceTaskAfterControl();
      return;
    }

    // The ambiguous menu first requires the user to choose an action. Choosing
    // an action does not mutate anything; it opens the specific confirmation.
    if (pending == ActiveTaskControlIntent.ambiguousStop) {
      final selected = _voiceControlSelection(utterance);

      if (selected == ActiveTaskControlIntent.none ||
          selected == ActiveTaskControlIntent.ambiguousStop) {
        await _speakBackendText(_voiceControlPrompt(pending));
        return;
      }

      await _beginVoiceTaskControl(selected);
      return;
    }

    // A clear destructive/skip intent still requires an explicit yes/confirm.
    if (_isConfirmSpeech(utterance)) {
      await _executeVoiceTaskControl(pending);
      return;
    }

    // If the user changes their mind to another control action, switch the
    // confirmation target but still do not mutate yet.
    final selected = _voiceControlSelection(utterance);
    if (selected != ActiveTaskControlIntent.none && selected != pending) {
      await _beginVoiceTaskControl(selected);
      return;
    }

    await _speakBackendText(_voiceControlPrompt(pending));
  }

'''
        text = text[:helper_index] + helpers + text[helper_index:]

    # -------------------------------------------------------------
    # Main routing: spoken controls are intercepted BEFORE draft answers.
    # -------------------------------------------------------------
    new_process = r'''  Future<void> _processTaskUtterance(String utterance) async {
    if (_processingTask) {
      _queuedTaskUtterance = utterance;
      return;
    }

    _processingTask = true;

    try {
      // -----------------------------------------------------
      // PENDING VOICE TASK-CONTROL CONFIRMATION
      // -----------------------------------------------------
      if (_pendingVoiceTaskControlIntent != null) {
        await _handlePendingVoiceTaskControl(utterance);
        return;
      }

      // -----------------------------------------------------
      // ACTIVE BATCH TASK-CONTROL INTENT
      // -----------------------------------------------------
      // This MUST run before the current task answer is sent to /continue.
      // Clear destructive/skip requests open confirmation; generic cancel/stop
      // opens an action menu. No backend mutation happens here.
      if (_taskBatchId != null) {
        final controlIntent = detectActiveTaskControlIntent(utterance);
        if (controlIntent != ActiveTaskControlIntent.none) {
          await _beginVoiceTaskControl(controlIntent);
          return;
        }
      }

      // -----------------------------------------------------
      // LEGACY STANDALONE CANCEL / STOP
      // -----------------------------------------------------
      // Update/delete/complete single-command voice flows retain their old
      // cancel behavior. Batch creates use the explicit control flow above.
      if (_taskBatchId == null &&
          _taskFlowActive &&
          _isCancelSpeech(utterance)) {
        _clearTaskFlow();
        await _speakBackendText('Cancelled. No changes were made.');
        return;
      }

      final pending = _pendingTaskPreview;

      // -----------------------------------------------------
      // TARGET SELECTION (standalone update/delete flow)
      // -----------------------------------------------------
      if (pending != null && pending.needsTargetSelection) {
        final match = _resolveTaskMatch(pending.targetMatches, utterance);

        if (match == null) {
          await _speakBackendText(
            _voiceTaskSpeech(_targetSelectionPrompt(pending)),
          );
          return;
        }

        final resolved = await ref
            .read(assistantRepositoryProvider)
            .selectTaskTarget(
              draftId: pending.draftId,
              taskId: match.id,
            );

        _taskDraftId = resolved.draftId;
        _pendingTaskPreview = null;
        await _handleTaskPreview(resolved);
        return;
      }

      // -----------------------------------------------------
      // DUPLICATE REVIEW
      // -----------------------------------------------------
      if (pending != null && pending.duplicateReview) {
        await _handleDuplicateSpeech(pending, utterance);
        return;
      }

      // -----------------------------------------------------
      // FINAL CONFIRMATION
      // -----------------------------------------------------
      if (pending != null &&
          pending.ready &&
          pending.action != 'list_active_tasks') {
        if (_isConfirmSpeech(utterance)) {
          await _executeConfirmedTask(pending);
          return;
        }

        final message = _taskBatchId != null
            ? '${pending.summary}. Say confirm to save this task.'
            : 'The task change is ready. '
                '${pending.summary}. '
                'Say confirm to continue, '
                'or cancel to make no changes.';

        await _speakBackendText(_voiceTaskSpeech(message));
        return;
      }

      // -----------------------------------------------------
      // ANSWER TO ACTIVE BATCH TASK
      // -----------------------------------------------------
      if (_taskBatchId != null) {
        await _continueVoiceTaskBatch(utterance);
        return;
      }

      // -----------------------------------------------------
      // NEW CREATE REQUEST -> SERVER-OWNED BATCH
      // -----------------------------------------------------
      if (_taskDraftId == null && looksLikeCreateTaskAction(utterance)) {
        await _startVoiceTaskBatch(utterance);
        return;
      }

      // -----------------------------------------------------
      // EXISTING SINGLE-COMMAND FLOW
      // -----------------------------------------------------
      final preview = await ref
          .read(assistantRepositoryProvider)
          .previewTaskCommand(
            utterance,
            draftId: _taskDraftId,
          );

      _taskDraftId = preview.draftId;
      await _handleTaskPreview(preview);
    } catch (error, stackTrace) {
      debugPrint('[VOICE TASK] Error: $error');
      debugPrint('$stackTrace');

      await _speakBackendText(
        'I could not complete that task request. '
        '${_cleanError(error.toString())}',
      );
    } finally {
      _processingTask = false;

      final queued = _queuedTaskUtterance;
      _queuedTaskUtterance = null;

      if (queued != null && queued.trim().isNotEmpty) {
        unawaited(_processTaskUtterance(queued));
      }
    }
  }

'''
    text = replace_between(
        text,
        '  Future<void> _processTaskUtterance(String utterance) async {',
        '  Future<void> _handleTaskPreview(',
        new_process,
        '_processTaskUtterance',
    )

    # -------------------------------------------------------------
    # Clearing a task flow also clears any unexecuted voice control intent.
    # -------------------------------------------------------------
    old_clear = '''  void _clearTaskFlow() {\n    _taskBatchId = null;\n    _taskBatchCurrentTaskNumber = null;\n    _taskBatchTotalTasks = null;\n    _taskDraftId = null;\n    _pendingTaskPreview = null;\n    _queuedTaskUtterance = null;\n  }\n'''
    new_clear = '''  void _clearTaskFlow() {\n    _taskBatchId = null;\n    _taskBatchCurrentTaskNumber = null;\n    _taskBatchTotalTasks = null;\n    _taskDraftId = null;\n    _pendingTaskPreview = null;\n    _pendingVoiceTaskControlIntent = null;\n    _voiceTaskResumePrompt = null;\n    _queuedTaskUtterance = null;\n  }\n'''
    text = replace_once(text, old_clear, new_clear, 'clear task flow')

    write(screen, text)

    # Source-level sanity checks. Flutter analyzer remains authoritative.
    current = read(screen)
    required = [
        '_pendingVoiceTaskControlIntent',
        'detectActiveTaskControlIntent(utterance)',
        'deferTaskBatch(',
        'cancelTaskBatch(',
        'abortTaskBatch(',
        '_handlePendingVoiceTaskControl(utterance)',
        'Do you want to discard all unfinished tasks in this batch?',
    ]
    missing = [x for x in required if x not in current]
    if missing:
        raise RuntimeError(f'Voice Step 4B source check failed: {missing}')

    print('Voice Step 4B applied successfully.')
    print('- Spoken Skip Current now requires confirmation.')
    print('- Spoken Discard Current now requires confirmation.')
    print('- Spoken Discard Remaining now requires confirmation.')
    print('- Generic Cancel/Stop opens a non-destructive action menu.')
    print('- Start New Task asks before aborting unfinished work.')
    print('- Single-task Skip resolves cleanly instead of attempting defer.')
    print('- Gemini Live audio/WebSocket/orb code was not modified.')


if __name__ == '__main__':
    main()
