import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../../../core/notifications/notification_service.dart';
import '../../../core/theme/app_colors.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() {
    return _NotificationsScreenState();
  }
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool _loading = true;

  List<_NotificationGroup> _groups = const [];

  @override
  void initState() {
    super.initState();

    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
    });

    try {
      final pending = await NotificationService.instance.pendingNotifications();

      final groups = _groupNotifications(pending);

      if (!mounted) {
        return;
      }

      setState(() {
        _groups = groups;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _groups = const [];
        _loading = false;
      });
    }
  }

  List<_NotificationGroup> _groupNotifications(
    List<PendingNotificationRequest> requests,
  ) {
    final counts = <String, int>{};

    final titles = <String, String>{};

    final bodies = <String, String>{};

    for (final request in requests) {
      final title = request.title?.trim().isNotEmpty == true
          ? request.title!.trim()
          : 'Task reminder';

      final body = request.body?.trim() ?? '';

      final key = '$title::$body';

      counts[key] = (counts[key] ?? 0) + 1;

      titles[key] = title;
      bodies[key] = body;
    }

    final result = counts.entries.map((entry) {
      return _NotificationGroup(
        title: titles[entry.key]!,
        body: bodies[entry.key]!,
        count: entry.value,
      );
    }).toList();

    result.sort(
      (a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()),
    );

    return result;
  }

  int get _totalPending {
    return _groups.fold(0, (total, group) => total + group.count);
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 40),
            children: [
              Row(
                children: [
                  IconButton(
                    onPressed: () {
                      Navigator.pop(context);
                    },
                    icon: const Icon(Icons.arrow_back),
                  ),

                  const SizedBox(width: 4),

                  Expanded(
                    child: Text(
                      'Notifications',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),

                  IconButton(
                    onPressed: _loading ? null : _load,
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),

              const SizedBox(height: 24),

              Text(
                'Upcoming reminders',
                style: TextStyle(
                  color: colors.textPrimary,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),

              const SizedBox(height: 5),

              Text(
                _loading
                    ? 'Checking reminders...'
                    : _totalPending == 0
                    ? 'No reminders are scheduled.'
                    : '$_totalPending reminders are scheduled on this device.',
                style: TextStyle(color: colors.textSecondary, fontSize: 12),
              ),

              const SizedBox(height: 22),

              if (_loading)
                const Padding(
                  padding: EdgeInsets.only(top: 60),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_groups.isEmpty)
                _EmptyState(colors: colors)
              else
                ..._groups.map((group) => _NotificationCard(group: group)),
            ],
          ),
        ),
      ),
    );
  }
}

class _NotificationCard extends StatelessWidget {
  final _NotificationGroup group;

  const _NotificationCard({required this.group});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: colors.surfaceElevated,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.notifications_none,
              color: colors.textSecondary,
              size: 19,
            ),
          ),

          const SizedBox(width: 13),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  group.title,
                  style: TextStyle(
                    color: colors.textPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                if (group.body.isNotEmpty) ...[
                  const SizedBox(height: 4),

                  Text(
                    group.body,
                    style: TextStyle(color: colors.textSecondary, fontSize: 11),
                  ),
                ],

                const SizedBox(height: 7),

                Text(
                  group.count == 1
                      ? '1 upcoming reminder'
                      : '${group.count} upcoming reminders',
                  style: TextStyle(color: colors.textMuted, fontSize: 10),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final AppPalette colors;

  const _EmptyState({required this.colors});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 70),
      child: Column(
        children: [
          Icon(Icons.notifications_none, size: 34, color: colors.textMuted),

          const SizedBox(height: 14),

          Text(
            'No upcoming reminders',
            style: TextStyle(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),

          const SizedBox(height: 6),

          Text(
            'Scheduled task reminders '
            'will appear here.',
            style: TextStyle(color: colors.textSecondary, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _NotificationGroup {
  final String title;
  final String body;
  final int count;

  const _NotificationGroup({
    required this.title,
    required this.body,
    required this.count,
  });
}
