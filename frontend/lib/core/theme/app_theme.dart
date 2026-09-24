import 'package:flutter/material.dart';

import 'app_colors.dart';

abstract final class AppTheme {
  static ThemeData get dark {
    return _build(AppColors.dark, Brightness.dark);
  }

  static ThemeData get light {
    return _build(AppColors.light, Brightness.light);
  }

  static ThemeData _build(AppPalette palette, Brightness brightness) {
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: brightness == Brightness.dark
              ? const Color(0xFFF4F4F4)
              : const Color(0xFF242424),
          brightness: brightness,
        ).copyWith(
          primary: palette.white,
          onPrimary: palette.onAccent,
          surface: palette.surface,
          onSurface: palette.textPrimary,
          outline: palette.border,
        );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,

      extensions: <ThemeExtension<dynamic>>[palette],

      scaffoldBackgroundColor: palette.background,

      canvasColor: palette.background,

      dividerColor: palette.border,

      splashColor: Colors.transparent,

      highlightColor: Colors.transparent,

      appBarTheme: AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: palette.background,
        foregroundColor: palette.textPrimary,
        surfaceTintColor: Colors.transparent,
      ),

      textTheme: TextTheme(
        headlineLarge: TextStyle(
          color: palette.textPrimary,
          fontSize: 30,
          fontWeight: FontWeight.w700,
          height: 1.05,
        ),
        headlineMedium: TextStyle(
          color: palette.textPrimary,
          fontSize: 24,
          fontWeight: FontWeight.w700,
        ),
        titleLarge: TextStyle(
          color: palette.textPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        titleMedium: TextStyle(
          color: palette.textPrimary,
          fontSize: 15,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: TextStyle(color: palette.textPrimary, fontSize: 15),
        bodyMedium: TextStyle(color: palette.textSecondary, fontSize: 13),
        bodySmall: TextStyle(color: palette.textMuted, fontSize: 12),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: palette.surface,

        hintStyle: TextStyle(color: palette.textMuted),

        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),

        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: palette.border),
        ),

        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: palette.textSecondary),
        ),
      ),

      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: palette.surfaceElevated,
        modalBackgroundColor: palette.surfaceElevated,
        surfaceTintColor: Colors.transparent,
      ),

      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: palette.white,
        foregroundColor: palette.onAccent,
      ),

      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: palette.white,
        linearTrackColor: palette.border,
      ),

      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return palette.onAccent;
          }

          return palette.textMuted;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return palette.white;
          }

          return palette.surfaceElevated;
        }),
      ),
    );
  }
}
