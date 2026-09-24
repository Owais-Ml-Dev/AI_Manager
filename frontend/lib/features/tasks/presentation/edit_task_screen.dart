import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../application/task_providers.dart';

enum EditRepeatType { everyday, weekdays, weekends, customDates }

class EditReminderDraft {
  TimeOfDay start;
  TimeOfDay end;
  int count;

  EditReminderDraft({
    required this.start,
    required this.end,
    required this.count,
  });
}

class EditTaskScreen extends ConsumerStatefulWidget {
  final String taskId;
  final bool recurring;

  const EditTaskScreen({
    super.key,
    required this.taskId,
    required this.recurring,
  });

  @override
  ConsumerState<EditTaskScreen> createState() {
    return _EditTaskScreenState();
  }
}

class _EditTaskScreenState extends ConsumerState<EditTaskScreen> {
  final _titleController = TextEditingController();

  final _descriptionController = TextEditingController();

  String _priority = 'important_urgent';

  EditRepeatType _repeatType = EditRepeatType.everyday;

  DateTime _startDate = DateTime.now();

  DateTime _endDate = DateTime.now();

  final List<DateTime> _customDates = [];

  final List<EditReminderDraft> _reminders = [];

  bool _loading = true;
  bool _saving = false;

  String? _loadError;

  @override
  void initState() {
    super.initState();

    _loadTask();
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();

    super.dispose();
  }

