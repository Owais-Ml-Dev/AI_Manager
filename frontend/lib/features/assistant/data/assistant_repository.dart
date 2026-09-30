import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/gemini_api_key_store.dart';

class AssistantLiveToken {
  final String token;
  final String model;

  const AssistantLiveToken({required this.token, required this.model});

  factory AssistantLiveToken.fromMap(Map<String, dynamic> data) {
    return AssistantLiveToken(
      token: data['token']?.toString() ?? '',
      model: data['model']?.toString() ?? 'gemini-3.8-live',
    );
  }
}

class AssistantChatResult {
  final String reply;
  final String provider;
  final String model;
  final bool fallbackUsed;

  const AssistantChatResult({
    required this.reply,
    required this.provider,
    required this.model,
    required this.fallbackUsed,
  });
}

class AssistantTaskMatch {
  final String id;
  final String taskType;
  final String title;
  final double score;
  final String? occurrenceId;
  final Map<String, dynamic> raw;

  const AssistantTaskMatch({
    required this.id,
    required this.taskType,
    required this.title,
    required this.score,
    required this.raw,
    this.occurrenceId,
  });

  factory AssistantTaskMatch.fromMap(Map<String, dynamic> data) {
    return AssistantTaskMatch(
      id: data['id']?.toString() ?? '',
      taskType: data['task_type']?.toString() ?? '',
      title: data['title']?.toString() ?? 'Untitled task',
      score: (data['score'] is num) ? (data['score'] as num).toDouble() : 0,
      occurrenceId: data['occurrence_id']?.toString(),
      raw: data,
    );
  }
}

class AssistantCommandPreview {
  final String model;
  final String timezone;
  final String draftId;
  final String status;
  final String? question;
  final List<String> missingFields;
  final Map<String, dynamic> command;
  final List<AssistantTaskMatch> duplicateMatches;
  final List<AssistantTaskMatch> targetMatches;

  /// Quick replies for the current question, e.g. ["AM", "PM"].
  final List<String> suggestions;

  const AssistantCommandPreview({
    required this.model,
    required this.timezone,
    required this.draftId,
    required this.status,
    required this.command,
    required this.missingFields,
    required this.duplicateMatches,
    required this.targetMatches,
    this.question,
    this.suggestions = const [],
  });

  String get action => command['action']?.toString() ?? '';
  String get summary => command['summary']?.toString() ?? '';
  bool get requiresConfirmation => command['requires_confirmation'] == true;
  bool get needsInput => status == 'needs_input';
  bool get needsTargetSelection => status == 'needs_target_selection';
  bool get duplicateReview => status == 'duplicate_review';
  bool get ready => status == 'ready';

  Map<String, dynamic> get arguments {
    final value = command['arguments'];
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }
}

Map<String, dynamic> _assistantMap(dynamic value) {
  if (value is! Map) return <String, dynamic>{};
  return value.map((key, value) => MapEntry(key.toString(), value));
}

List<dynamic> _assistantList(dynamic value) {
  if (value is! List) return const <dynamic>[];
  return value;
}

AssistantCommandPreview _assistantPreviewFromMap(Map<String, dynamic> data) {
  return AssistantCommandPreview(
    model: data['model']?.toString() ?? '',
    timezone: data['timezone']?.toString() ?? '',
    draftId: data['draft_id']?.toString() ?? '',
    status: data['status']?.toString() ?? '',
    question: data['question']?.toString(),
    missingFields: _assistantList(data['missing_fields'])
        .map((value) => value.toString())
        .toList(),
    command: _assistantMap(data['command']),
    duplicateMatches: _assistantList(data['duplicate_matches'])
        .map(_assistantMap)
        .map(AssistantTaskMatch.fromMap)
        .where((match) => match.id.isNotEmpty)
        .toList(),
    targetMatches: _assistantList(data['target_matches'])
        .map(_assistantMap)
        .map(AssistantTaskMatch.fromMap)
        .where((match) => match.id.isNotEmpty)
        .toList(),
    suggestions: _assistantList(data['suggestions'])
        .map((value) => value.toString())
        .where((value) => value.isNotEmpty)
        .toList(),
  );
}

class AssistantTaskBatchStartResult {
  final String batchId;
  final int totalTasks;
  final int currentTaskNumber;
  final String provider;
  final String model;
  final bool fallbackUsed;
  final AssistantCommandPreview activeDraft;

