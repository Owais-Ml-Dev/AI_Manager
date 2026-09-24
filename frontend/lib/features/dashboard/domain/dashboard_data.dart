class DashboardDay {
  final String date;
  final String day;
  final int completed;

  const DashboardDay({
    required this.date,
    required this.day,
    required this.completed,
  });
}

class DashboardInsight {
  final String taskTitle;
  final String weekday;
  final int missedCount;
  final String message;

  const DashboardInsight({
    required this.taskTitle,
    required this.weekday,
    required this.missedCount,
    required this.message,
  });
}

class DashboardData {
  final String weekStart;
  final String weekEnd;

  final int done;
  final int missed;
  final int streak;

  final List<DashboardDay> dailyCompletion;

  final int importantUrgent;
  final int importantNotUrgent;
  final int notImportantUrgent;
  final int notImportantNotUrgent;

  final DashboardInsight? insight;

  const DashboardData({
    required this.weekStart,
    required this.weekEnd,
    required this.done,
    required this.missed,
    required this.streak,
    required this.dailyCompletion,
    required this.importantUrgent,
    required this.importantNotUrgent,
    required this.notImportantUrgent,
    required this.notImportantNotUrgent,
    required this.insight,
  });

  int get totalActivePriorityTasks {
    return importantUrgent +
        importantNotUrgent +
        notImportantUrgent +
        notImportantNotUrgent;
  }
}
