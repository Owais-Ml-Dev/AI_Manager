import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/theme_mode_provider.dart';
import '../application/home_providers.dart';
import '../domain/home_task_item.dart';
import '../../tasks/application/task_providers.dart';
import '../../tasks/presentation/new_task_screen.dart';
import '../../tasks/presentation/edit_task_screen.dart';
import '../../tasks/presentation/recurring_task_detail_screen.dart';
import '../../profile/presentation/profile_screen.dart';
import '../../settings/presentation/settings_screen.dart';
import '../../notifications/presentation/notifications_screen.dart';

enum HomeTab { recurring, repeatUntilDone }

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() {
    return _HomeScreenState();
  }
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  HomeTab _selectedTab = HomeTab.recurring;

  Future<void> _refresh() async {
    ref.invalidate(homeDataProvider);

    await ref.read(homeDataProvider.future);
  }

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(homeDataProvider);

    return SafeArea(
      bottom: false,
      child: Stack(
        children: [
          RefreshIndicator(
            onRefresh: _refresh,
            child: SingleChildScrollView(
              physics: AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.fromLTRB(20, 18, 20, 110),
              child: home.when(
                loading: () =>
                    _buildContent(context, data: null, loading: true),
                error: (error, stackTrace) =>
                    _buildContent(context, data: null, error: error.toString()),
                data: (data) => _buildContent(context, data: data),
              ),
            ),
          ),

          Positioned(
            left: 20,
            right: 20,
            bottom: 20,
            child: _AddTaskBar(
              onTap: () async {
                final created = await Navigator.push<bool>(
                  context,
                  MaterialPageRoute(
                    builder: (context) {
                      return const NewTaskScreen();
                    },
                  ),
                );

                if (created == true) {
                  ref.invalidate(homeDataProvider);
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _completeTask(HomeTaskItem task) async {
    try {
      final repository = ref.read(taskRepositoryProvider);

      if (task.kind == HomeTaskKind.recurring) {
        final occurrenceId = task.occurrenceId;

        if (occurrenceId == null || occurrenceId.isEmpty) {
          throw ApiException(message: 'Today occurrence could not be found.');
        }

        await repository.completeRecurringOccurrence(occurrenceId);
      } else {
        await repository.completeRepeatUntilDoneTask(task.taskId);
      }

      ref.invalidate(homeDataProvider);

      await ref.read(homeDataProvider.future);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            task.kind == HomeTaskKind.recurring
                ? 'Completed for today.'
                : 'Task completed permanently.',
          ),
        ),
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

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not complete the task.')));
    }
  }

  Future<void> _completeRecurringPermanently(HomeTaskItem task) async {
    try {
      final repository = ref.read(taskRepositoryProvider);

      await repository.completeRecurringTask(task.taskId);

      ref.invalidate(homeDataProvider);

      await ref.read(homeDataProvider.future);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Recurring task completed permanently.')),
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
        const SnackBar(content: Text('Could not complete the recurring task.')),
      );
    }
  }

  Widget _buildContent(
    BuildContext context, {
    required HomeData? data,
    bool loading = false,
    String? error,
  }) {
    final now = DateTime.now();

    final formattedDate = DateFormat('EEEE, d MMMM').format(now);

    final tasks = _selectedTab == HomeTab.recurring
        ? data?.recurringTasks ?? []
        : data?.repeatUntilDoneTasks ?? [];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _TopBar(),

        SizedBox(height: 26),

        Text('Today', style: Theme.of(context).textTheme.headlineMedium),

        SizedBox(height: 3),

        Text(formattedDate, style: Theme.of(context).textTheme.bodyMedium),

        SizedBox(height: 28),

        _ProgressSection(
          completed: data?.completedCount ?? 0,
          total: data?.totalCount ?? 0,
          loading: loading,
        ),

        SizedBox(height: 23),

        _TaskTabs(
          selected: _selectedTab,
          onChanged: (tab) {
            setState(() {
              _selectedTab = tab;
            });
          },
        ),

        SizedBox(height: 8),

        Divider(),

        if (loading)
          _LoadingState()
        else if (error != null)
          _ErrorState(
            message: error,
            onRetry: () {
              ref.invalidate(homeDataProvider);
            },
          )
        else if (tasks.isEmpty)
          _EmptyState(type: _selectedTab)
        else
          ...tasks.map(
            (task) => _TaskRow(
              task: task,
              onTap: task.kind == HomeTaskKind.recurring
                  ? () async {
                      await Navigator.push<bool>(
                        context,
                        MaterialPageRoute(
                          builder: (context) {
                            return RecurringTaskDetailScreen(
                              taskId: task.taskId,
                            );
                          },
                        ),
                      );

                      if (mounted) {
                        ref.invalidate(homeDataProvider);
                      }
                    }
                  : null,
              onMore: task.status == HomeTaskStatus.pending
                  ? () {
                      _showTaskActions(
                        context,
                        task,
                        onEdit: () async {
                          final updated = await Navigator.push<bool>(
                            context,
                            MaterialPageRoute(
                              builder: (context) {
                                return EditTaskScreen(
                                  taskId: task.taskId,
                                  recurring:
                                      task.kind == HomeTaskKind.recurring,
                                );
                              },
                            ),
                          );

                          if (updated == true) {
                            ref.invalidate(homeDataProvider);
                          }
                        },
                        onComplete: () {
                          return _completeTask(task);
                        },
                        onCompletePermanently:
                            task.kind == HomeTaskKind.recurring
                            ? () {
                                return _completeRecurringPermanently(task);
                              }
                            : null,
                      );
                    }
                  : null,
            ),
          ),
      ],
    );
  }
}

class _AddTaskBar extends StatelessWidget {
  final VoidCallback onTap;

  const _AddTaskBar({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(28),
        child: Container(
          height: 56,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: colors.surfaceElevated,
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: colors.border, width: 1),
          ),
          child: Row(
            children: [
              Icon(Icons.add, size: 22, color: colors.textSecondary),

              const SizedBox(width: 12),

              Expanded(
                child: Text(
                  'Add a task',
                  style: TextStyle(
                    color: colors.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),

              Icon(Icons.arrow_upward, size: 20, color: colors.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}

class _TopBar extends ConsumerWidget {
  const _TopBar();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Row(
      children: [
        _CircleIconButton(
          icon: Icons.person_outline,
          onTap: () {
            debugPrint('Opening Profile screen...');

            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) {
                  return const ProfileScreen();
                },
              ),
            );
          },
        ),
        Spacer(),
        Stack(
          clipBehavior: Clip.none,
          children: [
            _CircleIconButton(
              icon: Icons.notifications_none,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) {
                      return const NotificationsScreen();
                    },
                  ),
                );
              },
              transparent: true,
            ),
            Positioned(
              right: 7,
              top: 4,
              child: CircleAvatar(radius: 3, backgroundColor: AppColors.red),
            ),
          ],
        ),
        _CircleIconButton(
          icon: Theme.of(context).brightness == Brightness.dark
              ? Icons.light_mode_outlined
              : Icons.dark_mode_outlined,
          onTap: () {
            ref.read(themeModeProvider.notifier).toggle();
          },
          transparent: true,
        ),
        _CircleIconButton(
          icon: Icons.settings_outlined,
          onTap: () {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) {
                  return SettingsScreen();
                },
              ),
            );
          },
          transparent: true,
        ),
      ],
    );
  }
}