  const AssistantTaskBatchStartResult({
    required this.batchId,
    required this.totalTasks,
    required this.currentTaskNumber,
    required this.provider,
    required this.model,
    required this.fallbackUsed,
    required this.activeDraft,
  });

  bool get hasMultipleTasks => totalTasks > 1;

  factory AssistantTaskBatchStartResult.fromMap(Map<String, dynamic> data) {
    final activeTask = _assistantMap(data['active_task']);
    final draft = _assistantMap(activeTask['draft']);

    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    return AssistantTaskBatchStartResult(
      batchId: data['batch_id']?.toString() ?? '',
      totalTasks: asInt(data['total_tasks']),
      currentTaskNumber: asInt(data['current_task_number']),
      provider: data['provider']?.toString() ?? '',
      model: data['model']?.toString() ?? '',
      fallbackUsed: data['fallback_used'] == true,
      activeDraft: _assistantPreviewFromMap(draft),
    );
  }
}

class AssistantTaskBatchActiveResult {
  final String batchId;
  final String batchStatus;
  final int totalTasks;
  final int currentTaskNumber;
  final String itemStatus;
  final AssistantCommandPreview activeDraft;

  const AssistantTaskBatchActiveResult({
    required this.batchId,
    required this.batchStatus,
    required this.totalTasks,
    required this.currentTaskNumber,
    required this.itemStatus,
    required this.activeDraft,
  });

  factory AssistantTaskBatchActiveResult.fromMap(Map<String, dynamic> data) {
    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    return AssistantTaskBatchActiveResult(
      batchId: data['batch_id']?.toString() ?? '',
      batchStatus: data['batch_status']?.toString() ?? '',
      totalTasks: asInt(data['total_tasks']),
      currentTaskNumber: asInt(data['current_task_number']),
      itemStatus: data['item_status']?.toString() ?? '',
      activeDraft: _assistantPreviewFromMap(_assistantMap(data['draft'])),
    );
  }
}

class AssistantTaskBatchResolutionResult {
  final String batchId;
  final String batchStatus;
  final int resolvedTaskNumber;
  final String resolution;
  final int? currentTaskNumber;
  final int totalTasks;
  final bool allDone;
  final AssistantTaskBatchActiveResult? nextTask;
  final String? nextTaskError;

  const AssistantTaskBatchResolutionResult({
    required this.batchId,
    required this.batchStatus,
    required this.resolvedTaskNumber,
    required this.resolution,
    required this.currentTaskNumber,
    required this.totalTasks,
    required this.allDone,
    required this.nextTask,
    required this.nextTaskError,
  });

  factory AssistantTaskBatchResolutionResult.fromMap(
    Map<String, dynamic> data,
  ) {
    int asInt(dynamic value) {
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value?.toString() ?? '') ?? 0;
    }

    int? asNullableInt(dynamic value) {
      if (value == null) return null;
      if (value is int) return value;
      if (value is num) return value.toInt();
      return int.tryParse(value.toString());
    }

    final nextTaskMap = _assistantMap(data['next_task']);
    final nextTaskErrorMap = _assistantMap(data['next_task_error']);

    return AssistantTaskBatchResolutionResult(
      batchId: data['batch_id']?.toString() ?? '',
      batchStatus: data['batch_status']?.toString() ?? '',
      resolvedTaskNumber: asInt(data['resolved_task_number']),
      resolution: data['resolution']?.toString() ?? '',
      currentTaskNumber: asNullableInt(data['current_task_number']),
      totalTasks: asInt(data['total_tasks']),
      allDone: data['all_done'] == true,
      nextTask: nextTaskMap.isEmpty
          ? null
          : AssistantTaskBatchActiveResult.fromMap(nextTaskMap),
      nextTaskError: nextTaskErrorMap['message']?.toString(),
    );
  }
}

class AssistantRepository {
  final ApiClient _apiClient;
  final GeminiApiKeyStore _keyStore;

  AssistantRepository(this._apiClient, this._keyStore);

  Future<AssistantLiveToken> createLiveToken() async {
    final headers = await _geminiHeaders();

    final result = await _apiClient.post(
      '/api/assistant/live/token',
      data: const <String, dynamic>{},
      headers: headers,
    );

    final token = AssistantLiveToken.fromMap(_asMap(result));

    if (token.token.isEmpty) {
      throw const ApiException(
        message: 'The backend did not return a Live token.',
      );
    }

    return token;
  }

