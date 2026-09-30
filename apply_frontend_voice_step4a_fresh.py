from pathlib import Path
import shutil
import sys


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig')


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')


def backup(path: Path) -> None:
    target = path.with_name(path.name + '.before_voice_step4a.bak')
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
        raise SystemExit('Usage: python apply_frontend_voice_step4a.py <frontend_dir>')

    frontend = Path(sys.argv[1]).resolve()
    screen = frontend / 'lib/features/assistant/presentation/voice_mode_screen.dart'
    store = frontend / 'lib/features/assistant/data/assistant_batch_session_store.dart'
    repo = frontend / 'lib/features/assistant/data/assistant_repository.dart'
    intent = frontend / 'lib/features/assistant/domain/assistant_intent.dart'

    for path in (screen, store, repo, intent):
        if not path.exists():
            raise RuntimeError(f'Missing required file: {path}')

    backup(screen)
    text = read(screen)

    # -------------------------------------------------------------
    # Import shared batch recovery store.
    # -------------------------------------------------------------
    if "../data/assistant_batch_session_store.dart" not in text:
        text = replace_once(
            text,
            "import '../data/assistant_repository.dart';\n",
            "import '../data/assistant_batch_session_store.dart';\n"
            "import '../data/assistant_repository.dart';\n",
            'batch session store import',
        )

    # -------------------------------------------------------------
    # Voice batch state. Keep _taskDraftId because standalone update,
    # delete, complete and list commands still use the existing flow.
    # -------------------------------------------------------------
    old_state = '''  String? _taskDraftId;\n\n  AssistantCommandPreview? _pendingTaskPreview;\n'''
    new_state = '''  final AssistantBatchSessionStore _batchSessionStore =\n      const AssistantBatchSessionStore();\n\n  String? _taskBatchId;\n\n  int? _taskBatchCurrentTaskNumber;\n\n  int? _taskBatchTotalTasks;\n\n  String? _taskDraftId;\n\n  AssistantCommandPreview? _pendingTaskPreview;\n'''
    text = replace_once(text, old_state, new_state, 'voice batch state')

    # -------------------------------------------------------------
    # Active-flow test must include a server-owned task batch.
    # -------------------------------------------------------------
    old_active = '''  bool get _taskFlowActive {\n    return _taskDraftId != null || _pendingTaskPreview != null;\n  }\n'''
    new_active = '''  bool get _taskFlowActive {\n    return _taskBatchId != null ||\n        _taskDraftId != null ||\n        _pendingTaskPreview != null;\n  }\n'''
    text = replace_once(text, old_active, new_active, 'task flow active getter')

    # -------------------------------------------------------------
    # Batch helpers: start, continue, progress speech, persistence,
    # and advancement after each individually confirmed task.
    # -------------------------------------------------------------
    helper_anchor = '  Future<void> _processTaskUtterance(String utterance) async {'
    if 'Future<void> _startVoiceTaskBatch(' not in text:
        helper_index = text.find(helper_anchor)
        if helper_index == -1:
            raise RuntimeError('Could not find _processTaskUtterance anchor.')

        helpers = r'''  String _voiceTaskProgress() {
    final current = _taskBatchCurrentTaskNumber;
    final total = _taskBatchTotalTasks;

    if (_taskBatchId == null ||
        current == null ||
        total == null ||
        current < 1 ||
        total < 1) {
      return '';
    }

    return 'Task $current of $total.';
  }

  String _voiceTaskSpeech(
    String body, {
    String? lead,
  }) {
    final parts = <String>[];

    final cleanLead = lead?.trim();
    if (cleanLead != null && cleanLead.isNotEmpty) {
      parts.add(cleanLead);
    }

    final progress = _voiceTaskProgress();
    if (progress.isNotEmpty) {
      parts.add(progress);
    }

    final cleanBody = body.trim();
    if (cleanBody.isNotEmpty) {
      parts.add(cleanBody);
    }

    return parts.join(' ');
  }

  void _applyVoiceBatchActive(
    AssistantTaskBatchActiveResult active,
  ) {
    _taskBatchId = active.batchId;
    _taskBatchCurrentTaskNumber = active.currentTaskNumber;
    _taskBatchTotalTasks = active.totalTasks;
    _taskDraftId = active.activeDraft.draftId;
    _pendingTaskPreview = null;
  }

  Future<void> _rememberVoiceBatch(String batchId) async {
    try {
      await _batchSessionStore.saveActiveBatchId(batchId);
    } catch (error) {
      debugPrint('[VOICE TASK] Could not persist batch id: $error');
    }
  }

  Future<void> _forgetVoiceBatch() async {
    try {
      await _batchSessionStore.clearActiveBatchId();
    } catch (error) {
      debugPrint('[VOICE TASK] Could not clear batch id: $error');
    }
  }

  Future<void> _startVoiceTaskBatch(String utterance) async {
    final batch = await ref
        .read(assistantRepositoryProvider)
        .startTaskBatch(utterance);

    _taskBatchId = batch.batchId;
    _taskBatchCurrentTaskNumber = batch.currentTaskNumber;
    _taskBatchTotalTasks = batch.totalTasks;
    _taskDraftId = batch.activeDraft.draftId;
    _pendingTaskPreview = null;

    await _rememberVoiceBatch(batch.batchId);
    await _handleTaskPreview(batch.activeDraft);
  }

  Future<void> _continueVoiceTaskBatch(String utterance) async {
    final batchId = _taskBatchId;
    if (batchId == null) {
      return;
    }

    final active = await ref
        .read(assistantRepositoryProvider)
        .continueTaskBatch(
          batchId: batchId,
          message: utterance,
        );

    _applyVoiceBatchActive(active);
    await _handleTaskPreview(active.activeDraft);
  }

  Future<AssistantTaskBatchActiveResult?> _recoverNextVoiceBatchTask(
    String batchId,
  ) async {
    try {
      return await ref
          .read(assistantRepositoryProvider)
          .getActiveTaskBatch(batchId);
    } catch (error) {
      debugPrint('[VOICE TASK] Could not recover next batch task: $error');
      return null;
    }
  }

  Future<void> _handleVoiceBatchResolution(
    AssistantTaskBatchResolutionResult resolution, {
    String? lead,
  }) async {
    final total = resolution.totalTasks > 0
        ? resolution.totalTasks
        : (_taskBatchTotalTasks ?? 0);
    final resolvedNumber = resolution.resolvedTaskNumber;

    if (resolution.allDone || resolution.batchStatus == 'completed') {
      await _forgetVoiceBatch();
      _clearTaskFlow();

      final doneLead = lead?.trim().isNotEmpty == true
          ? lead!.trim()
          : 'Saved Task $resolvedNumber of $total.';

      await _speakBackendText(
        '$doneLead Batch complete. '
        '$total of $total task requests reviewed.',
      );
      return;
    }

    var next = resolution.nextTask;

    if (next == null && resolution.batchId.isNotEmpty) {
      next = await _recoverNextVoiceBatchTask(resolution.batchId);
    }

    if (next == null) {
      _taskDraftId = null;
      _pendingTaskPreview = null;
      _taskBatchCurrentTaskNumber = resolution.currentTaskNumber;

      final savedLead = lead?.trim().isNotEmpty == true
          ? lead!.trim()
          : 'Saved Task $resolvedNumber of $total.';

      await _speakBackendText(
        '$savedLead The next task is still saved in the batch, '
        'but I could not load it right now. '
        'Open the text Assistant to recover the unfinished batch.',
      );
      return;
    }

    _applyVoiceBatchActive(next);

    final savedLead = lead?.trim().isNotEmpty == true
        ? lead!.trim()
        : 'Saved Task $resolvedNumber of $total.';

    await _handleTaskPreview(
      next.activeDraft,
      lead: savedLead,
    );
  }

'''
        text = text[:helper_index] + helpers + text[helper_index:]

    # -------------------------------------------------------------
    # Main voice routing.
    # New CREATE requests use /task-batch/start (even one task).
    # Existing update/delete/complete/list behavior stays standalone.
    # -------------------------------------------------------------
    new_process = r'''  Future<void> _processTaskUtterance(String utterance) async {
    if (_processingTask) {
      _queuedTaskUtterance = utterance;
      return;
    }

    _processingTask = true;

    try {
      // -----------------------------------------------------
      // CANCEL / STOP SAFETY
      // -----------------------------------------------------
      // Step 4A intentionally does not map spoken "cancel" to a
      // destructive batch mutation. That arrives in Voice Step 4B with
      // explicit Skip / Discard Current / Discard Remaining confirmation.
      if (_taskFlowActive && _isCancelSpeech(utterance)) {
        if (_taskBatchId != null) {
          await _speakBackendText(
            'This task batch is still active. '
            'I will not discard anything without confirmation. '
            'Continue answering the current task, or use the text Assistant '
            'for skip and discard controls for now.',
          );
          return;
        }

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
    # Preview speaker with batch progress and optional lead-in from the
    # just-confirmed previous task.
    # -------------------------------------------------------------
    new_preview = r'''  Future<void> _handleTaskPreview(
    AssistantCommandPreview preview, {
    String? lead,
  }) async {
    if (preview.draftId.isNotEmpty) {
      _taskDraftId = preview.draftId;
    }

    // -------------------------------------------------------
    // BACKEND NEEDS AN ANSWER
    // -------------------------------------------------------
    if (preview.needsInput) {
      _pendingTaskPreview = null;

      var question = preview.question ?? 'I need a little more information.';

      if (preview.suggestions.isNotEmpty) {
        question += ' Options include ${preview.suggestions.join(', ')}.';
      }

      await _speakBackendText(
        _voiceTaskSpeech(question, lead: lead),
      );
      return;
    }

    // -------------------------------------------------------
    // USER MUST SELECT MATCHING TASK
    // -------------------------------------------------------
    if (preview.needsTargetSelection) {
      _pendingTaskPreview = preview;

      await _speakBackendText(
        _voiceTaskSpeech(
          _targetSelectionPrompt(preview),
          lead: lead,
        ),
      );
      return;
    }

    // -------------------------------------------------------
    // DUPLICATE TASK REVIEW
    // -------------------------------------------------------
    if (preview.duplicateReview) {
      _pendingTaskPreview = preview;

      await _speakBackendText(
        _voiceTaskSpeech(
          _duplicatePrompt(preview),
          lead: lead,
        ),
      );
      return;
    }

    // -------------------------------------------------------
    // READY
    // -------------------------------------------------------
    if (preview.ready) {
      if (preview.action == 'list_active_tasks') {
        final response = await ref
            .read(assistantRepositoryProvider)
            .executeTaskCommand(
              draftId: preview.draftId,
              confirmed: false,
            );

        final spoken = _formatReadOnlyTasks(response);
        _clearTaskFlow();
        await _speakBackendText(spoken);
        return;
      }

      // Never mutate immediately. Every task is individually confirmed.
      _pendingTaskPreview = preview;

      final summary = preview.summary.isEmpty
          ? 'The task change is ready.'
          : preview.summary;

      final body = _taskBatchId != null
          ? '$summary. Say confirm to save this task.'
          : '$summary. '
              'Say confirm to continue, '
              'or cancel to make no changes.';

      await _speakBackendText(
        _voiceTaskSpeech(body, lead: lead),
      );
      return;
    }

    await _speakBackendText(
      _voiceTaskSpeech(
        preview.question ?? 'I could not determine the next task step.',
        lead: lead,
      ),
    );
  }

