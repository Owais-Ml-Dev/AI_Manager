import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../application/history_providers.dart';
import '../domain/history_item.dart';
import 'history_details_screen.dart';

enum HistoryTab { recurring, repeatUntilDone }

class HistoryScreen extends ConsumerStatefulWidget {
  const HistoryScreen({super.key});

  @override
  ConsumerState<HistoryScreen> createState() {
    return _HistoryScreenState();
  }
}

class _HistoryScreenState extends ConsumerState<HistoryScreen> {
  HistoryTab _selectedTab = HistoryTab.recurring;

  final Set<String> _selectedIds = <String>{};

  bool _selectionMode = false;
  bool _deleting = false;

  Future<void> _refresh() async {
    ref.invalidate(historyDataProvider);

    await ref.read(historyDataProvider.future);
  }

  void _enterSelection(HistoryItem item) {
    setState(() {
      _selectionMode = true;

      _selectedIds.add(item.taskId);
    });
  }

  void _toggleSelection(HistoryItem item) {
    setState(() {
      if (_selectedIds.contains(item.taskId)) {
        _selectedIds.remove(item.taskId);
      } else {
        _selectedIds.add(item.taskId);
      }

      if (_selectedIds.isEmpty) {
        _selectionMode = false;
      }
    });
  }

  void _cancelSelection() {
    setState(() {
      _selectionMode = false;
      _selectedIds.clear();
    });
  }

  void _selectAll(List<HistoryItem> items) {
    setState(() {
      _selectionMode = true;

      _selectedIds
        ..clear()
        ..addAll(items.map((item) => item.taskId));
    });
  }

  Future<void> _deleteSelected(List<HistoryItem> items) async {
    if (_selectedIds.isEmpty || _deleting) {
      return;
    }

    final selectedItems = items
        .where((item) => _selectedIds.contains(item.taskId))
        .toList();

    if (selectedItems.isEmpty) {
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final colors = AppColors.of(dialogContext);

        return AlertDialog(
          backgroundColor: colors.surface,
          title: Text(
            selectedItems.length == 1
                ? 'Delete task?'
                : 'Delete ${selectedItems.length} tasks?',
          ),
          content: Text(
            'This permanently removes the selected '
            'task${selectedItems.length == 1 ? '' : 's'} '
            'from History. This cannot be undone.',
            style: TextStyle(color: colors.textSecondary),
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
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.red,
                foregroundColor: Colors.white,
              ),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );

    if (confirmed != true || !mounted) {
      return;
    }

    setState(() {
      _deleting = true;
    });

    try {
      await ref
          .read(historyRepositoryProvider)
          .deleteHistoryItems(selectedItems);

      if (!mounted) {
        return;
      }

      _cancelSelection();

      ref.invalidate(historyDataProvider);

      // Historical deletion can change
      // dashboard statistics too.
      ref.invalidate(dashboardDataProvider);

      await ref.read(historyDataProvider.future);

      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            selectedItems.length == 1
                ? 'Task deleted.'
                : '${selectedItems.length} tasks deleted.',
          ),
        ),
      );
    } catch (_) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not delete the selected tasks.')),
      );

      // Some requests may already have succeeded,
      // so refresh to show the true server state.
      ref.invalidate(historyDataProvider);
    } finally {
      if (mounted) {
        setState(() {
          _deleting = false;
        });
      }
    }
  }

  void _changeTab(HistoryTab tab) {
    setState(() {
      _selectedTab = tab;

      // Selection never leaks between tabs.
      _selectionMode = false;
      _selectedIds.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final history = ref.watch(historyDataProvider);

    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _refresh,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 110),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              history.when(
                loading: () => _buildHeader(const <HistoryItem>[]),
                error: (_, _) => _buildHeader(const <HistoryItem>[]),
                data: (data) {
                  final items = _selectedTab == HistoryTab.recurring
                      ? data.recurring
                      : data.repeatUntilDone;

                  return _buildHeader(items);
                },
              ),

              const SizedBox(height: 5),

              Text(
                _selectionMode
                    ? '${_selectedIds.length} selected'
                    : 'Your completed and ended tasks',
                style: TextStyle(
                  color: AppColors.of(context).textSecondary,
                  fontSize: 13,
                ),
              ),

              const SizedBox(height: 28),

              _HistoryTabs(selected: _selectedTab, onChanged: _changeTab),

              Divider(color: AppColors.of(context).border),

              history.when(
                loading: () => const _LoadingState(),

                error: (error, stackTrace) => _ErrorState(
                  message: error.toString(),
                  onRetry: () {
                    ref.invalidate(historyDataProvider);
                  },
                ),

                data: (data) {
                  final items = _selectedTab == HistoryTab.recurring
                      ? data.recurring
                      : data.repeatUntilDone;

                  if (_selectionMode && items.isNotEmpty) {
                    return Column(
                      children: [
                        _SelectionBar(
                          selected: _selectedIds.length,
                          total: items.length,
                          deleting: _deleting,
                          onSelectAll: () {
                            _selectAll(items);
                          },
                          onDelete: () {
                            _deleteSelected(items);
                          },
                        ),

                        _buildItems(items),
                      ],
                    );
                  }

                  if (items.isEmpty) {
                    return _EmptyState(tab: _selectedTab);
                  }

                  return _buildItems(items);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(List<HistoryItem> items) {
    return Row(
      children: [
        Expanded(
          child: Text(
            'History',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
        ),

        if (items.isNotEmpty)
          TextButton(
            onPressed: _deleting
                ? null
                : () {
                    if (_selectionMode) {
                      _cancelSelection();
                    } else {
                      setState(() {
                        _selectionMode = true;
                      });
                    }
                  },
            child: Text(_selectionMode ? 'Cancel' : 'Select'),
          ),
      ],
    );
  }

  Widget _buildItems(List<HistoryItem> items) {
    return Column(
      children: items.map((item) {
        return _HistoryCard(
          item: item,
          selectionMode: _selectionMode,
          selected: _selectedIds.contains(item.taskId),
          onTap: () {
            if (_selectionMode) {
              _toggleSelection(item);

              return;
            }

            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) {
                  return HistoryDetailsScreen(item: item);
                },
              ),
            );
          },
          onLongPress: () {
            if (!_selectionMode) {
              _enterSelection(item);
            }
          },
        );
      }).toList(),
    );
  }
}

class _SelectionBar extends StatelessWidget {
  final int selected;
  final int total;
  final bool deleting;

  final VoidCallback onSelectAll;
  final VoidCallback onDelete;

  const _SelectionBar({
    required this.selected,
    required this.total,
    required this.deleting,
    required this.onSelectAll,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.fromLTRB(14, 9, 8, 9),
      decoration: BoxDecoration(
        color: colors.surfaceElevated,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '$selected of $total selected',
              style: TextStyle(color: colors.textSecondary, fontSize: 12),
            ),
          ),

          TextButton(
            onPressed: deleting ? null : onSelectAll,
            child: const Text('Select all'),
          ),

          const SizedBox(width: 2),

          IconButton(
            tooltip: 'Delete selected',
            onPressed: selected == 0 || deleting ? null : onDelete,
            icon: deleting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.delete_outline),
          ),
        ],
      ),
    );
  }
}

