import 'package:flutter_test/flutter_test.dart';
import 'package:ai_task_manager/features/assistant/data/assistant_batch_session_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const store = AssistantBatchSessionStore();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('active batch id survives a new store instance', () async {
    await store.saveActiveBatchId('batch-123');

    const reopenedStore = AssistantBatchSessionStore();

    expect(
      await reopenedStore.loadActiveBatchId(),
      'batch-123',
    );
  });

  test('clearing active batch removes restart recovery pointer', () async {
    await store.saveActiveBatchId('batch-123');
    await store.clearActiveBatchId();

    expect(await store.loadActiveBatchId(), isNull);
  });

  test('empty batch id is rejected', () async {
    await expectLater(
      store.saveActiveBatchId('   '),
      throwsArgumentError,
    );
  });
}
