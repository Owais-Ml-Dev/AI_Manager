import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'core/theme/theme_mode_provider.dart';
import 'features/navigation/presentation/app_shell.dart';

class AiTaskManagerApp extends ConsumerWidget {
  const AiTaskManagerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);

    return MaterialApp(
      title: 'AI Task Manager',
      debugShowCheckedModeBanner: false,

      theme: AppTheme.light,

      darkTheme: AppTheme.dark,

      themeMode: themeMode,

      home: const AppShell(),
    );
  }
}