class _HistoryTabs extends StatelessWidget {
  final HistoryTab selected;

  final ValueChanged<HistoryTab> onChanged;

  const _HistoryTabs({required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _TabButton(
            label: 'Recurring',
            selected: selected == HistoryTab.recurring,
            onTap: () {
              onChanged(HistoryTab.recurring);
            },
          ),
        ),

        const SizedBox(width: 12),

        Expanded(
          child: _TabButton(
            label: 'Repeat Until Done',
            selected: selected == HistoryTab.repeatUntilDone,
            onTap: () {
              onChanged(HistoryTab.repeatUntilDone);
            },
          ),
        ),
      ],
    );
  }
}

class _TabButton extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _TabButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: selected ? colors.textPrimary : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Text(
          label,
          textAlign: TextAlign.center,
          maxLines: 1,
          style: TextStyle(
            color: selected ? colors.textPrimary : colors.textSecondary,
            fontSize: 12,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  final HistoryItem item;

  final bool selectionMode;
  final bool selected;

  final VoidCallback onTap;
  final VoidCallback onLongPress;

  const _HistoryCard({
    required this.item,
    required this.selectionMode,
    required this.selected,
    required this.onTap,
    required this.onLongPress,
  });

  Color get _priorityColor {
    switch (item.priority) {
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
    final colors = AppColors.of(context);

    final recurring = item.kind == HistoryTaskKind.recurring;

    return InkWell(
      onTap: onTap,
      onLongPress: onLongPress,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        margin: const EdgeInsets.only(top: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: selected ? colors.surfaceElevated : colors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? colors.textSecondary : colors.border,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 9,
                  height: 9,
                  margin: const EdgeInsets.only(top: 6),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _priorityColor,
                  ),
                ),

                const SizedBox(width: 11),

                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        style: TextStyle(
                          color: colors.textPrimary,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),

                      if (item.description != null &&
                          item.description!.trim().isNotEmpty) ...[
                        const SizedBox(height: 4),

                        Text(
                          item.description!,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: colors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),

                const SizedBox(width: 10),

                if (selectionMode)
                  Icon(
                    selected
                        ? Icons.check_circle
                        : Icons.radio_button_unchecked,
                    color: selected ? colors.textPrimary : colors.textMuted,
                    size: 21,
                  )
                else
                  Icon(Icons.chevron_right, color: colors.textMuted, size: 20),
              ],
            ),

            const SizedBox(height: 15),

            if (recurring)
              _RecurringSummary(item: item)
            else
              _RepeatSummary(item: item),
          ],
        ),
      ),
    );
  }
}