  Future<void> _loadTask() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });

    try {
      final repository = ref.read(taskRepositoryProvider);

      final result = widget.recurring
          ? await repository.getRecurringTask(widget.taskId)
          : await repository.getRepeatUntilDoneTask(widget.taskId);

      final task = _asMap(result);

      if (task.isEmpty) {
        throw ApiException(message: 'Task data could not be loaded.');
      }

      _titleController.text = task['title']?.toString() ?? '';

      _descriptionController.text = task['description']?.toString() ?? '';

      _priority = task['priority']?.toString() ?? 'important_urgent';

      _loadRepeat(task['repeat']);

      _loadReminders(task['reminders']);

      _loadDuration(
        task['duration'],
      );

      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
        _loadError = error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _loading = false;
        _loadError = 'Could not load task.';
      });
    }
  }

  void _loadDuration(dynamic rawDuration) {
    final duration = _asMap(rawDuration);

    final start = DateTime.tryParse(duration['start_date']?.toString() ?? '');

    final end = DateTime.tryParse(duration['end_date']?.toString() ?? '');

    if (start != null) {
      _startDate = start;
    }

    if (end != null) {
      _endDate = end;
    }

    if (_endDate.isBefore(_startDate)) {
      _endDate = _startDate;
    }
  }

  void _loadRepeat(dynamic rawRepeat) {
    final repeat = _asMap(rawRepeat);

    switch (repeat['type']?.toString()) {
      case 'weekdays':
        _repeatType = EditRepeatType.weekdays;
        break;

      case 'weekends':
        _repeatType = EditRepeatType.weekends;
        break;

      case 'custom_dates':
        _repeatType = EditRepeatType.customDates;
        break;

      default:
        _repeatType = EditRepeatType.everyday;
    }

    _customDates.clear();

    final rawDates = repeat['custom_dates'];

    if (rawDates is List) {
      for (final value in rawDates) {
        final date = DateTime.tryParse(value.toString());

        if (date != null) {
          _customDates.add(date);
        }
      }
    }

    _customDates.sort();
  }

  void _loadReminders(dynamic rawReminders) {
    _reminders.clear();

    if (rawReminders is! List) {
      return;
    }

    for (final raw in rawReminders) {
      final reminder = _asMap(raw);

      final start = _parseTime(reminder['start_time']);

      final end = _parseTime(reminder['end_time']);

      final countValue = reminder['count'];

      final count = countValue is int
          ? countValue
          : int.tryParse(countValue?.toString() ?? '') ?? 1;

      _reminders.add(
        EditReminderDraft(start: start, end: end, count: count < 1 ? 1 : count),
      );
    }
  }

  TimeOfDay _parseTime(dynamic value) {
    final text = value?.toString() ?? '';

    final parts = text.split(':');

    if (parts.length < 2) {
      return TimeOfDay(hour: 9, minute: 0);
    }

    final hour = int.tryParse(parts[0]);

    final minute = int.tryParse(parts[1]);

    if (hour == null || minute == null) {
      return TimeOfDay(hour: 9, minute: 0);
    }

    return TimeOfDay(hour: hour, minute: minute);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.of(context).background,
        elevation: 0,
        title: Text(
          'Edit Task',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
      ),

      body: _loading
          ? Center(child: CircularProgressIndicator())
          : _loadError != null
          ? _buildLoadError()
          : _buildForm(),
    );
  }

  Widget _buildLoadError() {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.error_outline,
              size: 38,
              color: AppColors.of(context).textMuted,
            ),
            SizedBox(height: 12),
            Text(
              _loadError!,
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.of(context).textSecondary),
            ),
            SizedBox(height: 16),
            TextButton(onPressed: _loadTask, child: Text('Try again')),
          ],
        ),
      ),
    );
  }

  Widget _buildForm() {
    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(20, 16, 20, 50),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.recurring ? 'Recurring' : 'Repeat Until Done',
              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                fontSize: 12,
              ),
            ),

            SizedBox(height: 24),

            _sectionTitle('Title'),

            TextField(
              controller: _titleController,
              textCapitalization: TextCapitalization.sentences,
              decoration: InputDecoration(hintText: 'Task title'),
            ),

            SizedBox(height: 20),

            _sectionTitle('Description', optional: true),

            TextField(
              controller: _descriptionController,
              minLines: 2,
              maxLines: 5,
              decoration: InputDecoration(hintText: 'Task description'),
            ),

            ...[
              SizedBox(height: 26),

              _sectionTitle('Duration'),

              Row(
                children: [
                  Expanded(
                    child: _dateButton(
                      label: 'Starts',
                      value: _startDate,
                      onTap: _pickStartDate,
                    ),
                  ),
                  SizedBox(width: 12),
                  Expanded(
                    child: _dateButton(
                      label: 'Ends',
                      value: _endDate,
                      onTap: _pickEndDate,
                    ),
                  ),
                ],
              ),
            ],

            SizedBox(height: 26),

            _sectionTitle('Repeat'),

            _repeatSelector(),

            if (_repeatType == EditRepeatType.customDates) ...[
              SizedBox(height: 16),
              _customDateSection(),
            ],

            SizedBox(height: 26),

            Row(
              children: [
                _sectionTitle('Reminders'),
                Spacer(),
                TextButton.icon(
                  onPressed: _addReminder,
                  icon: Icon(Icons.add, size: 17),
                  label: Text('Add'),
                ),
              ],
            ),

            if (_reminders.isEmpty)
              _noReminders()
            else
              ...List.generate(_reminders.length, (index) {
                return _reminderCard(index, _reminders[index]);
              }),

            SizedBox(height: 26),

            _sectionTitle('Priority'),

            _prioritySelector(),

            SizedBox(height: 34),

            SizedBox(
              width: double.infinity,
              height: 52,
              child: FilledButton(
                onPressed: _saving ? null : _save,
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.of(context).white,
                  foregroundColor: AppColors.of(context).onAccent,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                child: _saving
                    ? SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: AppColors.of(context).onAccent,
                        ),
                      )
                    : Text(
                        'Save Changes',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String title, {bool optional = false}) {
    return Padding(
      padding: EdgeInsets.only(bottom: 9),
      child: Row(
        children: [
          Text(
            title,
            style: TextStyle(
              color: AppColors.of(context).textPrimary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (optional)
            Text(
              '  Optional',
              style: TextStyle(
                color: AppColors.of(context).textMuted,
                fontSize: 11,
              ),
            ),
        ],
      ),
    );
  }

  Widget _dateButton({
    required String label,
    required DateTime value,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: AppColors.of(context).surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.of(context).border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: AppColors.of(context).textMuted,
                fontSize: 10,
              ),
            ),
            SizedBox(height: 4),
            Text(
              DateFormat('d MMM yyyy').format(value),
              style: TextStyle(
                color: AppColors.of(context).textPrimary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _repeatSelector() {
    final items = [
      (EditRepeatType.everyday, 'Every day'),
      (EditRepeatType.weekdays, 'Weekdays'),
      (EditRepeatType.weekends, 'Weekends'),
      (EditRepeatType.customDates, 'Custom'),
    ];

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: items.map((item) {
        final selected = _repeatType == item.$1;

        return ChoiceChip(
          label: Text(item.$2),
          selected: selected,
          onSelected: (value) {
            if (!value) {
              return;
            }

            setState(() {
              _repeatType = item.$1;
            });
          },
          backgroundColor: AppColors.of(context).surface,
          selectedColor: AppColors.of(context).white,
          side: BorderSide(color: AppColors.of(context).border),
          labelStyle: TextStyle(
            color: selected
                ? AppColors.of(context).onAccent
                : AppColors.of(context).textSecondary,
            fontWeight: FontWeight.w600,
            fontSize: 12,
          ),
        );
      }).toList(),
    );
  }

  Widget _customDateSection() {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_customDates.isNotEmpty)
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: _customDates.map((date) {
                return InputChip(
                  label: Text(DateFormat('d MMM yyyy').format(date)),
                  onDeleted: () {
                    setState(() {
                      _customDates.remove(date);
                    });
                  },
                );
              }).toList(),
            ),

          if (_customDates.isNotEmpty) SizedBox(height: 10),

          TextButton.icon(
            onPressed: _addCustomDate,
            icon: Icon(Icons.calendar_today_outlined, size: 17),
            label: Text('Add date'),
          ),
        ],
      ),
    );
  }

  Widget _noReminders() {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Text(
        'No reminders added.',
        style: TextStyle(
          color: AppColors.of(context).textSecondary,
          fontSize: 12,
        ),
      ),
    );
  }

  Widget _reminderCard(int index, EditReminderDraft reminder) {
    return Container(
      margin: EdgeInsets.only(bottom: 10),
      padding: EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.of(context).surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.of(context).border),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Text(
                'Reminder window',
                style: TextStyle(
                  color: AppColors.of(context).textPrimary,
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
              Spacer(),
              IconButton(
                onPressed: () {
                  setState(() {
                    _reminders.removeAt(index);
                  });
                },
                icon: Icon(Icons.close, size: 18),
                color: AppColors.of(context).textMuted,
              ),
            ],
          ),

          SizedBox(height: 8),

          Row(
            children: [
              Expanded(
                child: _timeButton(
                  label: 'Start',
                  value: reminder.start,
                  onTap: () async {
                    final value = await showTimePicker(
                      context: context,
                      initialTime: reminder.start,
                    );

                    if (value != null) {
                      setState(() {
                        reminder.start = value;
                      });
                    }
                  },
                ),
              ),

              SizedBox(width: 10),

              Expanded(
                child: _timeButton(
                  label: 'End',
                  value: reminder.end,
                  onTap: () async {
                    final value = await showTimePicker(
                      context: context,
                      initialTime: reminder.end,
                    );

                    if (value != null) {
                      setState(() {
                        reminder.end = value;
                      });
                    }
                  },
                ),
              ),
            ],
          ),

          SizedBox(height: 12),

          Row(
            children: [
              Expanded(
                child: Text(
                  'Number of reminders',
                  style: TextStyle(
                    color: AppColors.of(context).textSecondary,
                    fontSize: 12,
                  ),
                ),
              ),

              IconButton(
                onPressed: reminder.count > 1
                    ? () {
                        setState(() {
                          reminder.count--;
                        });
                      }
                    : null,
                icon: Icon(Icons.remove, size: 18),
              ),

              SizedBox(
                width: 28,
                child: Text(
                  '${reminder.count}',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
              ),

              IconButton(
                onPressed: () {
                  setState(() {
                    reminder.count++;
                  });
                },
                icon: Icon(Icons.add, size: 18),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _timeButton({
    required String label,
    required TimeOfDay value,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        decoration: BoxDecoration(
          color: AppColors.of(context).surfaceElevated,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: AppColors.of(context).textMuted,
                fontSize: 10,
              ),
            ),
            SizedBox(height: 3),
            Text(
              value.format(context),
              style: TextStyle(
                color: AppColors.of(context).textPrimary,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _prioritySelector() {
    final items = [
      ('important_urgent', 'Important + Urgent', AppColors.red),
      ('important_not_urgent', 'Important', AppColors.orange),
      ('not_important_urgent', 'Urgent', AppColors.blue),
      ('not_important_not_urgent', 'Low', AppColors.green),
    ];

    return Column(
      children: items.map((item) {
        final selected = _priority == item.$1;

        return InkWell(
          onTap: () {
            setState(() {
              _priority = item.$1;
            });
          },
          borderRadius: BorderRadius.circular(12),
          child: Container(
            margin: EdgeInsets.only(bottom: 8),
            padding: EdgeInsets.symmetric(horizontal: 14, vertical: 13),
            decoration: BoxDecoration(
              color: AppColors.of(context).surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: selected
                    ? AppColors.of(context).textSecondary
                    : AppColors.of(context).border,
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: item.$3,
                  ),
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    item.$2,
                    style: TextStyle(color: AppColors.of(context).textPrimary),
                  ),
                ),
                if (selected) Icon(Icons.check, size: 18),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  void _addReminder() {
    setState(() {
      _reminders.add(
        EditReminderDraft(
          start: TimeOfDay(hour: 9, minute: 0),
          end: TimeOfDay(hour: 10, minute: 0),
          count: 1,
        ),
      );
    });
  }

  Future<void> _pickStartDate() async {
    final value = await showDatePicker(
      context: context,
      initialDate: _startDate,
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(Duration(days: 3650)),
    );

    if (value == null) {
      return;
    }

    setState(() {
      _startDate = value;

      if (_endDate.isBefore(_startDate)) {
        _endDate = _startDate;
      }

      _removeDatesOutsideDuration();
    });
  }

  Future<void> _pickEndDate() async {
    final value = await showDatePicker(
      context: context,
      initialDate: _endDate.isBefore(_startDate) ? _startDate : _endDate,
      firstDate: _startDate,
      lastDate: _startDate.add(Duration(days: 3650)),
    );

    if (value == null) {
      return;
    }

    setState(() {
      _endDate = value;

      _removeDatesOutsideDuration();
    });
  }

  Future<void> _addCustomDate() async {
    DateTime firstDate;
    DateTime lastDate;
    DateTime initialDate;

    firstDate = _startDate;
    lastDate = _endDate;
    initialDate = _startDate;

    final date = await showDatePicker(
      context: context,
      initialDate: initialDate,
      firstDate: firstDate,
      lastDate: lastDate,
    );

    if (date == null) {
      return;
    }

    final exists = _customDates.any(
      (item) =>
          item.year == date.year &&
          item.month == date.month &&
          item.day == date.day,
    );

    if (exists) {
      return;
    }

    setState(() {
      _customDates.add(date);

      _customDates.sort();
    });
  }

  void _removeDatesOutsideDuration() {
    _customDates.removeWhere(
      (date) => date.isBefore(_startDate) || date.isAfter(_endDate),
    );
  }

  bool _validate() {
    if (_titleController.text.trim().isEmpty) {
      _showMessage('Enter a task title.');

      return false;
    }

    if (_endDate.isBefore(_startDate)) {
      _showMessage('End date cannot be before start date.');

      return false;
    }

    if (_repeatType == EditRepeatType.customDates && _customDates.isEmpty) {
      _showMessage('Choose at least one custom date.');

      return false;
    }

    for (final reminder in _reminders) {
      final startMinutes = reminder.start.hour * 60 + reminder.start.minute;

      final endMinutes = reminder.end.hour * 60 + reminder.end.minute;

      if (startMinutes >= endMinutes) {
        _showMessage('Reminder start time must be before end time.');

        return false;
      }
    }

    return true;
  }

  Future<void> _save() async {
    if (!_validate()) {
      return;
    }

    setState(() {
      _saving = true;
    });

    final payload = <String, dynamic>{
      'title': _titleController.text.trim(),

      'description': _descriptionController.text.trim(),

      'priority': _priority,

      'repeat': {
        'type': _repeatApiValue(),

        'custom_dates': _repeatType == EditRepeatType.customDates
            ? _customDates
                  .map((date) => DateFormat('yyyy-MM-dd').format(date))
                  .toList()
            : <String>[],
      },

      'reminders': _reminders.map((reminder) {
        return {
          'start_time': _timeToString(reminder.start),
          'end_time': _timeToString(reminder.end),
          'count': reminder.count,
        };
      }).toList(),
    };

    payload['duration'] = {
      'start_date':
          DateFormat('yyyy-MM-dd').format(
        _startDate,
      ),
      'end_date':
          DateFormat('yyyy-MM-dd').format(
        _endDate,
      ),
    };

    try {
      final repository = ref.read(taskRepositoryProvider);

      if (widget.recurring) {
        await repository.updateRecurringTask(widget.taskId, payload);
      } else {
        await repository.updateRepeatUntilDoneTask(widget.taskId, payload);
      }

      if (!mounted) {
        return;
      }

      Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }

      _showMessage(error.message);
    } catch (_) {
      if (!mounted) {
        return;
      }

      _showMessage('Could not update task.');
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  String _repeatApiValue() {
    switch (_repeatType) {
      case EditRepeatType.everyday:
        return 'everyday';

      case EditRepeatType.weekdays:
        return 'weekdays';

      case EditRepeatType.weekends:
        return 'weekends';

      case EditRepeatType.customDates:
        return 'custom_dates';
    }
  }

  String _timeToString(TimeOfDay value) {
    final hour = value.hour.toString().padLeft(2, '0');

    final minute = value.minute.toString().padLeft(2, '0');

    return '$hour:$minute';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) {
      return {};
    }

    return value.map((key, item) => MapEntry(key.toString(), item));
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}