  Future<AssistantChatResult> sendMessage(
    String message, {
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();
    final result = await _apiClient.post(
      '/api/assistant/chat',
      data: {'message': message},
      cancelToken: cancelToken,
      headers: headers,
    );
    final data = _asMap(result);
    return AssistantChatResult(
      reply: data['reply']?.toString() ?? '',
      provider: data['provider']?.toString() ?? '',
      model: data['model']?.toString() ?? '',
      fallbackUsed: data['fallback_used'] == true,
    );
  }

  Future<AssistantTaskBatchStartResult> startTaskBatch(
    String message, {
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();

    final result = await _apiClient.post(
      '/api/assistant/task-batch/start',
      data: <String, dynamic>{
        'message': message,
        'timezone': _deviceUtcOffset(),
      },
      cancelToken: cancelToken,
      headers: headers,
    );

    final batch = AssistantTaskBatchStartResult.fromMap(_asMap(result));

    if (batch.batchId.isEmpty || batch.activeDraft.draftId.isEmpty) {
      throw const ApiException(
        message: 'The backend returned an invalid task batch.',
      );
    }

    return batch;
  }

  Future<AssistantTaskBatchActiveResult> getActiveTaskBatch(
    String batchId,
  ) async {
    final result = await _apiClient.get(
      '/api/assistant/task-batch/$batchId/active',
    );

    final active = AssistantTaskBatchActiveResult.fromMap(_asMap(result));

    if (active.batchId.isEmpty || active.activeDraft.draftId.isEmpty) {
      throw const ApiException(
        message: 'The backend returned an invalid active batch task.',
      );
    }

    return active;
  }

  Future<AssistantTaskBatchActiveResult> continueTaskBatch({
    required String batchId,
    required String message,
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();

    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/continue',
      data: <String, dynamic>{'message': message},
      cancelToken: cancelToken,
      headers: headers,
    );

    final active = AssistantTaskBatchActiveResult.fromMap(_asMap(result));

    if (active.batchId.isEmpty || active.activeDraft.draftId.isEmpty) {
      throw const ApiException(
        message: 'The backend returned an invalid active batch task.',
      );
    }

    return active;
  }

  Future<AssistantTaskBatchResolutionResult> confirmTaskBatch({
    required String batchId,
    required String draftId,
    String? duplicateDecision,
    String? candidateId,
  }) async {
    final payload = <String, dynamic>{'draft_id': draftId};

    if (duplicateDecision != null) {
      payload['duplicate_decision'] = duplicateDecision;
    }
    if (candidateId != null) {
      payload['candidate_id'] = candidateId;
    }

    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/confirm',
      data: payload,
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch confirmation result.',
      );
    }

    return resolution;
  }

