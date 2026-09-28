from datetime import datetime, timezone

from bson import ObjectId

from src.config.db import get_db


def _create_recurring_task(
    title="Guided Update Gym",
):
    db = get_db()

    now = datetime.now(
        timezone.utc
    )

    result = db.tasks.insert_one({
        "task_type": "recurring",

        "title": title,

        "description": "Workout task",

        "priority":
            "important_not_urgent",

        "duration": {
            "start_date":
                "2026-09-25",

            "end_date":
                "2026-10-25",
        },

        "repeat": {
            "type": "everyday",
            "custom_dates": [],
        },

        "reminders": [
            {
                "start_time":
                    "18:00",

                "end_time":
                    "19:00",

                "count": 2,

                "generated_times": [
                    "18:00",
                    "19:00",
                ],
            }
        ],

        "status": "active",

        "occurrence_count": 0,

        "created_at": now,
        "updated_at": now,
    })

    return str(
        result.inserted_id
    )


def test_guided_update_title_end_to_end(
    client,
    monkeypatch,
):
    """
    Expected flow:

    Update task
        -> backend finds one matching task
        -> asks which field to update
        -> user chooses Title
        -> asks for new title
        -> shows ready confirmation preview
        -> database is STILL unchanged
        -> Confirm
        -> backend update service runs
        -> MongoDB is updated
    """

    task_id = (
        _create_recurring_task()
    )

    # Gemini must never be needed for this explicit
    # guided update workflow.
    def gemini_must_not_run(
        **kwargs,
    ):
        raise AssertionError(
            "Gemini must not run "
            "for guided update."
        )

    monkeypatch.setattr(
        (
            "src.modules.assistant."
            "drafts.service."
            "parse_task_message"
        ),
        gemini_must_not_run,
    )

    # =====================================================
    # STEP 1:
    # User asks to update task.
    # =====================================================

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message":
                "Update guided update gym task",

            "timezone":
                "+05:30",
        },
    )

    assert (
        response.status_code
        == 200
    ), response.get_json()

    data = (
        response
        .get_json()["data"]
    )

    assert (
        data["status"]
        == "needs_input"
    ), data

    assert (
        data["missing_fields"]
        == ["update_field"]
    ), data

    assert (
        "Title"
        in data.get(
            "suggestions",
            [],
        )
    ), data

    draft_id = data[
        "draft_id"
    ]

    # =====================================================
    # STEP 2:
    # User chooses Title.
    # =====================================================

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Title",

            "timezone":
                "+05:30",
        },
    )

    assert (
        response.status_code
        == 200
    ), response.get_json()

    data = (
        response
        .get_json()["data"]
    )

    assert (
        data["status"]
        == "needs_input"
    ), data

    assert (
        data["missing_fields"]
        == ["update.title"]
    ), data

    # =====================================================
    # STEP 3:
    # User supplies new title.
    # =====================================================

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Evening Gym",

            "timezone":
                "+05:30",
        },
    )

    assert (
        response.status_code
        == 200
    ), response.get_json()

    data = (
        response
        .get_json()["data"]
    )

    assert (
        data["status"]
        == "ready"
    ), data

    command = data[
        "command"
    ]

    assert (
        command["action"]
        == "update_recurring_task"
    )

    assert (
        command[
            "arguments"
        ][
            "task_id"
        ]
        == task_id
    )

    assert (
        command[
            "arguments"
        ][
            "changes"
        ][
            "title"
        ]
        == "Evening Gym"
    )

    assert (
        command[
            "requires_confirmation"
        ]
        is True
    )

    # =====================================================
    # IMPORTANT:
    # Preview must NOT change MongoDB.
    # =====================================================

    before = (
        get_db()
        .tasks
        .find_one({
            "_id":
                ObjectId(
                    task_id
                )
        })
    )

    assert (
        before["title"]
        == "Guided Update Gym"
    )

    # =====================================================
    # STEP 4:
    # User presses Confirm.
    # =====================================================

    response = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id":
                draft_id,

            "confirmed":
                True,
        },
    )

    assert (
        response.status_code
        == 200
    ), response.get_json()

    # =====================================================
    # NOW MongoDB must be updated.
    # =====================================================

    after = (
        get_db()
        .tasks
        .find_one({
            "_id":
                ObjectId(
                    task_id
                )
        })
    )

    assert (
        after["title"]
        == "Evening Gym"
    )


def test_guided_update_does_not_modify_before_confirm(
    client,
    monkeypatch,
):
    """
    Cancel/not-confirm behavior:
    reaching the preview must never modify the task.
    """

    task_id = (
        _create_recurring_task(
            "Update Safety Task"
        )
    )

    def gemini_must_not_run(
        **kwargs,
    ):
        raise AssertionError(
            "Gemini must not run."
        )

    monkeypatch.setattr(
        (
            "src.modules.assistant."
            "drafts.service."
            "parse_task_message"
        ),
        gemini_must_not_run,
    )

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message":
                "Update update safety task",

            "timezone":
                "+05:30",
        },
    )

    assert response.status_code == 200

    data = response.get_json()[
        "data"
    ]

    draft_id = data[
        "draft_id"
    ]

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Title",

            "timezone":
                "+05:30",
        },
    )

    assert response.status_code == 200

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Changed But Not Confirmed",

            "timezone":
                "+05:30",
        },
    )

    assert response.status_code == 200

    data = response.get_json()[
        "data"
    ]

    assert (
        data["status"]
        == "ready"
    )

    task = (
        get_db()
        .tasks
        .find_one({
            "_id":
                ObjectId(
                    task_id
                )
        })
    )

    assert (
        task["title"]
        == "Update Safety Task"
    )


def test_guided_update_confirm_is_execute_once(
    client,
    monkeypatch,
):
    """
    Confirm must remain execute-once.
    """

    task_id = (
        _create_recurring_task(
            "Execute Once Update"
        )
    )

    def gemini_must_not_run(
        **kwargs,
    ):
        raise AssertionError(
            "Gemini must not run."
        )

    monkeypatch.setattr(
        (
            "src.modules.assistant."
            "drafts.service."
            "parse_task_message"
        ),
        gemini_must_not_run,
    )

    response = client.post(
        "/api/assistant/task-command/preview",
        json={
            "message":
                "Update execute once update task",

            "timezone":
                "+05:30",
        },
    )

    data = response.get_json()[
        "data"
    ]

    draft_id = data[
        "draft_id"
    ]

    client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Title",

            "timezone":
                "+05:30",
        },
    )

    client.post(
        "/api/assistant/task-command/preview",
        json={
            "draft_id":
                draft_id,

            "message":
                "Updated Once",

            "timezone":
                "+05:30",
        },
    )

    first = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id":
                draft_id,

            "confirmed":
                True,
        },
    )

    assert first.status_code == 200

    second = client.post(
        "/api/assistant/task-command/execute",
        json={
            "draft_id":
                draft_id,

            "confirmed":
                True,
        },
    )

    assert second.status_code in {
        409,
        410,
    }

    task = (
        get_db()
        .tasks
        .find_one({
            "_id":
                ObjectId(
                    task_id
                )
        })
    )

    assert (
        task["title"]
        == "Updated Once"
    )
