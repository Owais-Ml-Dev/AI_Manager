import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as tz_data;
import 'package:timezone/timezone.dart' as tz;

class NotificationService {
  NotificationService._();

  static final NotificationService instance = NotificationService._();

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  bool _canScheduleExact = false;

  Future<void> initialize({
    required DidReceiveNotificationResponseCallback
    onDidReceiveNotificationResponse,
    required DidReceiveBackgroundNotificationResponseCallback
    onDidReceiveBackgroundNotificationResponse,
  }) async {
    await prepareTimeZone();

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');

    const settings = InitializationSettings(android: android);

    await _plugin.initialize(
      settings: settings,
      onDidReceiveNotificationResponse: onDidReceiveNotificationResponse,
      onDidReceiveBackgroundNotificationResponse:
          onDidReceiveBackgroundNotificationResponse,
    );
  }

  Future<void> prepareTimeZone() async {
    tz_data.initializeTimeZones();

    await _configureLocalTimezone();
  }

  Future<void> _configureLocalTimezone() async {
    final timezoneInfo = await FlutterTimezone.getLocalTimezone();

    final reportedIdentifier = timezoneInfo.identifier;

    final canonicalIdentifier = _canonicalTimezone(reportedIdentifier);

    try {
      final location = tz.getLocation(canonicalIdentifier);

      tz.setLocalLocation(location);

      debugPrint(
        'Notification timezone: '
        '$reportedIdentifier -> '
        '${location.name}',
      );
    } catch (error) {
      debugPrint(
        'Could not load timezone '
        '"$reportedIdentifier": $error. '
        'Using UTC temporarily.',
      );

      tz.setLocalLocation(tz.UTC);
    }
  }

  String _canonicalTimezone(String identifier) {
    const aliases = <String, String>{
      'Asia/Calcutta': 'Asia/Kolkata',
      'Europe/Kiev': 'Europe/Kyiv',
      'America/Godthab': 'America/Nuuk',
    };

    return aliases[identifier] ?? identifier;
  }

  Future<bool> requestPermission() async {
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();

    if (android == null) {
      return true;
    }

    return await android.requestNotificationsPermission() ?? false;
  }

  Future<bool> ensureExactAlarmPermission() async {
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();

    if (android == null) {
      _canScheduleExact = false;
      return false;
    }

    var allowed = await android.canScheduleExactNotifications() ?? false;

    if (!allowed) {
      await android.requestExactAlarmsPermission();

      allowed = await android.canScheduleExactNotifications() ?? false;
    }

    _canScheduleExact = allowed;

    debugPrint(
      'Exact task reminders enabled: '
      '$_canScheduleExact',
    );

    return allowed;
  }

  Future<bool> canScheduleExact() async {
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();

    if (android == null) {
      return false;
    }

    _canScheduleExact = await android.canScheduleExactNotifications() ?? false;

    return _canScheduleExact;
  }

  Future<void> cancelPendingTaskNotifications() async {
    await _plugin.cancelAllPendingNotifications();
  }

  NotificationDetails _taskNotificationDetails() {
    return const NotificationDetails(
      android: AndroidNotificationDetails(
        'task_reminders',
        'Task Reminders',
        channelDescription: 'Reminders for your tasks',
        importance: Importance.high,
        priority: Priority.high,
        category: AndroidNotificationCategory.reminder,

        actions: <AndroidNotificationAction>[
          AndroidNotificationAction(
            'done',
            'Done',
            showsUserInterface: false,
            cancelNotification: true,
          ),
          AndroidNotificationAction(
            'snooze_10',
            'Snooze 10 min',
            showsUserInterface: false,
            cancelNotification: true,
          ),
        ],
      ),
    );
  }

  Future<void> scheduleTaskReminder({
    required int id,
    required String title,
    required String body,
    required DateTime localDateTime,
    required String payload,
  }) async {
    final scheduledDate = tz.TZDateTime(
      tz.local,
      localDateTime.year,
      localDateTime.month,
      localDateTime.day,
      localDateTime.hour,
      localDateTime.minute,
      localDateTime.second,
    );

    final now = tz.TZDateTime.now(tz.local);

    if (!scheduledDate.isAfter(now)) {
      return;
    }

    await _plugin.zonedSchedule(
      id: id,
      title: title,
      body: body,
      scheduledDate: scheduledDate,
      notificationDetails: _taskNotificationDetails(),
      androidScheduleMode: _canScheduleExact
          ? AndroidScheduleMode.exactAllowWhileIdle
          : AndroidScheduleMode.inexactAllowWhileIdle,
      payload: payload,
    );
  }

  Future<void> snoozeTenMinutes({
    required String title,
    required String body,
    required String payload,
  }) async {
    await canScheduleExact();

    // Snooze represents an absolute delay,
    // therefore UTC is safe even from a
    // background isolate.
    tz_data.initializeTimeZones();

    final scheduledDate = tz.TZDateTime.now(tz.UTC)
        .add(const Duration(minutes: 10));

    final now = DateTime.now().millisecondsSinceEpoch;

    // Android notification IDs are signed
    // 32-bit integers.
    final notificationId = 1900000000 + (now % 100000000);

    await _plugin.zonedSchedule(
      id: notificationId,
      title: title,
      body: body,
      scheduledDate: scheduledDate,
      notificationDetails: _taskNotificationDetails(),
      androidScheduleMode: _canScheduleExact
          ? AndroidScheduleMode.exactAllowWhileIdle
          : AndroidScheduleMode.inexactAllowWhileIdle,
      payload: payload,
    );

    debugPrint(
      'Notification snoozed for '
      '10 minutes.',
    );
  }

  Future<List<PendingNotificationRequest>> pendingNotifications() async {
    return _plugin.pendingNotificationRequests();
  }

  Future<int> pendingCount() async {
    final pending = await _plugin.pendingNotificationRequests();

    return pending.length;
  }

  Future<void> showTestNotification() async {
    const details = NotificationDetails(
      android: AndroidNotificationDetails(
        'task_reminders',
        'Task Reminders',
        channelDescription: 'Reminders for your tasks',
        importance: Importance.high,
        priority: Priority.high,
      ),
    );

    await _plugin.show(
      id: 1001,
      title: 'AI Task Manager',
      body: 'Notifications are working.',
      notificationDetails: details,
    );
  }
}
