from pathlib import Path
import sys

backend = Path(sys.argv[1]).resolve()
frontend = Path(sys.argv[2]).resolve()


def read(p):
    return p.read_text(encoding='utf-8-sig')


def write(p, s):
    p.write_text(s, encoding='utf-8')


def rep(p, old, new, count=1):
    s = read(p)
    if old not in s:
        raise RuntimeError(f'Expected block not found in {p}')
    write(p, s.replace(old, new, count))


# =========================================================
# 1. REPEAT UNTIL DONE VALIDATION
#    Reuse the already-correct recurring duration/repeat
#    validation rules.
# =========================================================

rec_v = (
    backend
    / 'src/modules/tasks/recurring/validation.py'
)

rud_v = (
    backend
    / 'src/modules/tasks/repeat_until_done/validation.py'
)

s = read(rec_v)

s = s.replace(
    'validate_create_recurring_task',
    'validate_create_repeat_until_done_task'
)

s = s.replace(
    'validate_update_recurring_task',
    'validate_update_repeat_until_done_task'
)

write(
    rud_v,
    s
)


# =========================================================
# 2. REPEAT UNTIL DONE SERVICE
#    Store, return and update duration.
# =========================================================

p = (
    backend
    / 'src/modules/tasks/repeat_until_done/service.py'
)

rep(
    p,
    '''        "priority":\n            task["priority"],\n\n        # Repeat configuration.''',
    '''        "priority":\n            task["priority"],\n\n        "duration":\n            task.get("duration"),\n\n        # Repeat configuration.'''
)

rep(
    p,
    '''        "priority":\n            data["priority"],\n\n        # Store repeat configuration.''',
    '''        "priority":\n            data["priority"],\n\n        "duration": {\n            "start_date": data["duration"]["start_date"],\n            "end_date": data["duration"]["end_date"],\n        },\n\n        # Store repeat configuration.'''
)

rep(
    p,
    '''    # -----------------------------------------------------\n    # REPEAT\n    # -----------------------------------------------------\n\n    if "repeat" in data:''',
    '''    # -----------------------------------------------------\n    # DURATION\n    # -----------------------------------------------------\n\n    if "duration" in data:\n        update_data["duration"] = {\n            "start_date": data["duration"]["start_date"],\n            "end_date": data["duration"]["end_date"],\n        }\n\n    # -----------------------------------------------------\n    # REPEAT\n    # -----------------------------------------------------\n\n    if "repeat" in data:'''
)


# =========================================================
# 3. REPEAT UNTIL DONE CONTROLLER
#    Validate PATCH using current task so custom dates
#    remain consistent with duration.
# =========================================================

p = (
    backend
    / 'src/modules/tasks/repeat_until_done/controller.py'
)

rep(
    p,
    '''    # Validate the partial update.\n    errors = (\n        validate_update_repeat_until_done_task(\n            data\n        )\n    )\n\n    if errors:\n        return jsonify({\n            "success":\n                False,\n\n            "message":\n                "Validation failed.",\n\n            "errors":\n                errors\n        }), 400\n\n    try:\n        result = (\n            update_repeat_until_done_task(\n                task_id,\n                data\n            )\n        )\n\n    except InvalidId:\n        return jsonify({\n            "success":\n                False,\n\n            "message":\n                "Invalid task ID."\n        }), 400\n''',
    '''    try:\n        current_task = get_repeat_until_done_task(task_id)\n    except InvalidId:\n        return jsonify({\n            "success": False,\n            "message": "Invalid task ID."\n        }), 400\n\n    if current_task is None:\n        return jsonify({\n            "success": False,\n            "message": "Repeat Until Done task not found."\n        }), 404\n\n    if current_task.get("status") == "completed":\n        return jsonify({\n            "success": False,\n            "message": "Completed Repeat Until Done tasks cannot be updated."\n        }), 409\n\n    errors = validate_update_repeat_until_done_task(\n        data,\n        current_task\n    )\n\n    if errors:\n        return jsonify({\n            "success": False,\n            "message": "Validation failed.",\n            "errors": errors,\n        }), 400\n\n    result = update_repeat_until_done_task(\n        task_id,\n        data\n    )\n'''
)


# =========================================================
# 4. ASSISTANT CREATE FLOW
#    Duration required for BOTH task types.
#    Ask reminder count for EACH reminder window.
# =========================================================

p = (
    backend
    / 'src/modules/assistant/create_flow.py'
)

