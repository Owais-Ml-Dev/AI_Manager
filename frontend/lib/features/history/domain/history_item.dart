enum HistoryTaskKind { recurring, repeatUntilDone }

class HistoryItem {
  final String taskId;
  final HistoryTaskKind kind;
  final String title;
  final String priority;

  final String? description;

  final DateTime? date;

  final String? startDate;
  final String? endDate;

  final int done;
  final int missed;
  final int completionRate;

  const HistoryItem({
    required this.taskId,
    required this.kind,
    required this.title,
    required this.priority,
    this.description,
    this.date,
    this.startDate,
    this.endDate,
    this.done = 0,
    this.missed = 0,
    this.completionRate = 0,
  });
}

class HistoryData {
  final List<HistoryItem> recurring;
  final List<HistoryItem> repeatUntilDone;

  const HistoryData({required this.recurring, required this.repeatUntilDone});
}
