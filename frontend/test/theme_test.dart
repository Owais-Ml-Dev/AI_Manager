import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_task_manager/core/theme/app_colors.dart';
import 'package:ai_task_manager/core/theme/app_theme.dart';

void main() {
  test('dark and light themes are configured', () {
    expect(AppTheme.dark.brightness, Brightness.dark);

    expect(AppTheme.light.brightness, Brightness.light);

    final darkPalette = AppTheme.dark.extension<AppPalette>();

    final lightPalette = AppTheme.light.extension<AppPalette>();

    expect(darkPalette, isNotNull);

    expect(lightPalette, isNotNull);

    expect(darkPalette!.background, isNot(lightPalette!.background));

    expect(darkPalette.textPrimary, isNot(lightPalette.textPrimary));
  });
}
