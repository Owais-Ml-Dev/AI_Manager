import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../application/history_providers.dart';
import '../domain/history_item.dart';

class HistoryDetailsScreen extends ConsumerStatefulWidget {
  final HistoryItem item;

  const HistoryDetailsScreen({super.key, required this.item});

  @override
  ConsumerState<HistoryDetailsScreen> createState() {
    return _HistoryDetailsScreenState();
  }
}

class _HistoryDetailsScreenState extends ConsumerState<HistoryDetailsScreen> {
  bool _loading = true;
  String? _error;

  Map<String, dynamic> _details = {};

  @override
  void initState() {
    super.initState();

    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final repository = ref.read(historyRepositoryProvider);

      final result = widget.item.kind == HistoryTaskKind.recurring
          ? await repository.getRecurringDetails(widget.item.taskId)
          : await repository.getRepeatUntilDoneDetails(widget.item.taskId);

      if (!mounted) {
        return;
      }

      setState(() {
        _details = result;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
        _error = 'Could not load task details.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.of(context).background,
        elevation: 0,
        title: Text('History Details'),
      ),

      body: _loading
          ? Center(child: CircularProgressIndicator())
          : _error != null
          ? _errorView()
          : widget.item.kind == HistoryTaskKind.recurring
          ? _recurringView()
          : _repeatUntilDoneView(),
    );
  }