class _CircleIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final bool transparent;

  const _CircleIconButton({
    required this.icon,
    required this.onTap,
    this.transparent = false,
  });

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onTap,
      icon: Icon(icon, size: 21),
      color: AppColors.of(context).textSecondary,
      style: IconButton.styleFrom(
        backgroundColor: transparent
            ? Colors.transparent
            : AppColors.of(context).surfaceElevated,
      ),
    );
  }
}

class _ProgressSection extends StatelessWidget {
  final int completed;
  final int total;
  final bool loading;

  const _ProgressSection({
    required this.completed,
    required this.total,
    required this.loading,
  });

  @override
  Widget build(BuildContext context) {
    final progress = total == 0 ? 0.0 : completed / total;

    final percent = (progress * 100).round();

    return Column(
      children: [
        Row(
          children: [
            Text(
              loading ? 'Loading today...' : '$completed of $total done',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: AppColors.of(context).textPrimary,
              ),
            ),
            Spacer(),
            if (!loading)
              Text(
                '$percent%',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: AppColors.of(context).textPrimary,
                ),
              ),
          ],
        ),
        SizedBox(height: 9),
        ClipRRect(
          borderRadius: BorderRadius.circular(100),
          child: LinearProgressIndicator(
            value: loading ? null : progress,
            minHeight: 4,
            backgroundColor: AppColors.of(context).border,
            valueColor: AlwaysStoppedAnimation(AppColors.of(context).white),
          ),
        ),
      ],
    );
  }
}

class _TaskTabs extends StatelessWidget {
  final HomeTab selected;
  final ValueChanged<HomeTab> onChanged;

  const _TaskTabs({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _TaskTabButton(
            label: 'Recurring',
            selected: selected == HomeTab.recurring,
            onTap: () {
              onChanged(HomeTab.recurring);
            },
          ),
        ),
        SizedBox(width: 16),
        Expanded(
          child: _TaskTabButton(
            label: 'Repeat Until Done',
            selected: selected == HomeTab.repeatUntilDone,
            onTap: () {
              onChanged(HomeTab.repeatUntilDone);
            },
          ),
        ),
      ],
    );
  }
}

class _TaskTabButton extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _TaskTabButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(vertical: 8),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: selected
                  ? AppColors.of(context).white
                  : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Text(
          label,
          maxLines: 1,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: selected
                ? AppColors.of(context).textPrimary
                : AppColors.of(context).textSecondary,
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}

class _TaskRow extends StatelessWidget {
  final HomeTaskItem task;
  final VoidCallback? onTap;
  final VoidCallback? onMore;

  const _TaskRow({required this.task, this.onTap, this.onMore});

