import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../application/task_providers.dart';
import 'edit_task_screen.dart';

class RepeatUntilDoneTaskDetailScreen extends ConsumerStatefulWidget {
  final String taskId;

  const RepeatUntilDoneTaskDetailScreen({super.key, required this.taskId});

  @override
  ConsumerState<RepeatUntilDoneTaskDetailScreen> createState() {
    return _RepeatUntilDoneTaskDetailScreenState();
  }
}

class _RepeatUntilDoneTaskDetailScreenState
    extends ConsumerState<RepeatUntilDoneTaskDetailScreen> {
  bool _loading = true;
  bool _working = false;

  String? _error;

  Map<String, dynamic> _task = {};

  @override
  void initState() {
    super.initState();

    _load();
  }

  Future<void> _load({bool showLoading = true}) async {
    if (showLoading && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final repository = ref.read(taskRepositoryProvider);

      final raw = await repository.getRepeatUntilDoneTask(widget.taskId);

      final task = _asMap(raw);

      if (task.isEmpty) {
        throw const ApiException(
          message: 'Repeat Until Done task could not be loaded.',
        );
      }

      if (!mounted) {
        return;
      }

      setState(() {
        _task = task;
        _loading = false;
        _error = null;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
        _error = error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
        _error = 'Could not load Repeat Until Done task.';
      });
    }
  }

  Future<void> _editTask() async {
    if (_working) {
      return;
    }

    final updated = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (context) {
          return EditTaskScreen(taskId: widget.taskId, recurring: false);
        },
      ),
    );

    if (updated == true && mounted) {
      await _load();
    }
  }

  Future<void> _completeTask() async {
    if (_working || _task['status']?.toString() == 'completed') {
      return;
    }

    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (dialogContext) {
            return AlertDialog(
              title: const Text('Complete task?'),
              content: const Text(
                'This will complete the Repeat Until Done task and stop its future reminders.',
              ),
              actions: [
                TextButton(
                  onPressed: () {
                    Navigator.pop(dialogContext, false);
                  },
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () {
                    Navigator.pop(dialogContext, true);
                  },
                  child: const Text('Complete'),
                ),
              ],
            );
          },
        ) ??
        false;

    if (!confirmed || !mounted) {
      return;
    }

    setState(() {
      _working = true;
    });

    try {
      await ref
          .read(taskRepositoryProvider)
          .completeRepeatUntilDoneTask(widget.taskId);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Repeat Until Done task completed.')),
      );

      Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.message)));
    } catch (_) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not complete the task.')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _working = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Scaffold(
      backgroundColor: colors.background,

      appBar: AppBar(
        backgroundColor: colors.background,

        elevation: 0,

        title: const Text('Repeat Until Done'),
      ),

      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? _buildError()
          : _buildDetails(),
    );
  }

  Widget _buildError() {
    final colors = AppColors.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 40, color: colors.textMuted),

            const SizedBox(height: 12),

            Text(
              _error!,
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.textSecondary),
            ),

            const SizedBox(height: 14),

            TextButton(onPressed: _load, child: const Text('Try again')),
          ],
        ),
      ),
    );
  }

  Widget _buildDetails() {
    final colors = AppColors.of(context);

    final title = _task['title']?.toString() ?? 'Repeat Until Done';

    final description = _task['description']?.toString() ?? '';

    final status = _task['status']?.toString() ?? 'pending';

    final reminders = _asList(_task['reminders']);

    final completed = status == 'completed';

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
        ),

        if (description.trim().isNotEmpty) ...[
          const SizedBox(height: 8),

          Text(
            description,
            style: TextStyle(
              color: colors.textSecondary,
              fontSize: 14,
              height: 1.45,
            ),
          ),
        ],

        const SizedBox(height: 16),

        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _chip(completed ? 'Completed' : 'Pending'),

            _chip(_priorityLabel(_task['priority'])),

            _chip(_repeatLabel(_task['repeat'])),
          ],
        ),

        const SizedBox(height: 26),

        _sectionTitle('DURATION'),

        const SizedBox(height: 10),

        _infoCard(
          icon: Icons.date_range_outlined,
          title: _durationText(_task['duration']),
        ),

        const SizedBox(height: 26),

        _sectionTitle('REMINDERS'),

        const SizedBox(height: 10),

        if (reminders.isEmpty)
          _infoCard(icon: Icons.notifications_none, title: 'No reminders')
        else
          ...reminders.asMap().entries.map((entry) {
            final index = entry.key;

            final reminder = entry.value;

            final start = reminder['start_time']?.toString();

            final end = reminder['end_time']?.toString();

            final count = _toInt(reminder['count']);

            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _infoCard(
                icon: Icons.notifications_none,
                title: 'Reminder ${index + 1}',
                subtitle:
                    '${_formatTime(start)} ? ${_formatTime(end)}'
                    ' ? $count ${count == 1 ? 'reminder' : 'reminders'}',
              ),
            );
          }),

        const SizedBox(height: 20),

        if (!completed)
          SizedBox(
            width: double.infinity,
            height: 50,
            child: FilledButton(
              onPressed: _working ? null : _editTask,

              style: FilledButton.styleFrom(
                backgroundColor: colors.white,

                foregroundColor: colors.onAccent,
              ),

              child: const Text('Edit task'),
            ),
          ),

        if (!completed) const SizedBox(height: 12),

        if (!completed)
          SizedBox(
            width: double.infinity,
            height: 50,
            child: OutlinedButton(
              onPressed: _working ? null : _completeTask,

              style: OutlinedButton.styleFrom(
                foregroundColor: colors.textPrimary,

                side: BorderSide(color: colors.border),
              ),

              child: _working
                  ? const SizedBox(
                      width: 19,
                      height: 19,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Complete task'),
            ),
          ),
      ],
    );
  }

  Widget _sectionTitle(String text) {
    final colors = AppColors.of(context);

    return Text(
      text,
      style: TextStyle(
        color: colors.textSecondary,
        fontSize: 12,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.5,
      ),
    );
  }

  Widget _chip(String text) {
    final colors = AppColors.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),

      decoration: BoxDecoration(
        color: colors.surfaceElevated,

        borderRadius: BorderRadius.circular(20),

        border: Border.all(color: colors.border),
      ),

      child: Text(
        text,
        style: TextStyle(
          color: colors.textSecondary,
          fontSize: 11,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _infoCard({
    required IconData icon,
    required String title,
    String? subtitle,
  }) {
    final colors = AppColors.of(context);

    return Container(
      width: double.infinity,

      padding: const EdgeInsets.all(15),

      decoration: BoxDecoration(
        color: colors.surfaceElevated,

        borderRadius: BorderRadius.circular(12),

        border: Border.all(color: colors.border),
      ),

      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: colors.textSecondary),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                if (subtitle != null) ...[
                  const SizedBox(height: 5),

                  Text(
                    subtitle,
                    style: TextStyle(color: colors.textSecondary, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _priorityLabel(dynamic value) {
    switch (value?.toString()) {
      case 'important_urgent':
        return 'Important ? Urgent';

      case 'important_not_urgent':
        return 'Important ? Not urgent';

      case 'not_important_urgent':
        return 'Not important ? Urgent';

      case 'not_important_not_urgent':
        return 'Not important ? Not urgent';

      default:
        return 'Priority';
    }
  }

  String _repeatLabel(dynamic raw) {
    final repeat = _asMap(raw);

    switch (repeat['type']?.toString()) {
      case 'everyday':
        return 'Every day';

      case 'weekdays':
        return 'Weekdays';

      case 'weekends':
        return 'Weekends';

      case 'custom_dates':
        final dates = repeat['custom_dates'];

        if (dates is List) {
          return '${dates.length} custom dates';
        }

        return 'Custom dates';

      default:
        return 'Repeat Until Done';
    }
  }

  String _durationText(dynamic raw) {
    final duration = _asMap(raw);

    final start = _parseDate(duration['start_date']);

    final end = _parseDate(duration['end_date']);

    if (start == null && end == null) {
      return 'No duration';
    }

    if (start != null && end != null) {
      return '${DateFormat('d MMM yyyy').format(start)}'
          ' ? '
          '${DateFormat('d MMM yyyy').format(end)}';
    }

    if (start != null) {
      return 'Starts '
          '${DateFormat('d MMM yyyy').format(start)}';
    }

    return 'Ends '
        '${DateFormat('d MMM yyyy').format(end!)}';
  }

  String _formatTime(String? value) {
    if (value == null || value.isEmpty) {
      return '?';
    }

    final parts = value.split(':');

    if (parts.length != 2) {
      return value;
    }

    final hour = int.tryParse(parts[0]);

    final minute = int.tryParse(parts[1]);

    if (hour == null || minute == null) {
      return value;
    }

    final now = DateTime.now();

    final date = DateTime(now.year, now.month, now.day, hour, minute);

    return DateFormat('h:mm a').format(date);
  }

  DateTime? _parseDate(dynamic value) {
    if (value == null) {
      return null;
    }

    return DateTime.tryParse(value.toString());
  }

  int _toInt(dynamic value) {
    if (value is int) {
      return value;
    }

    if (value is num) {
      return value.round();
    }

    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) {
      return {};
    }

    return value.map((key, value) => MapEntry(key.toString(), value));
  }

  List<Map<String, dynamic>> _asList(dynamic value) {
    if (value is! List) {
      return [];
    }

    return value
        .whereType<Map>()
        .map(
          (item) => item.map((key, value) => MapEntry(key.toString(), value)),
        )
        .toList();
  }
}
