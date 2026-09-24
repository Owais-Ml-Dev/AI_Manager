import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/notifications/notification_service.dart';
import 'core/notifications/notification_callbacks.dart';
import 'core/notifications/notification_sync_service.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await NotificationService.instance.initialize(
    onDidReceiveNotificationResponse: handleNotificationResponse,
    onDidReceiveBackgroundNotificationResponse: notificationBackgroundHandler,
  );
  await NotificationService.instance.requestPermission();

  await NotificationService.instance.ensureExactAlarmPermission();

  runApp(const ProviderScope(child: AiTaskManagerApp()));

  // The UI starts immediately.
  // Reminder syncing happens in the background.
  unawaited(NotificationSyncService.instance.syncFromBackend());
}