rep(
    p,
    '''    # ---- 1. Dates (recurring only) -----------------------------------\n    if action == "create_recurring_task":''',
    '''    # ---- 1. Dates (both task types) ----------------------------------\n    if action in CREATE_ACTIONS:'''
)

rep(
    p,
    '''    if not repeat.get("type"):\n        if action == "create_recurring_task":\n            question = (\n                f"How should it repeat between {_pretty_date(start)} and "\n                f"{_pretty_date(end)}: every day, weekdays, weekends, or custom dates?"\n            )\n        else:\n            question = (\n                "How often should I remind you until it's done: every day, "\n                "weekdays, weekends, or custom dates?"\n            )\n        return {''',
    '''    if not repeat.get("type"):\n        question = (\n            f"How should it repeat between {_pretty_date(start)} and "\n            f"{_pretty_date(end)}: every day, weekdays, weekends, or custom dates?"\n        )\n        return {'''
)

rep(
    p,
    '''        where = (\n            f" (between {_pretty_date(start)} and {_pretty_date(end)})"\n            if action == "create_recurring_task"\n            else ""\n        )''',
    '''        where = (
            f" (between {_pretty_date(start)} "
            f"and {_pretty_date(end)})"
        )'''
)

rep(
    p,
    '''    # ---- 5. Start and end time for each window --------------------------\n    if count and len(windows) < count:''',
    '''    # ---- 5. Reminder count inside each entered window -----------------\n    confirmed_counts = int(\n        collect.get("confirmed_window_counts") or 0\n    )\n\n    if confirmed_counts < len(windows):\n        number = confirmed_counts + 1\n        window = windows[confirmed_counts]\n\n        return {\n            "field": "reminders.window_reminder_count",\n            "question": (\n                f"How many reminders should I send in reminder window {number} "\n                f"({_pretty_time(window.get('start_time'))} - "\n                f"{_pretty_time(window.get('end_time'))})? (1 to 20)"\n            ),\n            "suggestions": ["1", "2", "3"],\n        }\n\n    # ---- 6. Start and end time for next window ---------------------------\n    if count and len(windows) < count:'''
)

rep(
    p,
    '''    "reminders.window": (\n        "Sorry, I didn't get the times. Give a start and end time with AM/PM, "\n        "for example: 9 am to 11 am, or 18:00 to 19:30."\n    ),''',
    '''    "reminders.window": (\n        "Sorry, I didn't get the times. Give a start and end time with AM/PM, "\n        "for example: 9 am to 11 am, or 18:00 to 19:30."\n    ),\n    "reminders.window_reminder_count": (\n        "How many reminders should I send in this window? "\n        "Reply with a number from 1 to 20."\n    ),'''
)

rep(
    p,
    '''    elif field == "reminders.window":\n        windows, ambiguous = parse_reminder_windows(reply, lenient=True)\n        if ambiguous:\n            _hold_for_meridiem(collect, reply, True)\n            understood = True\n        elif windows:\n            _set_windows(task, collect, windows)\n            understood = True\n\n    if understood:''',
    '''    elif field == "reminders.window":\n        windows, ambiguous = parse_reminder_windows(\n            reply,\n            lenient=True\n        )\n\n        if ambiguous:\n            _hold_for_meridiem(\n                collect,\n                reply,\n                True\n            )\n            understood = True\n\n        elif windows:\n            _set_windows(\n                task,\n                collect,\n                windows\n            )\n            understood = True\n\n    elif field == "reminders.window_reminder_count":\n        count_value = extract_count(reply)\n\n        confirmed_counts = int(\n            collect.get("confirmed_window_counts") or 0\n        )\n\n        windows = _windows(task)\n\n        if (\n            count_value\n            and confirmed_counts < len(windows)\n        ):\n            windows[confirmed_counts]["count"] = min(\n                count_value,\n                20\n            )\n\n            task["reminders"] = windows\n\n            collect["confirmed_window_counts"] = (\n                confirmed_counts + 1\n            )\n\n            understood = True\n\n    if understood:'''
)

rep(
    p,
    '''    if action != "create_recurring_task":\n        task.pop("duration", None)\n\n    if _windows(task) and collect.get("window_count") is None:''',
    '''    if _windows(task) and collect.get("window_count") is None:'''
)


# =========================================================
# 5. ASSISTANT SLOT FILLER
#    Preserve duration for Repeat Until Done.
# =========================================================

p = (
    backend
    / 'src/modules/assistant/slot_filler.py'
)

