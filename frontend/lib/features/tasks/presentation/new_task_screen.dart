import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../home/application/home_providers.dart';
import '../application/task_providers.dart';

enum NewTaskType { recurring, repeatUntilDone }

enum RepeatType { everyday, weekdays, weekends, customDates }

class ReminderDraft {
  TimeOfDay start;
  TimeOfDay end;
  int count;

  ReminderDraft({required this.start, required this.end, this.count = 1});
}

class NewTaskScreen extends ConsumerStatefulWidget {
  const NewTaskScreen({super.key});

  @override
  ConsumerState<NewTaskScreen> createState() {
    return _NewTaskScreenState();
  }
}

class _NewTaskScreenState extends ConsumerState<NewTaskScreen> {
  final _titleController = TextEditingController();

  final _descriptionController = TextEditingController();

  NewTaskType _taskType = NewTaskType.recurring;

  RepeatType _repeatType = RepeatType.everyday;

  String _priority = 'important_urgent';

  DateTime _startDate = DateTime.now();

  DateTime _endDate = DateTime.now().add(Duration(days: 30));

  final List<DateTime> _customDates = [];

  final List<ReminderDraft> _reminders = [
    ReminderDraft(
      start: TimeOfDay(hour: 9, minute: 0),
      end: TimeOfDay(hour: 10, minute: 0),
    ),
  ];

  bool _saving = false;

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppColors.of(context).background,

        elevation: 0,

        leading: IconButton(
          onPressed: () {
            Navigator.pop(context);
          },
          icon: Icon(Icons.arrow_back),
        ),

        title: Text(
          'New Task',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
      ),

      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(20, 16, 20, 120),

          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,

