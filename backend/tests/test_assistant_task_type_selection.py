from datetime import date

from src.modules.assistant.create_flow import (
    apply_answer,
    next_step,
    prefill_from_message,
    selected_create_action,
)


def test_plain_create_asks_task_type_first():

    task, collect = (
        prefill_from_message(
            "create_repeat_until_done_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Add swimming task",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    step = next_step(
        "create_repeat_until_done_task",
        task,
        collect,
    )

    assert (
        step["field"]
        == "task_type"
    )

    assert (
        step["suggestions"]
        == [
            "Recurring",
            "Repeat Until Done",
        ]
    )


def test_explicit_recurring_skips_type_question():

    task, collect = (
        prefill_from_message(
            "create_recurring_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Add recurring swimming task",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    step = next_step(
        "create_recurring_task",
        task,
        collect,
    )

    assert (
        collect[
            "task_type_confirmed"
        ]
        is True
    )

    assert (
        step["field"]
        == "duration"
    )


def test_can_switch_from_provisional_rud_to_recurring():

    task, collect, understood = (
        apply_answer(
            "task_type",
            "create_repeat_until_done_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Recurring",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    assert understood is True

    assert (
        selected_create_action(
            "create_repeat_until_done_task",
            collect,
        )
        == "create_recurring_task"
    )

    assert (
        task["title"]
        == "Swimming"
    )


def test_can_switch_from_provisional_recurring_to_rud():

    task, collect, understood = (
        apply_answer(
            "task_type",
            "create_recurring_task",
            {
                "title":
                    "Swimming",
            },
            {},
            "Repeat Until Done",
            date(
                2026,
                9,
                24,
            ),
        )
    )

    assert understood is True

    assert (
        selected_create_action(
            "create_recurring_task",
            collect,
        )
        == "create_repeat_until_done_task"
    )

    assert (
        task["title"]
        == "Swimming"
    )