rep(
    p,
    '''        if key == "duration" and action != "create_recurring_task":\n            continue''',
    '''        if key == "duration" and action not in {
            "create_recurring_task",
            "create_repeat_until_done_task",
        }:
            continue'''
)


# =========================================================
# 6. ASSISTANT DRAFT VALIDATION
#    Do not remove RUD duration.
# =========================================================

p = (
    backend
    / 'src/modules/assistant/draft_validation.py'
)

rep(
    p,
    '''    if action != "create_recurring_task":\n        task.pop("duration", None)\n\n    def needs(step, prefix=""):''',
    '''    def needs(step, prefix=""):'''
)

rep(
    p,
    '''                if prefix == "reminders":\n                    collect.pop("window_count", None)\n                break''',
    '''                if prefix == "reminders":
                    collect.pop(
                        "window_count",
                        None
                    )

                    collect.pop(
                        "confirmed_window_counts",
                        None
                    )

                break'''
)


# =========================================================
# 7. ASSISTANT COMMAND EXECUTOR
# =========================================================

p = (
    backend
    / 'src/modules/assistant/command_executor.py'
)

rep(
    p,
    '''        errors = validate_update_repeat_until_done_task(changes)''',
    '''        errors = validate_update_repeat_until_done_task(
            changes,
            current
        )'''
)


# =========================================================
# 8. GEMINI TASK COMMAND PROMPT
#    Both task types support duration.
# =========================================================

p = (
    backend
    / 'src/modules/assistant/prompts/task_command_prompt.py'
)

rep(
    p,
    '''- start_date / end_date: YYYY-MM-DD. "for 7 days" starting today means\n  end_date = today + 6 days. Use TODAY for relative dates.''',
    '''- start_date / end_date: YYYY-MM-DD for BOTH create_recurring_task and
  create_repeat_until_done_task. "for 7 days" starting today means
  end_date = today + 6 days. Use TODAY for relative dates.'''
)


# =========================================================
# 9. FLUTTER NEW TASK SCREEN
#    Show duration for BOTH task types.
# =========================================================

p = (
    frontend
    / 'lib/features/tasks/presentation/new_task_screen.dart'
)

rep(
    p,
    '''              if (_taskType == NewTaskType.recurring) ...[''',
    '''              ...['''
)

rep(
    p,
    '''    final firstDate = _taskType == NewTaskType.recurring\n        ? _startDate\n        : DateTime.now();\n\n    final lastDate = _taskType == NewTaskType.recurring\n        ? _endDate\n        : DateTime.now().add(Duration(days: 3650));''',
    '''    final firstDate = _startDate;
    final lastDate = _endDate;'''
)

rep(
    p,
    '''  void _removeCustomDatesOutsideDuration() {\n    if (_taskType != NewTaskType.recurring) {\n      return;\n    }\n\n    _customDates.removeWhere(''',
    '''  void _removeCustomDatesOutsideDuration() {
    _customDates.removeWhere('''
)

rep(
    p,
    '''    if (_repeatType == RepeatType.customDates && _customDates.isEmpty) {''',
    '''    if (_endDate.isBefore(_startDate)) {
      _showMessage(
        'End date cannot be before start date.',
      );
      return false;
    }

    if (_repeatType == RepeatType.customDates && _customDates.isEmpty) {'''
)

rep(
    p,
    '''    if (_taskType == NewTaskType.recurring) {\n      payload['duration'] = {\n        'start_date': DateFormat('yyyy-MM-dd').format(_startDate),\n\n        'end_date': DateFormat('yyyy-MM-dd').format(_endDate),\n      };\n    }''',
    '''    payload['duration'] = {
      'start_date':
          DateFormat('yyyy-MM-dd').format(
        _startDate,
      ),
      'end_date':
          DateFormat('yyyy-MM-dd').format(
        _endDate,
      ),
    };'''
)


# =========================================================
# 10. FLUTTER EDIT TASK SCREEN
#     Load/show/save duration for BOTH types.
# =========================================================

p = (
    frontend
    / 'lib/features/tasks/presentation/edit_task_screen.dart'
)

rep(
    p,
    '''      if (widget.recurring) {\n        _loadDuration(task['duration']);\n      }''',
    '''      _loadDuration(
        task['duration'],
      );'''
)

rep(
    p,
    '''            if (widget.recurring) ...[''',
    '''            ...['''
)