  Widget _errorView() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.error_outline,
            color: AppColors.of(context).textMuted,
            size: 38,
          ),
          SizedBox(height: 12),
          Text(
            _error!,
            style: TextStyle(color: AppColors.of(context).textSecondary),
          ),
          SizedBox(height: 12),
          TextButton(onPressed: _load, child: Text('Try again')),
        ],
      ),
    );
  }

  Widget _recurringView() {
    final task = _asMap(_details['task']);

    final summary = _asMap(_details['summary']);

    final occurrences = _asList(_details['occurrences']);

    final duration = _asMap(task['duration']);

    return ListView(
      padding: EdgeInsets.fromLTRB(20, 18, 20, 50),
      children: [
        _taskHeader(task, 'Recurring'),

        SizedBox(height: 22),

        _section(
          title: 'Duration',
          child: Text(
            '${_date(duration['start_date'])}'
            ' ? '
            '${_date(duration['end_date'])}',
            style: TextStyle(color: AppColors.of(context).textSecondary),
          ),
        ),

        SizedBox(height: 14),

        _summaryCard(summary),

        SizedBox(height: 24),

        Text(
          'Occurrences',
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        ),

        SizedBox(height: 10),

        if (occurrences.isEmpty)
          Text(
            'No occurrences available.',
            style: TextStyle(color: AppColors.of(context).textSecondary),
          )
        else
          ...occurrences.map(_occurrenceRow),
      ],
    );
  }

  Widget _repeatUntilDoneView() {
    final task = _details;

    return ListView(
      padding: EdgeInsets.fromLTRB(20, 18, 20, 50),
      children: [
        _taskHeader(task, 'Repeat Until Done'),

        SizedBox(height: 22),

        _section(
          title: 'Completed',
          child: Row(
            children: [
              Icon(
                Icons.check_circle_outline,
                size: 18,
                color: AppColors.green,
              ),
              SizedBox(width: 8),
              Text(
                _dateTime(task['completed_at']),
                style: TextStyle(color: AppColors.of(context).textSecondary),
              ),
            ],
          ),
        ),

        SizedBox(height: 14),

        _section(
          title: 'Repeat',
          child: Text(
            _repeatText(task['repeat']),
            style: TextStyle(color: AppColors.of(context).textSecondary),
          ),
        ),

        SizedBox(height: 14),

        _section(
          title: 'Priority',
          child: Text(
            _priorityText(task['priority']?.toString()),
            style: TextStyle(color: AppColors.of(context).textSecondary),
          ),
        ),
      ],
    );
  }

  Widget _taskHeader(Map<String, dynamic> task, String type) {
    final description = task['description']?.toString();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          type,
          style: TextStyle(
            color: AppColors.of(context).textSecondary,
            fontSize: 12,
          ),
        ),

        SizedBox(height: 8),

        Text(
          task['title']?.toString() ?? widget.item.title,
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        ),

        if (description != null && description.trim().isNotEmpty) ...[
          SizedBox(height: 8),
          Text(
            description,
            style: TextStyle(
              color: AppColors.of(context).textSecondary,
              height: 1.5,
            ),
          ),
        ],
      ],
    );
  }

  Widget _summaryCard(Map<String, dynamic> summary) {
    final done = _number(summary['done']);

    final missed = _number(summary['missed']);

    final pending = _number(summary['pending']);

    final rate = _number(summary['completion_rate']);

    return Container(
      padding: EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Text('Completion', style: TextStyle(fontWeight: FontWeight.w600)),
              Spacer(),
              Text('$rate%', style: TextStyle(fontWeight: FontWeight.w700)),
            ],
          ),

          SizedBox(height: 10),

          LinearProgressIndicator(
            value: rate.clamp(0, 100) / 100,
            minHeight: 4,
            backgroundColor: AppColors.of(context).border,
            valueColor: AlwaysStoppedAnimation(AppColors.of(context).white),
          ),

          SizedBox(height: 16),

          Row(
            children: [
              Expanded(child: _stat('$done', 'Done')),
              Expanded(child: _stat('$missed', 'Missed')),
              Expanded(child: _stat('$pending', 'Pending')),
            ],
          ),
        ],
      ),
    );
  }

  Widget _stat(String value, String label) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
        ),
        SizedBox(height: 3),
        Text(
          label,
          style: TextStyle(
            color: AppColors.of(context).textSecondary,
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _occurrenceRow(Map<String, dynamic> item) {
    final status = item['status']?.toString() ?? 'pending';

    IconData icon;
    Color color;

    if (status == 'completed') {
      icon = Icons.check_circle;
      color = AppColors.green;
    } else if (status == 'missed') {
      icon = Icons.cancel;
      color = AppColors.red;
    } else {
      icon = Icons.radio_button_unchecked;
      color = AppColors.of(context).textMuted;
    }

    return Container(
      padding: EdgeInsets.symmetric(vertical: 13),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.of(context).border)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 19, color: color),

          SizedBox(width: 12),

          Expanded(child: Text(_date(item['scheduled_date'] ?? item['date']))),

          Text(
            _statusText(status),
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _section({required String title, required Widget child}) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
          SizedBox(height: 8),
          child,
        ],
      ),
    );
  }

  String _statusText(String value) {
    switch (value) {
      case 'completed':
        return 'Done';

      case 'missed':
        return 'Missed';

      default:
        return 'Pending';
    }
  }

  String _repeatText(dynamic raw) {
    final repeat = _asMap(raw);

    switch (repeat['type']?.toString()) {
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

  String _priorityText(String? value) {
    switch (value) {
      case 'important_urgent':
        return 'Important + Urgent';

      case 'important_not_urgent':
        return 'Important';

      case 'not_important_urgent':
        return 'Urgent';

      case 'not_important_not_urgent':
        return 'Low';

      default:
        return 'Not specified';
    }
  }

  String _date(dynamic value) {
    if (value == null) {
      return 'Unknown date';
    }

    final parsed = DateTime.tryParse(value.toString());

    if (parsed == null) {
      return value.toString();
    }

    return DateFormat('d MMM yyyy').format(parsed.toLocal());
  }

  String _dateTime(dynamic value) {
    if (value == null) {
      return 'Completed';
    }

    final parsed = DateTime.tryParse(value.toString());

    if (parsed == null) {
      return value.toString();
    }

    return DateFormat('d MMM yyyy ? h:mm a').format(parsed.toLocal());
  }

  int _number(dynamic value) {
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