'''
    text = replace_between(
        text,
        '  Future<void> _handleTaskPreview(',
        '  String _targetSelectionPrompt(',
        new_preview,
        '_handleTaskPreview',
    )

    # -------------------------------------------------------------
    # Duplicate handling must resolve through the batch endpoint when the
    # duplicate belongs to a batch-created task.
    # -------------------------------------------------------------
    new_duplicate = r'''  Future<void> _handleDuplicateSpeech(
    AssistantCommandPreview preview,
    String utterance,
  ) async {
    final normalized = _normalizeTaskSpeech(utterance);
    final batchId = _taskBatchId;

    if (normalized.contains('create new') ||
        normalized.contains('create anyway') ||
        normalized == 'new') {
      if (batchId != null) {
        final resolution = await ref
            .read(assistantRepositoryProvider)
            .confirmTaskBatch(
              batchId: batchId,
              draftId: preview.draftId,
              duplicateDecision: 'create_new',
            );

        _refreshTaskScreens();
        await _handleVoiceBatchResolution(
          resolution,
          lead: 'Saved Task ${resolution.resolvedTaskNumber} '
              'of ${resolution.totalTasks}.',
        );
        return;
      }

      await ref
          .read(assistantRepositoryProvider)
          .executeTaskCommand(
            draftId: preview.draftId,
            confirmed: true,
            duplicateDecision: 'create_new',
          );

      _refreshTaskScreens();

      final summary = preview.summary.isEmpty
          ? 'Task created.'
          : 'Done. ${preview.summary}';

      _clearTaskFlow();
      await _speakBackendText(summary);
      return;
    }

    final selected = _resolveTaskMatch(preview.duplicateMatches, utterance);

    final wantsExisting =
        normalized.contains('update') ||
        normalized.contains('existing') ||
        normalized.contains('use') ||
        selected != null;

    if (wantsExisting) {
      final candidate =
          selected ??
          (preview.duplicateMatches.length == 1
              ? preview.duplicateMatches.first
              : null);

      if (candidate == null) {
        await _speakBackendText(
          _voiceTaskSpeech(_duplicatePrompt(preview)),
        );
        return;
      }

      if (batchId != null) {
        final resolution = await ref
            .read(assistantRepositoryProvider)
            .confirmTaskBatch(
              batchId: batchId,
              draftId: preview.draftId,
              duplicateDecision: 'update_existing',
              candidateId: candidate.id,
            );

        _refreshTaskScreens();
        await _handleVoiceBatchResolution(
          resolution,
          lead: 'Used the existing task ${candidate.title} '
              'for Task ${resolution.resolvedTaskNumber} '
              'of ${resolution.totalTasks}.',
        );
        return;
      }

      await ref
          .read(assistantRepositoryProvider)
          .executeTaskCommand(
            draftId: preview.draftId,
            confirmed: true,
            duplicateDecision: 'update_existing',
            candidateId: candidate.id,
          );

      _refreshTaskScreens();
      _clearTaskFlow();

      await _speakBackendText(
        'Done. The existing task ${candidate.title} was used.',
      );
      return;
    }

    await _speakBackendText(
      _voiceTaskSpeech(_duplicatePrompt(preview)),
    );
  }

