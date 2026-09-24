import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(
  ThemeModeController.new,
);

class ThemeModeController extends Notifier<ThemeMode> {
  static const _storageKey = 'app_theme_mode';

  @override
  ThemeMode build() {
    // Preserve the app's existing appearance
    // until a saved preference is loaded.
    Future.microtask(_restore);

    return ThemeMode.dark;
  }

  Future<void> _restore() async {
    try {
      final preferences = await SharedPreferences.getInstance();

      final saved = preferences.getString(_storageKey);

      if (saved == 'light') {
        state = ThemeMode.light;
      } else if (saved == 'dark') {
        state = ThemeMode.dark;
      }
    } catch (_) {
      // Theme persistence must never
      // prevent the app from starting.
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    if (mode != ThemeMode.light && mode != ThemeMode.dark) {
      return;
    }

    state = mode;

    try {
      final preferences = await SharedPreferences.getInstance();

      await preferences.setString(
        _storageKey,
        mode == ThemeMode.dark ? 'dark' : 'light',
      );
    } catch (_) {
      // The visual theme still changes even
      // if persistence fails.
    }
  }

  Future<void> toggle() async {
    await setMode(state == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark);
  }
}
