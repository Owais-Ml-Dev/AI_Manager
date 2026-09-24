import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../assistant/presentation/assistant_screen.dart';
import '../../dashboard/presentation/dashboard_screen.dart';
import '../../history/presentation/history_screen.dart';
import '../../home/application/home_providers.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../../history/application/history_providers.dart';
import '../../home/presentation/home_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  final List<Widget> _screens = [
    HomeScreen(),
    AssistantScreen(),
    DashboardScreen(),
    HistoryScreen(),
  ];

  void _selectTab(int index) {
    setState(() {
      _selectedIndex = index;
    });

    // Always refresh data when the user opens
    // a data-driven section.
    //
    // This also picks up changes made by:
    // - notifications
    // - Assistant task commands
    // - task completion
    // - another screen
    switch (index) {
      case 0:
        ref.invalidate(homeDataProvider);
        break;

      case 2:
        ref.invalidate(dashboardDataProvider);
        break;

      case 3:
        ref.invalidate(historyDataProvider);
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _selectedIndex, children: _screens),

      bottomNavigationBar: _BottomNavigation(
        selectedIndex: _selectedIndex,
        onChanged: _selectTab,
      ),
    );
  }
}

class _BottomNavigation extends StatelessWidget {
  final int selectedIndex;

  final ValueChanged<int> onChanged;

  const _BottomNavigation({
    required this.selectedIndex,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final items = [
      (Icons.home_outlined, Icons.home, 'Home'),
      (Icons.auto_awesome_outlined, Icons.auto_awesome, 'Assistant'),
      (Icons.grid_view_outlined, Icons.grid_view, 'Dashboard'),
      (Icons.event_note_outlined, Icons.event_note, 'History'),
    ];

    return SafeArea(
      top: false,
      child: Container(
        height: 68,
        decoration: BoxDecoration(
          color: AppColors.of(context).background,

          border: Border(top: BorderSide(color: AppColors.of(context).border)),
        ),
        child: Row(
          children: List.generate(items.length, (index) {
            final item = items[index];

            final selected = selectedIndex == index;

            return Expanded(
              child: InkWell(
                onTap: () {
                  onChanged(index);
                },
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      selected ? item.$2 : item.$1,
                      size: 21,
                      color: selected
                          ? AppColors.of(context).white
                          : AppColors.of(context).textMuted,
                    ),
                    SizedBox(height: 4),
                    Text(
                      item.$3,
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: selected
                            ? FontWeight.w600
                            : FontWeight.w400,
                        color: selected
                            ? AppColors.of(context).white
                            : AppColors.of(context).textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