'''
    text = replace_between(
        text,
        '  Future<void> _handleDuplicateSpeech(',
        '  Future<void> _executeConfirmedTask(',
        new_duplicate,
        '_handleDuplicateSpeech',
    )

    # -------------------------------------------------------------
    # Confirm current batch item through /confirm, then auto-prepare and
    # speak Task N+1. Standalone mutations remain unchanged.
    # -------------------------------------------------------------
    new_execute = r'''  Future<void> _executeConfirmedTask(
    AssistantCommandPreview preview,
  ) async {
    final batchId = _taskBatchId;

    if (batchId != null) {
      final resolution = await ref
          .read(assistantRepositoryProvider)
          .confirmTaskBatch(
            batchId: batchId,
            draftId: preview.draftId,
          );

      _refreshTaskScreens();

      final summary = preview.summary.trim();
      final lead = summary.isEmpty
          ? 'Saved Task ${resolution.resolvedTaskNumber} '
              'of ${resolution.totalTasks}.'
          : 'Saved Task ${resolution.resolvedTaskNumber} '
              'of ${resolution.totalTasks}. $summary.';

      await _handleVoiceBatchResolution(
        resolution,
        lead: lead,
      );
      return;
    }

    await ref
        .read(assistantRepositoryProvider)
        .executeTaskCommand(
          draftId: preview.draftId,
          confirmed: true,
        );

    _refreshTaskScreens();

    final summary = preview.summary.isEmpty
        ? 'The task change was completed.'
        : 'Done. ${preview.summary}';

    _clearTaskFlow();
    await _speakBackendText(summary);
  }