            children: [
              _sectionTitle('Task type'),

              _taskTypeSelector(),

              SizedBox(height: 26),

              _sectionTitle('Title'),

              TextField(
                controller: _titleController,

                textCapitalization: TextCapitalization.sentences,

                decoration: InputDecoration(
                  hintText: 'What do you need to do?',
                ),
              ),

              SizedBox(height: 18),

              _sectionTitle('Description', optional: true),

              TextField(
                controller: _descriptionController,

                textCapitalization: TextCapitalization.sentences,

                minLines: 2,
                maxLines: 4,

                decoration: InputDecoration(hintText: 'Add some details'),
              ),

              if (_taskType == NewTaskType.recurring) ...[
                SizedBox(height: 26),

                _sectionTitle('Duration'),

                Row(
                  children: [
                    Expanded(
                      child: _dateButton(
                        label: 'Starts',
                        value: _startDate,
                        onTap: () {
                          _pickStartDate();
                        },
                      ),
                    ),

                    SizedBox(width: 12),

                    Expanded(
                      child: _dateButton(
                        label: 'Ends',
                        value: _endDate,
                        onTap: () {
                          _pickEndDate();
                        },
                      ),
                    ),
                  ],
                ),
              ],

              SizedBox(height: 26),

              _sectionTitle('Repeat'),

              _repeatSelector(),

              if (_repeatType == RepeatType.customDates) ...[
                SizedBox(height: 16),

                _customDatePicker(),
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

              SizedBox(height: 4),

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
                          'Create Task',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                ),
              ),
            ],
          ),
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

  Widget _taskTypeSelector() {
    return Container(
      padding: EdgeInsets.all(4),

      decoration: BoxDecoration(
        color: AppColors.of(context).surface,

        borderRadius: BorderRadius.circular(13),

        border: Border.all(color: AppColors.of(context).border),
      ),

      child: Row(
        children: [
          Expanded(
            child: _segmentButton(
              title: 'Recurring',

              selected: _taskType == NewTaskType.recurring,

              onTap: () {
                setState(() {
                  _taskType = NewTaskType.recurring;
                });
              },
            ),
          ),

          Expanded(
            child: _segmentButton(
              title: 'Repeat Until Done',

              selected: _taskType == NewTaskType.repeatUntilDone,

              onTap: () {
                setState(() {
                  _taskType = NewTaskType.repeatUntilDone;
                });
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _segmentButton({
    required String title,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,

      borderRadius: BorderRadius.circular(10),

      child: AnimatedContainer(
        duration: Duration(milliseconds: 150),

        padding: EdgeInsets.symmetric(vertical: 11, horizontal: 8),

        decoration: BoxDecoration(
          color: selected
              ? AppColors.of(context).surfaceElevated
              : Colors.transparent,

          borderRadius: BorderRadius.circular(10),
        ),

        child: Text(
          title,

          textAlign: TextAlign.center,

          style: TextStyle(
            color: selected
                ? AppColors.of(context).textPrimary
                : AppColors.of(context).textSecondary,

            fontSize: 12,

            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }

  Widget _repeatSelector() {
    final items = [
      (RepeatType.everyday, 'Every day'),
      (RepeatType.weekdays, 'Weekdays'),
      (RepeatType.weekends, 'Weekends'),
      (RepeatType.customDates, 'Custom'),
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

          labelStyle: TextStyle(
            color: selected
                ? AppColors.of(context).onAccent
                : AppColors.of(context).textSecondary,

            fontSize: 12,

            fontWeight: FontWeight.w600,
          ),

          side: BorderSide(color: AppColors.of(context).border),

          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(100),
          ),
        );
      }).toList(),
    );
  }

  Widget _customDatePicker() {
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
          Wrap(
            spacing: 7,
            runSpacing: 7,

            children: _customDates.map((date) {
              return InputChip(
                label: Text(DateFormat('d MMM').format(date)),

                onDeleted: () {
                  setState(() {
                    _customDates.remove(date);
                  });
                },
              );
            }).toList(),
          ),

          if (_customDates.isNotEmpty) SizedBox(height: 8),

          TextButton.icon(
            onPressed: _addCustomDate,

            icon: Icon(Icons.calendar_today_outlined, size: 17),

            label: Text('Add date'),
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

  Widget _reminderCard(int index, ReminderDraft reminder) {
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
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),

              Spacer(),

              if (_reminders.length > 1)
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

          SizedBox(height: 10),

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

          SizedBox(height: 13),

          Row(
            children: [
              Text(
                'Number of reminders',
                style: TextStyle(
                  color: AppColors.of(context).textSecondary,
                  fontSize: 12,
                ),
              ),

              Spacer(),

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
                  style: TextStyle(
                    color: AppColors.of(context).textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
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

            padding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),

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

                    style: TextStyle(
                      color: AppColors.of(context).textPrimary,
                      fontSize: 12,
                    ),
                  ),
                ),

                if (selected)
                  Icon(
                    Icons.check,
                    size: 18,
                    color: AppColors.of(context).white,
                  ),
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
        ReminderDraft(
          start: TimeOfDay(hour: 9, minute: 0),
          end: TimeOfDay(hour: 10, minute: 0),
        ),
      );
    });
  }

  Future<void> _addCustomDate() async {
    final firstDate = _taskType == NewTaskType.recurring
        ? _startDate
        : DateTime.now();

    final lastDate = _taskType == NewTaskType.recurring
        ? _endDate
        : DateTime.now().add(Duration(days: 3650));

    final date = await showDatePicker(
      context: context,

      initialDate: firstDate,

      firstDate: firstDate,

      lastDate: lastDate,
    );

    if (date == null) {
      return;
    }

    final alreadyExists = _customDates.any(
      (item) =>
          item.year == date.year &&
          item.month == date.month &&
          item.day == date.day,
    );

    if (!alreadyExists) {
      setState(() {
        _customDates.add(date);

        _customDates.sort();
      });
    }
  }

  Future<void> _pickStartDate() async {
    final value = await showDatePicker(
      context: context,

      initialDate: _startDate,

      firstDate: DateTime.now(),

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

      _removeCustomDatesOutsideDuration();
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

      _removeCustomDatesOutsideDuration();
    });
  }

  void _removeCustomDatesOutsideDuration() {
    if (_taskType != NewTaskType.recurring) {
      return;
    }

    _customDates.removeWhere(
      (date) => date.isBefore(_startDate) || date.isAfter(_endDate),
    );
  }

  String _timeToString(TimeOfDay value) {
    final hour = value.hour.toString().padLeft(2, '0');

    final minute = value.minute.toString().padLeft(2, '0');

    return '$hour:$minute';
  }

  String _repeatApiValue() {
    switch (_repeatType) {
      case RepeatType.everyday:
        return 'everyday';

      case RepeatType.weekdays:
        return 'weekdays';

      case RepeatType.weekends:
        return 'weekends';

      case RepeatType.customDates:
        return 'custom_dates';
    }
  }

  bool _validate() {
    if (_titleController.text.trim().isEmpty) {
      _showMessage('Enter a task title.');

      return false;
    }

    if (_repeatType == RepeatType.customDates && _customDates.isEmpty) {
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

    final repeat = {
      'type': _repeatApiValue(),

      'custom_dates': _repeatType == RepeatType.customDates
          ? _customDates
                .map((date) => DateFormat('yyyy-MM-dd').format(date))
                .toList()
          : <String>[],
    };

    final reminders = _reminders.map((reminder) {
      return {
        'start_time': _timeToString(reminder.start),

        'end_time': _timeToString(reminder.end),

        'count': reminder.count,
      };
    }).toList();

    final payload = <String, dynamic>{
      'title': _titleController.text.trim(),

      'description': _descriptionController.text.trim(),

      'priority': _priority,

      'repeat': repeat,

      'reminders': reminders,
    };

    if (_taskType == NewTaskType.recurring) {
      payload['duration'] = {
        'start_date': DateFormat('yyyy-MM-dd').format(_startDate),

        'end_date': DateFormat('yyyy-MM-dd').format(_endDate),
      };
    }

    try {
      final repository = ref.read(taskRepositoryProvider);

      if (_taskType == NewTaskType.recurring) {
        await repository.createRecurringTask(payload);
      } else {
        await repository.createRepeatUntilDoneTask(payload);
      }

      ref.invalidate(homeDataProvider);

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

      _showMessage('Could not create task.');
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}
