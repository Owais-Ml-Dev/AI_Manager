import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../../history/application/history_providers.dart';
import '../../home/application/home_providers.dart';
import '../../tasks/presentation/new_task_screen.dart';
import '../application/assistant_providers.dart';
import '../data/assistant_repository.dart';
import '../domain/assistant_intent.dart';
import '../domain/assistant_message.dart';

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  final List<AssistantMessage> _messages = [];

  bool _sending = false;
  CancelToken? _activeCancelToken;
  String? _activeDraftId;
  AssistantCommandPreview? _pendingCommand;
  String? _selectedMatchId;

  // Quick-reply chips for the question currently being asked.
  List<String> _suggestions = const [];

  @override
  void dispose() {
    _activeCancelToken?.cancel('Assistant screen closed.');
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final message = _messageController.text.trim();
    if (message.isEmpty || _sending) return;

    final normalized = message.toLowerCase();
    if (_activeDraftId != null &&
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

    setState(() {
      _suggestions = const [];
      _messages.add(AssistantMessage(text: message, fromUser: true));
      _messageController.clear();
      _activeCancelToken = CancelToken();
      _sending = true;
    });
    _scrollToBottom();

    // When the backend has an unfinished draft, the next message is always a
    // continuation even if it is just "14 days" or "8 PM".
    if (_activeDraftId != null || looksLikeTaskAction(message)) {
      await _previewTaskCommand(message);
    } else {
      await _sendChat(message);
    }
  }

  Future<void> _sendChat(String message) async {
    try {
      final result = await ref
          .read(assistantRepositoryProvider)
          .sendMessage(message, cancelToken: _activeCancelToken);
      if (!mounted) return;
      setState(() {
        _messages.add(
          AssistantMessage(
            text: result.reply,
            fromUser: false,
            model: result.model,
          ),
        );
      });
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) return;
      rethrow;
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not reach the assistant.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _previewTaskCommand(String message) async {
    try {
      final preview = await ref
          .read(assistantRepositoryProvider)
          .previewTaskCommand(
            message,
            draftId: _activeDraftId,
            cancelToken: _activeCancelToken,
          );
      if (!mounted) return;

      _activeDraftId = preview.draftId;

      if (preview.needsInput) {
        setState(() {
          _pendingCommand = null;
          _selectedMatchId = null;
          _suggestions = preview.suggestions;
          _messages.add(
            AssistantMessage(
              text: preview.question ?? 'I need a little more information.',
              fromUser: false,
              model: preview.model,
            ),
          );
        });
        return;
      }

      if (preview.ready && preview.action == 'list_active_tasks') {
        await _executeReadOnly(preview);
        return;
      }

      setState(() {
        _pendingCommand = preview;
        _selectedMatchId = null;
      });
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) return;
      rethrow;
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not understand that task request.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _selectTarget() async {
    final preview = _pendingCommand;
    final taskId = _selectedMatchId;
    if (preview == null || taskId == null || _sending) return;

    setState(() => _sending = true);
    try {
      final resolved = await ref
          .read(assistantRepositoryProvider)
          .selectTaskTarget(draftId: preview.draftId, taskId: taskId);
      if (!mounted) return;
      setState(() {
        _pendingCommand = resolved;
        _activeDraftId = resolved.draftId;
        _selectedMatchId = null;
      });
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not select that task.');
    } finally {
      _finishSending();
    }
  }

  Future<void> _executeReadOnly(AssistantCommandPreview preview) async {
    try {
      final response = await ref
          .read(assistantRepositoryProvider)
          .executeTaskCommand(draftId: preview.draftId, confirmed: false);
      if (!mounted) return;
      setState(() {
        _activeDraftId = null;
        _pendingCommand = null;
        _messages.add(
          AssistantMessage(
            text: _formatReadOnlyResult(response),
            fromUser: false,
            model: preview.model,
          ),
        );
      });
    } on ApiException catch (error) {
      _addError(error.message);
    }
  }

  Future<void> _confirmCommand({
    String? duplicateDecision,
    String? candidateId,
  }) async {
    final preview = _pendingCommand;
    if (preview == null || _sending) return;

    setState(() => _sending = true);
    try {
      await ref
          .read(assistantRepositoryProvider)
          .executeTaskCommand(
            draftId: preview.draftId,
            confirmed: true,
            duplicateDecision: duplicateDecision,
            candidateId: candidateId,
          );

      _refreshTaskScreens();
      if (!mounted) return;
      setState(() {
        _pendingCommand = null;
        _activeDraftId = null;
        _selectedMatchId = null;
        _messages.add(
          AssistantMessage(
            text: 'Done. ${preview.summary}',
            fromUser: false,
            model: preview.model,
          ),
        );
      });
    } on ApiException catch (error) {
      _addError(error.message);
    } catch (_) {
      _addError('Could not complete that task action.');
    } finally {
      _finishSending();
    }
  }

  void _cancelCommand() {
    setState(() {
      _pendingCommand = null;
      _activeDraftId = null;
      _selectedMatchId = null;
      _suggestions = const [];
      _messages.add(
        const AssistantMessage(
          text: 'Cancelled. No changes were made.',
          fromUser: false,
        ),
      );
    });
    _scrollToBottom();
  }

  void _refreshTaskScreens() {
    ref.invalidate(homeDataProvider);
    ref.invalidate(historyDataProvider);
    ref.invalidate(dashboardDataProvider);
  }

  void _openNewTask() {
    Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => const NewTaskScreen()));
  }

  String _formatReadOnlyResult(Map<String, dynamic> response) {
    final result = _asMap(response['result']);
    final repeat = _asList(result['repeat_until_done']);
    final recurring = _asList(result['recurring']);
    if (repeat.isEmpty && recurring.isEmpty) return 'You have no active tasks.';

    final lines = <String>[];
    if (recurring.isNotEmpty) {
      lines.add('Recurring:');
      for (final task in recurring) {
        lines.add('- ${task['title'] ?? 'Untitled task'}');
      }
    }
    if (repeat.isNotEmpty) {
      if (lines.isNotEmpty) lines.add('');
      lines.add('Repeat Until Done:');
      for (final task in repeat) {
        lines.add('- ${task['title'] ?? 'Untitled task'}');
      }
    }
    return lines.join('\n');
  }

  void _addError(String message) {
    if (!mounted) return;
    setState(() {
      _messages.add(
        AssistantMessage(
          text: 'Could not complete request: $message',
          fromUser: false,
        ),
      );
    });
  }

  void _finishSending() {
    if (!mounted) return;
    setState(() {
      _activeCancelToken = null;
      _sending = false;
    });
    _scrollToBottom();
  }

  void _stopGenerating() {
    final token = _activeCancelToken;
    if (token == null || token.isCancelled) return;
    token.cancel('Stopped by user.');
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          _header(),
          const Divider(height: 1),
          Expanded(
            child: _messages.isEmpty
                ? _emptyState()
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(16, 18, 16, 24),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      return _MessageBubble(message: _messages[index]);
                    },
                  ),
          ),
          if (_pendingCommand != null)
            _CommandPreviewCard(
              preview: _pendingCommand!,
              selectedMatchId: _selectedMatchId,
              onMatchSelected: (value) {
                setState(() => _selectedMatchId = value);
              },
              onSelectTarget: _selectTarget,
              onConfirm: () => _confirmCommand(),
              onCreateNew: () =>
                  _confirmCommand(duplicateDecision: 'create_new'),
              onUpdateExisting: () => _confirmCommand(
                duplicateDecision: 'update_existing',
                candidateId: _selectedMatchId,
              ),
              onCancel: _cancelCommand,
              busy: _sending,
            ),
          if (_sending)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 5),
              child: Row(
                children: [
                  const SizedBox(
                    width: 13,
                    height: 13,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 9),
                  Text(
                    'Thinking...',
                    style: TextStyle(
                      color: AppColors.of(context).textSecondary,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          if (_suggestions.isNotEmpty && !_sending && _pendingCommand == null)
            _suggestionChips(),
          _inputArea(),
        ],
      ),
    );
  }

  Widget _header() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 10),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: AppColors.of(context).surfaceElevated,
              borderRadius: BorderRadius.circular(13),
            ),
            child: const Icon(Icons.auto_awesome, size: 21),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Assistant',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  'Gemini parses task JSON. You confirm every change.',
                  style: TextStyle(
                    color: AppColors.of(context).textSecondary,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 35),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.auto_awesome,
              size: 42,
              color: AppColors.of(context).textMuted,
            ),
            const SizedBox(height: 16),
            const Text(
              'How can I help?',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(
              'Ask naturally. For task changes, the backend validates the '
              'details and asks for confirmation before saving.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                fontSize: 12,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Tapping a chip sends it exactly as if it had been typed.
  void _sendQuickReply(String text) {
    if (_sending) return;
    _messageController.text = text;
    _send();
  }

  Widget _suggestionChips() {
    final colors = AppColors.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
      child: SizedBox(
        height: 36,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: _suggestions.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (context, index) {
            final label = _suggestions[index];
            return ActionChip(
              label: Text(
                label,
                style: TextStyle(color: colors.textPrimary, fontSize: 12),
              ),
              backgroundColor: colors.surfaceElevated,
              side: BorderSide(color: colors.border),
              onPressed: () => _sendQuickReply(label),
            );
          },
        ),
      ),
    );
  }

  Widget _inputArea() {
    final colors = AppColors.of(context);
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      color: colors.background,
      child: Container(
        constraints: const BoxConstraints(minHeight: 56),
        decoration: BoxDecoration(
          color: colors.surfaceElevated,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: colors.border, width: 1),
        ),
        padding: const EdgeInsets.fromLTRB(6, 4, 6, 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            IconButton(
              onPressed: _openNewTask,
              visualDensity: VisualDensity.compact,
              icon: Icon(Icons.add, size: 22, color: colors.textSecondary),
            ),
            Expanded(
              child: TextField(
                controller: _messageController,
                minLines: 1,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                onSubmitted: (_) => _send(),
                style: TextStyle(color: colors.textPrimary, fontSize: 14),
                decoration: InputDecoration(
                  hintText: _activeDraftId == null
                      ? 'Message Assistant'
                      : 'Reply with the missing detail',
                  hintStyle: TextStyle(color: colors.textMuted),
                  filled: false,
                  isDense: true,
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 12,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 4),
            IconButton(
              onPressed: _activeCancelToken != null
                  ? _stopGenerating
                  : (_sending ? null : _send),
              style: IconButton.styleFrom(
                backgroundColor: colors.white,
                foregroundColor: colors.onAccent,
                disabledBackgroundColor: colors.surface,
                disabledForegroundColor: colors.textMuted,
                minimumSize: const Size(42, 42),
                maximumSize: const Size(42, 42),
              ),
              icon: Icon(
                _activeCancelToken != null
                    ? Icons.stop_rounded
                    : Icons.arrow_upward,
                size: _activeCancelToken != null ? 18 : 19,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }

  List<Map<String, dynamic>> _asList(dynamic value) {
    if (value is! List) return [];
    return value
        .whereType<Map>()
        .map(
          (item) => item.map((key, value) => MapEntry(key.toString(), value)),
        )
        .toList();
  }
}

class _CommandPreviewCard extends StatelessWidget {
  final AssistantCommandPreview preview;
  final String? selectedMatchId;
  final ValueChanged<String?> onMatchSelected;
  final Future<void> Function() onSelectTarget;
  final Future<void> Function() onConfirm;
  final Future<void> Function() onCreateNew;
  final Future<void> Function() onUpdateExisting;
  final VoidCallback onCancel;
  final bool busy;

  const _CommandPreviewCard({
    required this.preview,
    required this.selectedMatchId,
    required this.onMatchSelected,
    required this.onSelectTarget,
    required this.onConfirm,
    required this.onCreateNew,
    required this.onUpdateExisting,
    required this.onCancel,
    required this.busy,
  });

  @override
  Widget build(BuildContext context) {
    final matches = preview.needsTargetSelection
        ? preview.targetMatches
        : preview.duplicateMatches;

    return Container(
      margin: const EdgeInsets.fromLTRB(14, 6, 14, 8),
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.fact_check_outlined, size: 18),
              const SizedBox(width: 8),
              Text(
                preview.needsTargetSelection
                    ? 'Choose the task'
                    : preview.duplicateReview
                    ? 'Possible duplicate'
                    : 'Confirm task change',
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if ((preview.question ?? '').isNotEmpty)
            Text(
              preview.question!,
              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                height: 1.4,
                fontSize: 12,
              ),
            )
          else if (preview.summary.isNotEmpty)
            Text(
              preview.summary,
              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                height: 1.4,
                fontSize: 12,
              ),
            ),
          if (preview.command.isNotEmpty) ...[
            const SizedBox(height: 12),
            _CommandDetails(preview: preview),
          ],
          if (matches.isNotEmpty) ...[
            const SizedBox(height: 10),
            RadioGroup<String>(
              groupValue: selectedMatchId,
              onChanged: (value) {
                if (!busy) onMatchSelected(value);
              },
              child: Column(
                children: [
                  ...matches.map(
                    (match) => RadioListTile<String>(
                      value: match.id,
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        match.title,
                        style: const TextStyle(fontSize: 12),
                      ),
                      subtitle: Text(
                        '${_taskTypeLabel(match.taskType)} - ${match.score.toStringAsFixed(0)}% match',
                        style: TextStyle(
                          fontSize: 10,
                          color: AppColors.of(context).textMuted,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          if (preview.needsTargetSelection)
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: busy ? null : onCancel,
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    onPressed: busy || selectedMatchId == null
                        ? null
                        : onSelectTarget,
                    child: const Text('Use selected'),
                  ),
                ),
              ],
            )
          else if (preview.duplicateReview)
            Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: busy ? null : onCancel,
                        child: const Text('Cancel'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: FilledButton.tonal(
                        onPressed: busy ? null : onCreateNew,
                        child: const Text('Create new'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: busy || selectedMatchId == null
                        ? null
                        : onUpdateExisting,
                    child: const Text('Update selected existing task'),
                  ),
                ),
              ],
            )
          else
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: busy ? null : onCancel,
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton(
                    onPressed: busy ? null : onConfirm,
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.of(context).white,
                      foregroundColor: AppColors.of(context).onAccent,
                    ),
                    child: const Text('Confirm'),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }

  static String _taskTypeLabel(String value) {
    return value == 'recurring' ? 'Recurring' : 'Repeat Until Done';
  }
}

class _CommandDetails extends StatelessWidget {
  final AssistantCommandPreview preview;

  const _CommandDetails({required this.preview});

  @override
  Widget build(BuildContext context) {
    final arguments = preview.arguments;
    final task = _asMap(arguments['task']);
    final changes = _asMap(arguments['changes']);
    final rows = <String>[];

    if (task.isNotEmpty) {
      if (preview.action == 'create_recurring_task') {
        rows.add('Type: Recurring');
      } else if (preview.action == 'create_repeat_until_done_task') {
        rows.add('Type: Repeat Until Done');
      }

      final title = task['title']?.toString();
      if (title != null) rows.add('Task: $title');

      final description = task['description']?.toString() ?? '';
      if (description.isNotEmpty) rows.add('Description: $description');

      final duration = _asMap(task['duration']);
      if (duration.isNotEmpty) {
        rows.add(
          'Dates: ${duration['start_date']} to ${duration['end_date']}',
        );
      }

      final repeat = _asMap(task['repeat']);
      if (repeat.isNotEmpty) {
        final dates = repeat['custom_dates'];
        final extra = (dates is List && dates.isNotEmpty)
            ? ' (${dates.join(', ')})'
            : '';
        rows.add('Repeat: ${_repeatName(repeat['type']?.toString())}$extra');
      }

      final reminders = task['reminders'];
      if (reminders is List) {
        var number = 1;
        for (final item in reminders) {
          final reminder = _asMap(item);
          if (reminder.isEmpty) continue;
          final count = reminder['count'];
          final times = (count is int && count > 1) ? ' ($count reminders)' : '';
          rows.add(
            'Reminder window $number: '
            '${reminder['start_time']} - ${reminder['end_time']}$times',
          );
          number++;
        }
      }
    }

    if (changes.isNotEmpty) {
      rows.add('Changes: ${changes.keys.join(', ')}');
    }

    if (rows.isEmpty) rows.add(_actionName(preview.action));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: rows
          .map(
            (text) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(text, style: const TextStyle(fontSize: 11)),
            ),
          )
          .toList(),
    );
  }

  String _actionName(String action) {
    switch (action) {
      case 'create_recurring_task':
        return 'Create recurring task';
      case 'create_repeat_until_done_task':
        return 'Create Repeat Until Done task';
      case 'update_recurring_task':
      case 'update_repeat_until_done_task':
        return 'Update task';
      case 'complete_recurring_occurrence':
        return 'Complete today';
      case 'complete_repeat_until_done_task':
        return 'Complete permanently';
      case 'delete_recurring_task':
      case 'delete_repeat_until_done_task':
        return 'Delete task';
      default:
        return 'Task action';
    }
  }

  String _repeatName(String? value) {
    switch (value) {
      case 'everyday':
        return 'Every day';
      case 'weekdays':
        return 'Weekdays';
      case 'weekends':
        return 'Weekends';
      case 'custom_dates':
        return 'Custom dates';
      default:
        return 'Scheduled';
    }
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}

class _MessageBubble extends StatelessWidget {
  final AssistantMessage message;

  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final user = message.fromUser;
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.82,
        ),
        margin: const EdgeInsets.only(bottom: 13),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        decoration: BoxDecoration(
          color: user
              ? AppColors.of(context).white
              : AppColors.of(context).surface,
          borderRadius: BorderRadius.circular(16),
          border: user ? null : Border.all(color: AppColors.of(context).border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              message.text,
              style: TextStyle(
                color: user
                    ? AppColors.of(context).onAccent
                    : AppColors.of(context).textPrimary,
                fontSize: 13,
                height: 1.45,
              ),
            ),
            if (!user &&
                message.model != null &&
                message.model!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Gemini',
                style: TextStyle(
                  color: AppColors.of(context).textMuted,
                  fontSize: 9,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
