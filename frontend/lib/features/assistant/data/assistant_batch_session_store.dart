import 'package:shared_preferences/shared_preferences.dart';

class AssistantBatchSessionStore {
  static const String activeBatchIdKey = 'assistant_active_task_batch_id';

  const AssistantBatchSessionStore();

  Future<String?> loadActiveBatchId() async {
    final preferences = await SharedPreferences.getInstance();
    final value = preferences.getString(activeBatchIdKey)?.trim();

    if (value == null || value.isEmpty) {
      return null;
    }

    return value;
  }

  Future<void> saveActiveBatchId(String batchId) async {
    final value = batchId.trim();
    if (value.isEmpty) {
      throw ArgumentError.value(
        batchId,
        'batchId',
        'Active batch id cannot be empty.',
      );
    }

    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(activeBatchIdKey, value);
  }

  Future<void> clearActiveBatchId() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(activeBatchIdKey);
  }
}