  Color get _priorityColor {
    switch (task.priority) {
      case 'important_urgent':
        return AppColors.red;

      case 'important_not_urgent':
        return AppColors.orange;

      case 'not_important_urgent':
        return AppColors.blue;

      default:
        return AppColors.green;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 15),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: AppColors.of(context).border),
            ),
          ),
          child: Row(
            children: [
              _StatusCircle(status: task.status),

              const SizedBox(width: 12),

              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _priorityColor,
                ),
              ),

              const SizedBox(width: 12),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      task.title,
                      style: TextStyle(
                        color: task.isCompleted
                            ? AppColors.of(context).textSecondary
                            : AppColors.of(context).textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        decoration: task.isCompleted
                            ? TextDecoration.lineThrough
                            : null,
                      ),
                    ),

                    const SizedBox(height: 3),

                    Text(
                      task.subtitle,
                      style: TextStyle(
                        color: task.isMissed
                            ? AppColors.red
                            : AppColors.of(context).textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),

              if (task.kind == HomeTaskKind.recurring)
                Icon(
                  Icons.chevron_right,
                  size: 18,
                  color: AppColors.of(context).textMuted,
                ),

              if (onMore != null)
                IconButton(
                  onPressed: onMore,
                  icon: const Icon(Icons.more_vert, size: 18),
                  color: AppColors.of(context).textMuted,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusCircle extends StatelessWidget {
  final HomeTaskStatus status;

  const _StatusCircle({required this.status});

  @override
  Widget build(BuildContext context) {
    if (status == HomeTaskStatus.completed) {
      return Container(
        width: 20,
        height: 20,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppColors.of(context).white,
        ),
        child: Icon(
          Icons.check,
          size: 13,
          color: AppColors.of(context).onAccent,
        ),
      );
    }

    if (status == HomeTaskStatus.missed) {
      return Container(
        width: 20,
        height: 20,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.red),
        ),
        child: Icon(Icons.close, size: 12, color: AppColors.red),
      );
    }

    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.of(context).textMuted),
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 50),
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final HomeTab type;

  const _EmptyState({required this.type});

  @override
  Widget build(BuildContext context) {
    final message = type == HomeTab.recurring
        ? 'No recurring tasks for today.'
        : 'No Repeat Until Done tasks for today.';

    return Padding(
      padding: EdgeInsets.symmetric(vertical: 60),
      child: Center(
        child: Column(
          children: [
            Icon(
              Icons.check_circle_outline,
              color: AppColors.of(context).textMuted,
              size: 36,
            ),
            SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.of(context).textSecondary),
            ),
          ],
        ),
      ),
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
      padding: EdgeInsets.symmetric(vertical: 40),
      child: Center(
        child: Column(
          children: [
            Icon(
              Icons.wifi_off_outlined,
              color: AppColors.of(context).textMuted,
              size: 36,
            ),
            SizedBox(height: 12),
            Text(
              'Could not load tasks',
              style: TextStyle(
                color: AppColors.of(context).textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.of(context).textSecondary,
                fontSize: 12,
              ),
            ),
            SizedBox(height: 14),
            TextButton(onPressed: onRetry, child: Text('Try again')),
          ],
        ),
      ),
    );
  }
}

void _showTaskActions(
  BuildContext context,
  HomeTaskItem task, {
  required Future<void> Function() onEdit,
  required Future<void> Function() onComplete,
  Future<void> Function()? onCompletePermanently,
}) {
  final recurring = task.kind == HomeTaskKind.recurring;

  showModalBottomSheet(
    context: context,
    useSafeArea: true,
    showDragHandle: true,
    builder: (sheetContext) {
      return Padding(
        padding: EdgeInsets.fromLTRB(20, 2, 20, 30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(task.title, style: Theme.of(context).textTheme.titleLarge),
            SizedBox(height: 4),
            Text(
              recurring ? 'Recurring task' : 'Repeat Until Done',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            SizedBox(height: 18),
            _ActionRow(
              icon: Icons.edit_outlined,
              title: 'Edit task',
              description: 'Change task details.',
              onTap: () {
                Navigator.pop(sheetContext);

                onEdit();
              },
            ),
            _ActionRow(
              icon: recurring ? Icons.check : Icons.flag_outlined,
              title: recurring ? 'Complete for today' : 'Complete permanently',
              description: recurring
                  ? 'Only today will be completed.'
                  : 'Stops reminders and moves it to History.',
              onTap: () {
                Navigator.pop(sheetContext);

                onComplete();
              },
            ),

            if (recurring && onCompletePermanently != null)
              _ActionRow(
                icon: Icons.flag_outlined,
                title: 'Complete permanently',
                description: 'Ends this recurring task, stops future reminders, and moves it to History.',
                onTap: () {
                  Navigator.pop(sheetContext);

                  onCompletePermanently();
                },
              ),
          ],
        ),
      );
    },
  );
}

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final VoidCallback onTap;

  const _ActionRow({
    required this.icon,
    required this.title,
    required this.description,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: 13),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: AppColors.of(context).surfaceElevated,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: AppColors.of(context).white, size: 20),
            ),
            SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: AppColors.of(context).textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: 3),
                  Text(
                    description,
                    style: TextStyle(
                      color: AppColors.of(context).textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