class _RecurringSummary extends StatelessWidget {
  final HistoryItem item;

  const _RecurringSummary({required this.item});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                _dateRange(),
                style: TextStyle(color: colors.textSecondary, fontSize: 11),
              ),
            ),

            Text(
              '${item.completionRate}%',
              style: TextStyle(
                color: colors.textPrimary,
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),

        const SizedBox(height: 9),

        ClipRRect(
          borderRadius: BorderRadius.circular(100),
          child: LinearProgressIndicator(
            value: item.completionRate.clamp(0, 100) / 100,
            minHeight: 4,
            backgroundColor: colors.border,
            valueColor: AlwaysStoppedAnimation(colors.textPrimary),
          ),
        ),

        const SizedBox(height: 10),

        Row(
          children: [
            const Icon(
              Icons.check_circle_outline,
              size: 14,
              color: AppColors.green,
            ),

            const SizedBox(width: 5),

            Text(
              '${item.done} done',
              style: TextStyle(color: colors.textSecondary, fontSize: 11),
            ),

            const SizedBox(width: 16),

            const Icon(Icons.cancel_outlined, size: 14, color: AppColors.red),

            const SizedBox(width: 5),

            Text(
              '${item.missed} missed',
              style: TextStyle(color: colors.textSecondary, fontSize: 11),
            ),
          ],
        ),
      ],
    );
  }

  String _dateRange() {
    final start = _formatDateString(item.startDate);

    final end = _formatDateString(item.endDate);

    if (start.isEmpty && end.isEmpty) {
      return 'Recurring task ended';
    }

    if (end.isEmpty) {
      return start;
    }

    return '$start ? $end';
  }

  String _formatDateString(String? value) {
    if (value == null) {
      return '';
    }

    final date = DateTime.tryParse(value);

    if (date == null) {
      return value;
    }

    return DateFormat('d MMM yyyy').format(date);
  }
}

class _RepeatSummary extends StatelessWidget {
  final HistoryItem item;

  const _RepeatSummary({required this.item});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Row(
      children: [
        Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: colors.surfaceElevated,
            border: Border.all(color: colors.border),
          ),
          child: Icon(Icons.check, size: 15, color: colors.textPrimary),
        ),

        const SizedBox(width: 9),

        Expanded(
          child: Text(
            _completedText(),
            style: TextStyle(color: colors.textSecondary, fontSize: 12),
          ),
        ),
      ],
    );
  }

  String _completedText() {
    if (item.date == null) {
      return 'Completed';
    }

    return 'Completed '
        '${DateFormat('d MMM yyyy ? h:mm a').format(item.date!)}';
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
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
    final colors = AppColors.of(context);

    return Padding(
      padding: const EdgeInsets.only(top: 60),
      child: Center(
        child: Column(
          children: [
            Text(
              'Could not load History.',
              style: TextStyle(color: colors.textPrimary),
            ),

            const SizedBox(height: 8),

            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.textMuted, fontSize: 11),
            ),

            const SizedBox(height: 14),

            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final HistoryTab tab;

  const _EmptyState({required this.tab});

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);

    return Padding(
      padding: const EdgeInsets.only(top: 70),
      child: Center(
        child: Column(
          children: [
            Icon(Icons.history, size: 34, color: colors.textMuted),

            const SizedBox(height: 12),

            Text(
              tab == HistoryTab.recurring
                  ? 'No ended recurring tasks'
                  : 'No completed Repeat Until Done tasks',
              textAlign: TextAlign.center,
              style: TextStyle(color: colors.textSecondary, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }
}