  Future<AssistantTaskBatchResolutionResult> cancelTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/cancel',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch cancellation result.',
      );
    }

    return resolution;
  }

  Future<AssistantTaskBatchResolutionResult> deferTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/defer',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final resolution = AssistantTaskBatchResolutionResult.fromMap(
      _asMap(result),
    );

    if (resolution.batchId.isEmpty || resolution.resolvedTaskNumber < 1) {
      throw const ApiException(
        message: 'The backend returned an invalid batch skip result.',
      );
    }

    return resolution;
  }

  Future<Map<String, dynamic>> abortTaskBatch({
    required String batchId,
    required String draftId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-batch/$batchId/abort',
      data: <String, dynamic>{'draft_id': draftId},
    );

    final data = _asMap(result);
    if (data['batch_id']?.toString().isEmpty != false ||
        data['batch_status']?.toString() != 'aborted') {
      throw const ApiException(
        message: 'The backend returned an invalid batch discard result.',
      );
    }

    return data;
  }

  Future<AssistantCommandPreview> previewTaskCommand(
    String message, {
    String? draftId,
    CancelToken? cancelToken,
  }) async {
    final headers = await _providerHeaders();
    final payload = <String, dynamic>{
      'message': message,
      'timezone': _deviceUtcOffset(),
    };
    if (draftId != null && draftId.isNotEmpty) {
      payload['draft_id'] = draftId;
    }

    final result = await _apiClient.post(
      '/api/assistant/task-command/preview',
      data: payload,
      cancelToken: cancelToken,
      headers: headers,
    );
    return _previewFromMap(_asMap(result));
  }

  Future<AssistantCommandPreview> selectTaskTarget({
    required String draftId,
    required String taskId,
  }) async {
    final result = await _apiClient.post(
      '/api/assistant/task-command/select-target',
      data: {'draft_id': draftId, 'task_id': taskId},
    );
    return _previewFromMap(_asMap(result));
  }

  Future<Map<String, dynamic>> executeTaskCommand({
    required String draftId,
    required bool confirmed,
    String? duplicateDecision,
    String? candidateId,
  }) async {
    final payload = <String, dynamic>{
      'draft_id': draftId,
      'confirmed': confirmed,
    };
    if (duplicateDecision != null) {
      payload['duplicate_decision'] = duplicateDecision;
    }
    if (candidateId != null) {
      payload['candidate_id'] = candidateId;
    }

    final result = await _apiClient.post(
      '/api/assistant/task-command/execute',
      data: payload,
    );
    return _asMap(result);
  }

  AssistantCommandPreview _previewFromMap(Map<String, dynamic> data) {
    return AssistantCommandPreview(
      model: data['model']?.toString() ?? '',
      timezone: data['timezone']?.toString() ?? '',
      draftId: data['draft_id']?.toString() ?? '',
      status: data['status']?.toString() ?? '',
      question: data['question']?.toString(),
      missingFields: _asList(data['missing_fields'])
          .map((value) => value.toString())
          .toList(),
      command: _asMap(data['command']),
      duplicateMatches: _asList(data['duplicate_matches'])
          .map(_asMap)
          .map(AssistantTaskMatch.fromMap)
          .where((match) => match.id.isNotEmpty)
          .toList(),
      targetMatches: _asList(data['target_matches'])
          .map(_asMap)
          .map(AssistantTaskMatch.fromMap)
          .where((match) => match.id.isNotEmpty)
          .toList(),
      suggestions: _asList(data['suggestions'])
          .map((value) => value.toString())
          .where((value) => value.isNotEmpty)
          .toList(),
    );
  }

  Future<Map<String, dynamic>> _geminiHeaders() async {
    final apiKey = await _keyStore.read();
    if (apiKey == null) {
      throw const ApiException(
        message: 'Add your Gemini API key in Settings first.',
      );
    }
    return {'X-Gemini-Api-Key': apiKey};
  }

  Future<Map<String, dynamic>> _providerHeaders() async {
    final headers = <String, dynamic>{};

    final gemini = await _keyStore.readProviderApiKey('gemini');
    final groq = await _keyStore.readProviderApiKey('groq');
    final cloudflare = await _keyStore.readProviderApiKey('cloudflare');
    final cloudflareAccountId = await _keyStore.readCloudflareAccountId();
    final openrouter = await _keyStore.readProviderApiKey('openrouter');
    final cerebras = await _keyStore.readProviderApiKey('cerebras');

    final mistral = await _keyStore.readProviderApiKey('mistral');

    final nvidia = await _keyStore.readProviderApiKey('nvidia');

    if (gemini != null) headers['X-Gemini-Api-Key'] = gemini;
    if (groq != null) headers['X-Groq-Api-Key'] = groq;
    if (cloudflare != null && cloudflareAccountId != null) {
      headers['X-Cloudflare-Api-Token'] = cloudflare;
      headers['X-Cloudflare-Account-Id'] = cloudflareAccountId;
    }
    if (openrouter != null) headers['X-OpenRouter-Api-Key'] = openrouter;

    if (cerebras != null) {
      headers['X-Cerebras-Api-Key'] = cerebras;
    }

    if (mistral != null) {
      headers['X-Mistral-Api-Key'] = mistral;
    }

    if (nvidia != null) {
      headers['X-Nvidia-Api-Key'] = nvidia;
    }

    if (headers.isEmpty) {
      throw const ApiException(
        message: 'Add at least one AI provider API key in Settings first.',
      );
    }

    final autoFallback = await _keyStore.readAutoFallback();

    headers['X-AI-Auto-Fallback'] = autoFallback ? 'true' : 'false';

    final preferredProvider = await _keyStore.readPreferredProvider();

    headers['X-AI-Preferred-Provider'] = preferredProvider;

    return headers;
  }

  String _deviceUtcOffset() {
    final totalMinutes = DateTime.now().timeZoneOffset.inMinutes;
    final sign = totalMinutes < 0 ? '-' : '+';
    final absoluteMinutes = totalMinutes.abs();
    final hours = (absoluteMinutes ~/ 60).toString().padLeft(2, '0');
    final minutes = (absoluteMinutes % 60).toString().padLeft(2, '0');
    return '$sign$hours:$minutes';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is! Map) return {};
    return value.map((key, value) => MapEntry(key.toString(), value));
  }

  List<dynamic> _asList(dynamic value) {
    if (value is! List) return const [];
    return value;
  }
}
