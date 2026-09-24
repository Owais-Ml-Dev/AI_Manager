import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_task_manager/app.dart';
import 'package:ai_task_manager/features/home/application/home_providers.dart';
import 'package:ai_task_manager/features/home/domain/home_task_item.dart';

void main() {
  testWidgets('AI Task Manager starts successfully', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeDataProvider.overrideWith((ref) async {
            return const HomeData(
              recurringTasks: [],
              repeatUntilDoneTasks: [],
              completedCount: 0,
              totalCount: 0,
            );
          }),
        ],
        child: const AiTaskManagerApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Today'), findsOneWidget);

    expect(find.text('Recurring'), findsOneWidget);

    expect(find.text('Repeat Until Done'), findsOneWidget);

    expect(find.text('Assistant'), findsOneWidget);

    expect(find.text('Dashboard'), findsOneWidget);

    expect(find.text('History'), findsOneWidget);
  });
}