rep(
    p,
    '''    if (widget.recurring) {\n      firstDate = _startDate;\n      lastDate = _endDate;\n      initialDate = _startDate;\n    } else {\n      final today = DateTime.now();\n\n      firstDate = DateTime(today.year, today.month, today.day);\n\n      lastDate = firstDate.add(Duration(days: 3650));\n\n      initialDate = firstDate;\n    }''',
    '''    firstDate = _startDate;
    lastDate = _endDate;
    initialDate = _startDate;'''
)

rep(
    p,
    '''  void _removeDatesOutsideDuration() {\n    if (!widget.recurring) {\n      return;\n    }\n\n    _customDates.removeWhere(''',
    '''  void _removeDatesOutsideDuration() {
    _customDates.removeWhere('''
)

rep(
    p,
    '''    if (widget.recurring && _endDate.isBefore(_startDate)) {''',
    '''    if (_endDate.isBefore(_startDate)) {'''
)

rep(
    p,
    '''    if (widget.recurring) {\n      payload['duration'] = {\n        'start_date': DateFormat('yyyy-MM-dd').format(_startDate),\n\n        'end_date': DateFormat('yyyy-MM-dd').format(_endDate),\n      };\n    }''',
    '''    payload['duration'] = {
      'start_date':
          DateFormat('yyyy-MM-dd').format(
        _startDate,
      ),
      'end_date':
          DateFormat('yyyy-MM-dd').format(
        _endDate,
      ),
    };'''
)


# =========================================================
# 11. HOME
#     Repeat Until Done is only due inside its duration.
# =========================================================

p = (
    frontend
    / 'lib/features/home/data/home_repository.dart'
)

rep(
    p,
    '''      if (!_isDueToday(task['repeat'])) {''',
    '''      if (!_isDueToday(
        task['repeat'],
        task['duration'],
      )) {'''
)

rep(
    p,
    '''  bool _isDueToday(dynamic rawRepeat) {\n    final repeat = _asMap(rawRepeat);\n\n    final type = repeat['type']?.toString();\n\n    final now = DateTime.now();''',
    '''  bool _isDueToday(
    dynamic rawRepeat,
    dynamic rawDuration,
  ) {
    final repeat = _asMap(
      rawRepeat,
    );

    final duration = _asMap(
      rawDuration,
    );

    final type =
        repeat['type']?.toString();

    final now = DateTime.now();

    final today = DateTime(
      now.year,
      now.month,
      now.day,
    );

    final start = DateTime.tryParse(
      duration['start_date']
              ?.toString() ??
          '',
    );

    final end = DateTime.tryParse(
      duration['end_date']
              ?.toString() ??
          '',
    );

    if (start != null) {
      final startDate = DateTime(
        start.year,
        start.month,
        start.day,
      );

      if (today.isBefore(startDate)) {
        return false;
      }
    }

    if (end != null) {
      final endDate = DateTime(
        end.year,
        end.month,
        end.day,
      );

      if (today.isAfter(endDate)) {
        return false;
      }
    }'''
)

rep(
    p,
    '''        final today = DateFormat('yyyy-MM-dd').format(now);''',
    '''        final todayText =
            DateFormat(
          'yyyy-MM-dd',
        ).format(
          now,
        );'''
)

rep(
    p,
    '''        return dates.map((date) => date.toString()).contains(today);''',
    '''        return dates
            .map(
              (date) =>
                  date.toString(),
            )
            .contains(
              todayText,
            );'''
)


# =========================================================
# 12. NOTIFICATIONS
#     Respect Repeat Until Done start/end duration.
# =========================================================

p = (
    frontend
    / 'lib/core/notifications/notification_sync_service.dart'
)

rep(
    p,
    '''      final repeat = _asMap(task['repeat']);\n\n      final times = _generatedTimes(task['reminders']);''',
    '''      final repeat =
          _asMap(
        task['repeat'],
      );

      final duration =
          _asMap(
        task['duration'],
      );

      final rawStart =
          DateTime.tryParse(
        duration['start_date']
                ?.toString() ??
            '',
      );

      final rawEnd =
          DateTime.tryParse(
        duration['end_date']
                ?.toString() ??
            '',
      );

      var firstScheduledDate =
          startDate;

      if (rawStart != null) {
        final date = DateTime(
          rawStart.year,
          rawStart.month,
          rawStart.day,
        );

        if (date.isAfter(
          firstScheduledDate,
        )) {
          firstScheduledDate =
              date;
        }
      }

      final durationEnd =
          rawEnd == null
              ? null
              : DateTime(
                  rawEnd.year,
                  rawEnd.month,
                  rawEnd.day,
                );

      if (
          durationEnd != null &&
          firstScheduledDate
              .isAfter(
            durationEnd,
          )) {
        continue;
      }

      final times =
          _generatedTimes(
        task['reminders'],
      );'''
)

