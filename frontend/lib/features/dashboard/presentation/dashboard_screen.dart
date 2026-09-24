import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../application/dashboard_providers.dart';
import '../domain/dashboard_data.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashboard = ref.watch(dashboardDataProvider);

    return SafeArea(
      child: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(dashboardDataProvider);

          await ref.read(dashboardDataProvider.future);
        },

        child: SingleChildScrollView(
          physics: AlwaysScrollableScrollPhysics(),

          padding: EdgeInsets.fromLTRB(20, 24, 20, 110),

          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,

            children: [
              Text(
                'Dashboard',

                style: Theme.of(context).textTheme.headlineMedium,
              ),

              SizedBox(height: 5),

              Text(
                'See how your week is going',

                style: TextStyle(
                  color: AppColors.of(context).textSecondary,
                  fontSize: 13,
                ),
              ),

              SizedBox(height: 26),

              dashboard.when(
                loading: () => _LoadingState(),

                error: (error, stackTrace) => _ErrorState(
                  message: error.toString(),

                  onRetry: () {
                    ref.invalidate(dashboardDataProvider);
                  },
                ),

                data: (data) => _DashboardContent(data: data),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DashboardContent extends StatelessWidget {
  final DashboardData data;

  const _DashboardContent({required this.data});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,

      children: [
        Text(
          _weekText(),

          style: TextStyle(
            color: AppColors.of(context).textSecondary,
            fontSize: 12,
          ),
        ),

        SizedBox(height: 15),

        Row(
          children: [
            Expanded(
              child: _SummaryCard(
                icon: Icons.check_circle_outline,
                value: '${data.done}',
                label: 'Done',
                color: AppColors.green,
              ),
            ),

            SizedBox(width: 10),

            Expanded(
              child: _SummaryCard(
                icon: Icons.cancel_outlined,
                value: '${data.missed}',
                label: 'Missed',
                color: AppColors.red,
              ),
            ),

            SizedBox(width: 10),

            Expanded(
              child: _SummaryCard(
                icon: Icons.local_fire_department_outlined,
                value: '${data.streak}',
                label: 'Streak',
                color: AppColors.orange,
              ),
            ),
          ],
        ),

        SizedBox(height: 28),

        _SectionTitle(title: 'Completed this week'),

        SizedBox(height: 12),

        _DailyChart(days: data.dailyCompletion),

        SizedBox(height: 28),

        Row(
          children: [
            Expanded(child: _SectionTitle(title: 'Priority Matrix')),

            Text(
              '${data.totalActivePriorityTasks} active',

              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                fontSize: 11,
              ),
            ),
          ],
        ),

        SizedBox(height: 12),

        _PriorityMatrix(data: data),

        SizedBox(height: 28),

        _SectionTitle(title: 'Insight'),

        SizedBox(height: 12),

        _InsightCard(insight: data.insight),
      ],
    );
  }

  String _weekText() {
    final start = DateTime.tryParse(data.weekStart);

    final end = DateTime.tryParse(data.weekEnd);

    if (start == null || end == null) {
      return 'This week';
    }

    return '${DateFormat('d MMM').format(start)}'
        ' ? '
        '${DateFormat('d MMM yyyy').format(end)}';
  }
}

class _SummaryCard extends StatelessWidget {
  final IconData icon;
  final String value;
  final String label;
  final Color color;

