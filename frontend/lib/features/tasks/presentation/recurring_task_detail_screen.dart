import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../application/task_providers.dart';

class RecurringTaskDetailScreen extends ConsumerStatefulWidget {
  final String taskId;

  const RecurringTaskDetailScreen({super.key, required this.taskId});

  @override
  ConsumerState<RecurringTaskDetailScreen> createState() {
    return _RecurringTaskDetailScreenState();
  }
}

class _RecurringTaskDetailScreenState
    extends ConsumerState<RecurringTaskDetailScreen> {
  bool _loading = true;
  bool _working = false;

  String? _error;

  Map<String, dynamic> _details = {};

  DateTime _visibleMonth = DateTime(DateTime.now().year, DateTime.now().month);

  @override
  void initState() {
    super.initState();

    _load();
  }

  Future<void> _load({bool showLoading = true}) async {
    if (showLoading) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      final repository = ref.read(taskRepositoryProvider);

      final raw = await repository.getRecurringTaskDetails(widget.taskId);

      final details = _asMap(raw);

      if (details.isEmpty) {
        throw const ApiException(
          message: 'Recurring task details could not be loaded.',
        );
      }

      final task = _asMap(details['task']);
      final duration = _asMap(task['duration']);

      final start = _parseDate(duration['start_date']);
      final end = _parseDate(duration['end_date']);

      var visibleMonth = DateTime(DateTime.now().year, DateTime.now().month);

      if (start != null &&
          _monthValue(visibleMonth) <
              _monthValue(DateTime(start.year, start.month))) {
        visibleMonth = DateTime(start.year, start.month);
      }

      if (end != null &&
          _monthValue(visibleMonth) >
              _monthValue(DateTime(end.year, end.month))) {
        visibleMonth = DateTime(end.year, end.month);
      }

      if (!mounted) {
        return;
      }

      setState(() {
        _details = details;
        _visibleMonth = visibleMonth;
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
        _error = 'Could not load recurring task details.';
      });
    }
  }

  Future<void> _completeToday() async {
    final todayOccurrence = _asMap(_details['today_occurrence']);

    final occurrenceId = todayOccurrence['id']?.toString();

    if (occurrenceId == null ||
        occurrenceId.isEmpty ||
        todayOccurrence['status']?.toString() != 'pending') {
      return;
    }

    setState(() {
      _working = true;
    });

    try {
      await ref
          .read(taskRepositoryProvider)
          .completeRecurringOccurrence(occurrenceId);

      await _load(showLoading: false);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Task completed for today.')),
      );
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
        const SnackBar(content: Text('Could not complete today.')),
      );
    } finally {
      if (mounted) {
        setState(() {
          _working = false;
        });
      }
    }
  }

  Future<void> _completePermanently() async {
    final confirmed =
        await showDialog<bool>(
          context: context,
          builder: (dialogContext) {
            return AlertDialog(
              title: const Text('Complete permanently?'),
              content: const Text(
                'This will end the recurring task and remove its future pending occurrences. Completed and missed history will remain available.',
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
                  child: const Text('Complete permanently'),
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
          .completeRecurringTask(widget.taskId);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Recurring task completed permanently.')),
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
        const SnackBar(content: Text('Could not complete the recurring task.')),
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
        title: const Text('Recurring task'),
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

    final task = _asMap(_details['task']);

    final summary = _asMap(_details['summary']);

    final occurrences = _asList(_details['occurrences']);

    final todayOccurrence = _asMap(_details['today_occurrence']);

    final title = task['title']?.toString() ?? 'Recurring task';

    final description = task['description']?.toString() ?? '';

    final completionRate = _toInt(summary['completion_rate']);

    final streak = _currentStreak(occurrences);

    final todayStatus = todayOccurrence['status']?.toString();

    final canCompleteToday =
        todayOccurrence.isNotEmpty && todayStatus == 'pending';

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

        const SizedBox(height: 14),

        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _chip(_priorityLabel(task['priority'])),
            _chip(_repeatLabel(task['repeat'])),
          ],
        ),

        const SizedBox(height: 12),

        Text(
          _durationText(task['duration']),
          style: TextStyle(color: colors.textSecondary, fontSize: 12),
        ),

        const SizedBox(height: 22),

        Row(
          children: [
            Expanded(
              child: _statCard(
                label: 'Current streak',
                value: '$streak ${streak == 1 ? 'day' : 'days'}',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _statCard(label: 'Completion', value: '$completionRate%'),
            ),
          ],
        ),

        const SizedBox(height: 28),

        _calendar(occurrences),

        const SizedBox(height: 28),

        SizedBox(
          width: double.infinity,
          height: 50,
          child: FilledButton(
            onPressed: canCompleteToday && !_working ? _completeToday : null,
            style: FilledButton.styleFrom(
              backgroundColor: colors.white,
              foregroundColor: colors.onAccent,
              disabledBackgroundColor: colors.surfaceElevated,
              disabledForegroundColor: colors.textMuted,
            ),
            child: _working
                ? const SizedBox(
                    width: 19,
                    height: 19,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Text(
                    todayStatus == 'completed'
                        ? 'Completed today'
                        : todayOccurrence.isEmpty
                        ? 'No task scheduled today'
                        : todayStatus == 'missed'
                        ? 'Today is marked missed'
                        : 'Complete today',
                  ),
          ),
        ),

        const SizedBox(height: 12),

        SizedBox(
          width: double.infinity,
          height: 50,
          child: OutlinedButton(
            onPressed: _working ? null : _completePermanently,
            style: OutlinedButton.styleFrom(
              foregroundColor: colors.textPrimary,
              side: BorderSide(color: colors.border),
            ),
            child: const Text('Complete permanently'),
          ),
        ),
      ],
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

  Widget _statCard({required String label, required String value}) {
    final colors = AppColors.of(context);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surfaceElevated,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(color: colors.textSecondary, fontSize: 11),
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  Widget _calendar(List<Map<String, dynamic>> occurrences) {
    final colors = AppColors.of(context);

    final firstDay = DateTime(_visibleMonth.year, _visibleMonth.month, 1);

    final daysInMonth = DateUtils.getDaysInMonth(
      _visibleMonth.year,
      _visibleMonth.month,
    );

    final offset = firstDay.weekday - 1;

    final occurrenceMap = <String, Map<String, dynamic>>{};

    for (final occurrence in occurrences) {
      final date = occurrence['scheduled_date']?.toString();

      if (date != null) {
        occurrenceMap[date] = occurrence;
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                DateFormat('MMMM yyyy').format(_visibleMonth).toUpperCase(),
                style: TextStyle(
                  color: colors.textSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.4,
                ),
              ),
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              onPressed: _canMoveMonth(-1) ? () => _moveMonth(-1) : null,
              icon: const Icon(Icons.chevron_left),
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              onPressed: _canMoveMonth(1) ? () => _moveMonth(1) : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),

        const SizedBox(height: 8),

        Row(
          children: const [
            Expanded(child: Center(child: Text('M'))),
            Expanded(child: Center(child: Text('T'))),
            Expanded(child: Center(child: Text('W'))),
            Expanded(child: Center(child: Text('T'))),
            Expanded(child: Center(child: Text('F'))),
            Expanded(child: Center(child: Text('S'))),
            Expanded(child: Center(child: Text('S'))),
          ],
        ),

        const SizedBox(height: 8),

        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: offset + daysInMonth,
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 7,
            mainAxisSpacing: 6,
            crossAxisSpacing: 6,
          ),
          itemBuilder: (context, index) {
            if (index < offset) {
              return const SizedBox();
            }

            final day = index - offset + 1;

            final date = DateTime(_visibleMonth.year, _visibleMonth.month, day);

            final key = DateFormat('yyyy-MM-dd').format(date);

            return _calendarDay(date: date, occurrence: occurrenceMap[key]);
          },
        ),

        const SizedBox(height: 10),

        Wrap(
          spacing: 16,
          runSpacing: 8,
          children: [
            _legend(AppColors.green, 'Completed'),
            _legend(AppColors.red, 'Missed'),
            _legend(colors.textMuted, 'Scheduled'),
          ],
        ),
      ],
    );
  }

  Widget _calendarDay({
    required DateTime date,
    required Map<String, dynamic>? occurrence,
  }) {
    final colors = AppColors.of(context);

    final status = occurrence?['status']?.toString();

    final today = DateTime.now();

    final isToday =
        date.year == today.year &&
        date.month == today.month &&
        date.day == today.day;

    Color background = Colors.transparent;

    Color textColor = colors.textMuted;

    if (occurrence != null) {
      textColor = colors.textPrimary;

      if (status == 'completed') {
        background = AppColors.green.withValues(alpha: 0.18);

        textColor = AppColors.green;
      } else if (status == 'missed') {
        background = AppColors.red.withValues(alpha: 0.16);

        textColor = AppColors.red;
      } else {
        background = colors.surfaceElevated;
      }
    }

    return Container(
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(7),
        border: isToday ? Border.all(color: colors.white, width: 1.4) : null,
      ),
      child: Text(
        '${date.day}',
        style: TextStyle(
          color: textColor,
          fontSize: 12,
          fontWeight: occurrence != null ? FontWeight.w600 : FontWeight.w400,
        ),
      ),
    );
  }

  Widget _legend(Color color, String label) {
    final colors = AppColors.of(context);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(shape: BoxShape.circle, color: color),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(color: colors.textSecondary, fontSize: 11),
        ),
      ],
    );
  }

  int _currentStreak(List<Map<String, dynamic>> occurrences) {
    final today = DateTime.now();

    final items = occurrences
        .map((item) {
          return MapEntry(
            _parseDate(item['scheduled_date']),
            item['status']?.toString(),
          );
        })
        .where(
          (item) =>
              item.key != null &&
              !item.key!.isAfter(DateTime(today.year, today.month, today.day)),
        )
        .toList();

    items.sort((a, b) => b.key!.compareTo(a.key!));

    var streak = 0;

    for (final item in items) {
      final status = item.value;

      if (status == 'pending') {
        continue;
      }

      if (status == 'completed') {
        streak++;
        continue;
      }

      if (status == 'missed') {
        break;
      }
    }

    return streak;
  }

  bool _canMoveMonth(int difference) {
    final candidate = DateTime(
      _visibleMonth.year,
      _visibleMonth.month + difference,
    );

    final task = _asMap(_details['task']);

    final duration = _asMap(task['duration']);

    final start = _parseDate(duration['start_date']);

    final end = _parseDate(duration['end_date']);

    if (start != null &&
        _monthValue(candidate) <
            _monthValue(DateTime(start.year, start.month))) {
      return false;
    }

    if (end != null &&
        _monthValue(candidate) > _monthValue(DateTime(end.year, end.month))) {
      return false;
    }

    return true;
  }

  void _moveMonth(int difference) {
    if (!_canMoveMonth(difference)) {
      return;
    }

    setState(() {
      _visibleMonth = DateTime(
        _visibleMonth.year,
        _visibleMonth.month + difference,
      );
    });
  }

  int _monthValue(DateTime date) {
    return date.year * 12 + date.month;
  }

  String _priorityLabel(dynamic value) {
    switch (value?.toString()) {
      case 'important_urgent':
        return 'Important · Urgent';

      case 'important_not_urgent':
        return 'Important · Not urgent';

      case 'not_important_urgent':
        return 'Not important · Urgent';

      case 'not_important_not_urgent':
        return 'Not important · Not urgent';

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
        return 'Recurring';
    }
  }

  String _durationText(dynamic raw) {
    final duration = _asMap(raw);

    final start = _parseDate(duration['start_date']);

    final end = _parseDate(duration['end_date']);

    if (start == null && end == null) {
      return '';
    }

    if (start != null && end != null) {
      return '${DateFormat('d MMM yyyy').format(start)} – ${DateFormat('d MMM yyyy').format(end)}';
    }

    if (start != null) {
      return 'Starts ${DateFormat('d MMM yyyy').format(start)}';
    }

    return 'Ends ${DateFormat('d MMM yyyy').format(end!)}';
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