rep(
    p,
    '''      for (var offset = 0; offset < _repeatUntilDoneHorizonDays; offset++) {\n        final date = startDate.add(Duration(days: offset));\n\n        if (!_repeatMatchesDate(repeat, date)) {''',
    '''      for (
        var offset = 0;
        offset <
            _repeatUntilDoneHorizonDays;
        offset++
      ) {
        final date =
            firstScheduledDate.add(
          Duration(
            days: offset,
          ),
        );

        if (
            durationEnd != null &&
            date.isAfter(
              durationEnd,
            )) {
          break;
        }

        if (!_repeatMatchesDate(
          repeat,
          date,
        )) {'''
)


# =========================================================
# 13. BACKEND TEST FIXTURES
# =========================================================

for rel, old, new in [
    (
        'tests/test_repeat_until_done.py',
        '''        "priority": "important_urgent",\n        "repeat": {''',
        '''        "priority": "important_urgent",\n        "duration": {"start_date": "2099-09-01", "end_date": "2099-09-30"},\n        "repeat": {'''
    ),
    (
        'tests/test_repeat_until_done_edges.py',
        '''        "priority": "important_urgent",\n        "repeat": {''',
        '''        "priority": "important_urgent",\n        "duration": {"start_date": "2099-01-01", "end_date": "2099-12-31"},\n        "repeat": {'''
    ),
    (
        'tests/test_assistant_task_commands.py',
        '''        "priority": "important_urgent",\n        "repeat": {"type": "everyday", "custom_dates": []},''',
        '''        "priority": "important_urgent",\n        "duration": {"start_date": "2099-01-01", "end_date": "2099-12-31"},\n        "repeat": {"type": "everyday", "custom_dates": []},'''
    ),
]:
    rep(
        backend / rel,
        old,
        new
    )


# =========================================================
# 14. ASSISTANT FOLLOW-UP TESTS
# =========================================================

p = (
    backend
    / 'tests/test_assistant_followups.py'
)

rep(
    p,
    '''        ["from today to 15 oct", "weekdays", "2", "9 am to 11 am", "6-8 pm"],
    )
    assert asked == ["duration", "repeat", "reminders.count", "reminders.window", "reminders.window"]''',
    '''        [
            "from today to 15 oct",
            "weekdays",
            "2",
            "9 am to 11 am",
            "2",
            "6-8 pm",
            "3",
        ],
    )

    assert asked == [
        "duration",
        "repeat",
        "reminders.count",
        "reminders.window",
        "reminders.window_reminder_count",
        "reminders.window",
        "reminders.window_reminder_count",
    ]'''
)

rep(
    p,
    '''        ["everyday", "1", "4:22", "pm"],
    )
    assert asked == ["repeat", "reminders.count", "reminders.window", "reminders.meridiem"]''',
    '''        [
            "from today to 15 oct",
            "everyday",
            "1",
            "4:22",
            "pm",
            "3",
        ],
    )

    assert asked == [
        "duration",
        "repeat",
        "reminders.count",
        "reminders.window",
        "reminders.meridiem",
        "reminders.window_reminder_count",
    ]'''
)

rep(
    p,
    '''        result = _run(["Add buy task", "Everyday", "1", "4:22"])
        assert "AM or PM" in result["question"]
        result = _run_more(result, ["PM"])''',
    '''        result = _run([
            "Add buy task",
            "today for 2 weeks",
            "Everyday",
            "1",
            "4:22",
        ])

        assert "AM or PM" in result["question"]

        result = _run_more(
            result,
            [
                "PM",
                "3",
            ],
        )'''
)

rep(
    p,
    '''        result = _run(["Create buy", "weekends", "1", "7 pm to 9 pm"])''',
    '''        result = _run([
            "Create buy",
            "today for 2 weeks",
            "weekends",
            "1",
            "7 pm to 9 pm",
            "2",
        ])'''
)


print()
print(
    "SUCCESS: Repeat Until Done duration "
    "+ per-window reminder count patch applied."
)
print()
print(
    "Updated backend and frontend files."
)