  const _SummaryCard({
    required this.icon,
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 12, vertical: 15),

      decoration: BoxDecoration(
        color: AppColors.of(context).surface,

        borderRadius: BorderRadius.circular(15),

        border: Border.all(color: AppColors.of(context).border),
      ),

      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,

        children: [
          Icon(icon, size: 19, color: color),

          SizedBox(height: 12),

          Text(
            value,

            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
          ),

          SizedBox(height: 2),

          Text(
            label,

            style: TextStyle(
              color: AppColors.of(context).textSecondary,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String title;

  const _SectionTitle({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title,

      style: TextStyle(
        color: AppColors.of(context).textPrimary,

        fontSize: 14,

        fontWeight: FontWeight.w600,
      ),
    );
  }
}

class _DailyChart extends StatelessWidget {
  final List<DashboardDay> days;

  const _DailyChart({required this.days});

  @override
  Widget build(BuildContext context) {
    final highest = days.fold<int>(
      0,
      (current, day) => day.completed > current ? day.completed : current,
    );

    return Container(
      height: 190,

      padding: EdgeInsets.fromLTRB(14, 18, 14, 14),

      decoration: BoxDecoration(
        color: AppColors.of(context).surface,

        borderRadius: BorderRadius.circular(16),

        border: Border.all(color: AppColors.of(context).border),
      ),

      child: days.isEmpty
          ? Center(
              child: Text(
                'No weekly data yet.',
                style: TextStyle(color: AppColors.of(context).textSecondary),
              ),
            )
          : Row(
              crossAxisAlignment: CrossAxisAlignment.end,

              children: days.map((day) {
                final height = highest == 0
                    ? 5.0
                    : 95 * (day.completed / highest);

                return Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.end,

                    children: [
                      Text(
                        '${day.completed}',

                        style: TextStyle(
                          color: AppColors.of(context).textSecondary,
                          fontSize: 10,
                        ),
                      ),

                      SizedBox(height: 7),

                      Container(
                        width: 18,

                        height: height,

                        decoration: BoxDecoration(
                          color: day.completed > 0
                              ? AppColors.of(context).white
                              : AppColors.of(context).border,

                          borderRadius: BorderRadius.circular(6),
                        ),
                      ),

                      SizedBox(height: 9),

                      Text(
                        day.day,

                        style: TextStyle(
                          color: AppColors.of(context).textSecondary,
                          fontSize: 10,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
    );
  }
}

class _PriorityMatrix extends StatelessWidget {
  final DashboardData data;

  const _PriorityMatrix({required this.data});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _PriorityCard(
                title: 'Important + Urgent',
                value: data.importantUrgent,
                color: AppColors.red,
              ),
            ),

            SizedBox(width: 10),

            Expanded(
              child: _PriorityCard(
                title: 'Important',
                value: data.importantNotUrgent,
                color: AppColors.orange,
              ),
            ),
          ],
        ),

        SizedBox(height: 10),

        Row(
          children: [
            Expanded(
              child: _PriorityCard(
                title: 'Urgent',
                value: data.notImportantUrgent,
                color: AppColors.blue,
              ),
            ),

            SizedBox(width: 10),

            Expanded(
              child: _PriorityCard(
                title: 'Low',
                value: data.notImportantNotUrgent,
                color: AppColors.green,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _PriorityCard extends StatelessWidget {
  final String title;
  final int value;
  final Color color;

  const _PriorityCard({
    required this.title,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 90,

      padding: EdgeInsets.all(13),

      decoration: BoxDecoration(
        color: AppColors.of(context).surface,

        borderRadius: BorderRadius.circular(14),

        border: Border.all(color: AppColors.of(context).border),
      ),

      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,

        children: [
          Container(
            width: 8,
            height: 8,

            decoration: BoxDecoration(shape: BoxShape.circle, color: color),
          ),

          Spacer(),

          Row(
            children: [
              Expanded(
                child: Text(
                  title,

                  maxLines: 2,

                  style: TextStyle(
                    color: AppColors.of(context).textSecondary,
                    fontSize: 10,
                  ),
                ),
              ),

              SizedBox(width: 6),

              Text(
                '$value',

                style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InsightCard extends StatelessWidget {
  final DashboardInsight? insight;

  const _InsightCard({required this.insight});

  @override
  Widget build(BuildContext context) {
    if (insight == null) {
      return Container(
        width: double.infinity,

        padding: EdgeInsets.all(17),

        decoration: BoxDecoration(
          color: AppColors.of(context).surface,

          borderRadius: BorderRadius.circular(16),

          border: Border.all(color: AppColors.of(context).border),
        ),

        child: Row(
          children: [
            Icon(
              Icons.auto_awesome_outlined,
              color: AppColors.of(context).textMuted,
            ),

            SizedBox(width: 12),

            Expanded(
              child: Text(
                'No missed-task pattern yet.',

                style: TextStyle(color: AppColors.of(context).textSecondary),
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,

      padding: EdgeInsets.all(17),

      decoration: BoxDecoration(
        color: AppColors.of(context).surface,

        borderRadius: BorderRadius.circular(16),

        border: Border.all(color: AppColors.of(context).border),
      ),

      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,

        children: [
          Icon(Icons.auto_awesome_outlined, color: AppColors.orange, size: 21),

          SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,

              children: [
                Text(
                  insight!.message,

                  style: TextStyle(
                    color: AppColors.of(context).textPrimary,
                    fontSize: 13,
                    height: 1.4,
                    fontWeight: FontWeight.w600,
                  ),
                ),

                SizedBox(height: 6),

                Text(
                  '${insight!.missedCount} missed occurrence'
                  '${insight!.missedCount == 1 ? '' : 's'}',

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
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 80),

      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 60),

      child: Center(
        child: Column(
          children: [
            Icon(
              Icons.error_outline,

              size: 38,

              color: AppColors.of(context).textMuted,
            ),

            SizedBox(height: 12),

            Text(
              'Could not load Dashboard',

              style: TextStyle(fontWeight: FontWeight.w600),
            ),

            SizedBox(height: 7),

            Text(
              message,

              textAlign: TextAlign.center,

              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                fontSize: 11,
              ),
            ),

            SizedBox(height: 12),

            TextButton(onPressed: onRetry, child: Text('Try again')),
          ],
        ),
      ),
    );
  }
}
