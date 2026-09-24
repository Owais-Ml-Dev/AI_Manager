"""Deterministic task candidate and duplicate matching.

No Gemini calls occur here.  MongoDB narrows the candidate set first, then
RapidFuzz compares only the remaining titles.
"""

from rapidfuzz.fuzz import WRatio

from src.config.db import get_db


DUPLICATE_THRESHOLD = 70.0
TARGET_THRESHOLD = 45.0
AUTO_TARGET_THRESHOLD = 90.0
AUTO_TARGET_GAP = 12.0


def _title_score(left, right):
    return float(WRatio(str(left or "").strip(), str(right or "").strip()))


def _reminder_signature(reminders):
    signature = []
    if not isinstance(reminders, list):
        return signature
    for reminder in reminders:
        if not isinstance(reminder, dict):
            continue
        signature.append(
            (
                reminder.get("start_time"),
                reminder.get("end_time"),
                reminder.get("count"),
            )
        )
    return signature


def _candidate_payload(task, score, occurrence_id=None):
    return {
        "id": str(task["_id"]),
        "task_type": task.get("task_type"),
        "title": task.get("title", ""),
        "priority": task.get("priority"),
        "status": task.get("status"),
        "repeat": task.get("repeat"),
        "duration": task.get("duration"),
        "reminders": task.get("reminders", []),
        "score": round(float(score), 1),
        "occurrence_id": occurrence_id,
    }


def find_create_duplicates(command, limit=3):
    """Return likely duplicates for a ready create command."""

    if not isinstance(command, dict):
        return []

    action = command.get("action")
    task = (command.get("arguments") or {}).get("task")
    if not isinstance(task, dict):
        return []

    db = get_db()

    if action == "create_repeat_until_done_task":
        query = {
            "task_type": "repeat_until_done",
            "status": "pending",
        }
    elif action == "create_recurring_task":
        duration = task.get("duration") or {}
        start_date = duration.get("start_date")
        end_date = duration.get("end_date")
        if not start_date or not end_date:
            return []
        query = {
            "task_type": "recurring",
            "status": "active",
            "duration.start_date": {"$lte": end_date},
            "duration.end_date": {"$gte": start_date},
        }
    else:
        return []

    incoming_title = task.get("title", "")
    incoming_repeat = (task.get("repeat") or {}).get("type")
    incoming_reminders = _reminder_signature(task.get("reminders"))

    matches = []
    for existing in db.tasks.find(query):
        score = _title_score(incoming_title, existing.get("title"))

        if incoming_repeat and incoming_repeat == (existing.get("repeat") or {}).get("type"):
            score = min(100.0, score + 3.0)

        existing_reminders = _reminder_signature(existing.get("reminders"))
        if incoming_reminders and incoming_reminders == existing_reminders:
            score = min(100.0, score + 5.0)

        if score >= DUPLICATE_THRESHOLD:
            matches.append(_candidate_payload(existing, score))

    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]


def find_target_candidates(target_text, action, today_date, limit=5):
    """Find active tasks matching words such as 'gym' or 'morning walk'."""

    if not isinstance(target_text, str) or not target_text.strip():
        return []

    db = get_db()
    tasks = db.tasks.find(
        {
            "$or": [
                {"task_type": "repeat_until_done", "status": "pending"},
                {"task_type": "recurring", "status": "active"},
            ]
        },
        {
            "title": 1,
            "task_type": 1,
            "priority": 1,
            "status": 1,
            "repeat": 1,
            "duration": 1,
            "reminders": 1,
        },
    )

    candidates = []
    for task in tasks:
        occurrence_id = None
        if action == "complete_task" and task.get("task_type") == "recurring":
            occurrence = db.task_occurrences.find_one(
                {
                    "task_id": task["_id"],
                    "scheduled_date": today_date,
                    "status": "pending",
                },
                {"_id": 1},
            )
            if occurrence is None:
                continue
            occurrence_id = str(occurrence["_id"])

        score = _title_score(target_text, task.get("title"))
        if score >= TARGET_THRESHOLD:
            candidates.append(_candidate_payload(task, score, occurrence_id))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def obvious_target(candidates):
    """Return the top candidate only when the title match is clearly dominant."""

    if not candidates:
        return None

    top = candidates[0]
    if top["score"] < AUTO_TARGET_THRESHOLD:
        return None

    if len(candidates) == 1:
        return top

    if (top["score"] - candidates[1]["score"]) >= AUTO_TARGET_GAP:
        return top

    return None
