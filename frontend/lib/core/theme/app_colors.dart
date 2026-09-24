import 'package:flutter/material.dart';

@immutable
class AppPalette extends ThemeExtension<AppPalette> {
  final Color background;
  final Color surface;
  final Color surfaceElevated;
  final Color border;

  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;

  // Strong contrasting control/background.
  //
  // Dark mode: near white.
  // Light mode: near black.
  final Color white;

  // Text/icon placed on the strong contrasting color.
  final Color onAccent;

  const AppPalette({
    required this.background,
    required this.surface,
    required this.surfaceElevated,
    required this.border,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.white,
    required this.onAccent,
  });

  @override
  AppPalette copyWith({
    Color? background,
    Color? surface,
    Color? surfaceElevated,
    Color? border,
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? white,
    Color? onAccent,
  }) {
    return AppPalette(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      surfaceElevated: surfaceElevated ?? this.surfaceElevated,
      border: border ?? this.border,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textMuted: textMuted ?? this.textMuted,
      white: white ?? this.white,
      onAccent: onAccent ?? this.onAccent,
    );
  }

  @override
  AppPalette lerp(covariant AppPalette? other, double t) {
    if (other == null) {
      return this;
    }

    return AppPalette(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceElevated: Color.lerp(surfaceElevated, other.surfaceElevated, t)!,
      border: Color.lerp(border, other.border, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      white: Color.lerp(white, other.white, t)!,
      onAccent: Color.lerp(onAccent, other.onAccent, t)!,
    );
  }
}

abstract final class AppColors {
  // =========================================================
  // DARK
  // =========================================================

  static const dark = AppPalette(
    background: Color(0xFF111111),
    surface: Color(0xFF171717),
    surfaceElevated: Color(0xFF1D1D1D),
    border: Color(0xFF2A2A2A),
    textPrimary: Color(0xFFF4F4F4),
    textSecondary: Color(0xFF969696),
    textMuted: Color(0xFF6E6E6E),
    white: Color(0xFFF6F6F6),
    onAccent: Color(0xFF111111),
  );

  // =========================================================
  // LIGHT
  // =========================================================

  static const light = AppPalette(
    background: Color(0xFFF7F7F5),
    surface: Color(0xFFFFFFFF),
    surfaceElevated: Color(0xFFF0F0ED),
    border: Color(0xFFE0E0DC),
    textPrimary: Color(0xFF181818),
    textSecondary: Color(0xFF62625E),
    textMuted: Color(0xFF8A8A84),
    white: Color(0xFF181818),
    onAccent: Color(0xFFFFFFFF),
  );

  // Priority/status colors remain recognizable
  // in both themes.
  static const green = Color(0xFF80B83A);

  static const orange = Color(0xFFE59B23);

  static const red = Color(0xFFE25A5A);

  static const blue = Color(0xFF4D8FE8);

  static AppPalette of(BuildContext context) {
    final palette = Theme.of(context).extension<AppPalette>();

    if (palette != null) {
      return palette;
    }

    return Theme.of(context).brightness == Brightness.dark ? dark : light;
  }
}
