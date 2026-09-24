enum HomeTaskKind { recurring, repeatUntilDone }

enum HomeTaskStatus { pending, completed, missed }

class HomeTaskItem {
  final String taskId;
  final String? occurrenceId;
  final HomeTaskKind kind;
  final String title;
  final String priority;
  final HomeTaskStatus status;
  final String subtitle;

  const HomeTaskItem({
    required this.taskId,
    required this.kind,
    required this.title,
    required this.priority,
    required this.status,
    required this.subtitle,
    this.occurrenceId,
  });

  bool get isCompleted {
    return status == HomeTaskStatus.completed;
  }

  bool get isMissed {
    return status == HomeTaskStatus.missed;
  }
}

class HomeData {
  final List<HomeTaskItem> recurringTasks;

  final List<HomeTaskItem> repeatUntilDoneTasks;

  final int completedCount;
  final int totalCount;

  const HomeData({
    required this.recurringTasks,
    required this.repeatUntilDoneTasks,
    required this.completedCount,
    required this.totalCount,
  });

  double get progress {
    if (totalCount == 0) {
      return 0;
    }

    return completedCount / totalCount;
  }
}