'''
    text = replace_between(
        text,
        '  Future<void> _executeConfirmedTask(',
        '  void _clearTaskFlow()',
        new_execute,
        '_executeConfirmedTask',
    )

    # -------------------------------------------------------------
    # Local clear now resets batch-specific fields too. Persistent recovery
    # is cleared only after the backend actually completes/aborts the batch.
    # -------------------------------------------------------------
    old_clear = '''  void _clearTaskFlow() {\n    _taskDraftId = null;\n\n    _pendingTaskPreview = null;\n\n    _queuedTaskUtterance = null;\n  }\n'''
    new_clear = '''  void _clearTaskFlow() {\n    _taskBatchId = null;\n    _taskBatchCurrentTaskNumber = null;\n    _taskBatchTotalTasks = null;\n    _taskDraftId = null;\n    _pendingTaskPreview = null;\n    _queuedTaskUtterance = null;\n  }\n'''
    text = replace_once(text, old_clear, new_clear, 'task flow clear')

    write(screen, text)

    # Basic source checks before handing off to Flutter's analyzer.
    checks = [
        "startTaskBatch(utterance)",
        "continueTaskBatch(",
        "confirmTaskBatch(",
        "AssistantBatchSessionStore",
        "Task $current of $total.",
        "looksLikeCreateTaskAction(utterance)",
    ]
    current = read(screen)
    missing = [value for value in checks if value not in current]
    if missing:
        raise RuntimeError(f'Voice Step 4A source check failed: {missing}')

    print('Voice Step 4A applied successfully.')
    print('New CREATE requests now use the server-owned task-batch workflow.')
    print('Each batch task is confirmed individually before execution.')
    print('Standalone update/delete/complete/list flows remain unchanged.')
    print('Gemini Live microphone, WebSocket, playback, barge-in and orb were not modified.')


if __name__ == '__main__':
    main()
