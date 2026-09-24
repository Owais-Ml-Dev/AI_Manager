import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/security/gemini_api_key_store.dart';

class AssistantChatResult {
  final String reply;
  final String model;

  const AssistantChatResult({required this.reply, required this.model});
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

class AssistantRepository {
  final ApiClient _apiClient;
  final GeminiApiKeyStore _keyStore;

  AssistantRepository(this._apiClient, this._keyStore);

  Future<AssistantChatResult> sendMessage(
    String message, {
    CancelToken? cancelToken,
  }) async {
    final headers = await _geminiHeaders();
    final result = await _apiClient.post(
      '/api/assistant/chat',
      data: {'message': message},
      cancelToken: cancelToken,
      headers: headers,
    );
    final data = _asMap(result);
    return AssistantChatResult(
      reply: data['reply']?.toString() ?? '',
      model: data['model']?.toString() ?? '',
    );
  }

  Future<AssistantCommandPreview> previewTaskCommand(
    String message, {
    String? draftId,
    CancelToken? cancelToken,
  }) async {
    final headers = await _geminiHeaders();
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
