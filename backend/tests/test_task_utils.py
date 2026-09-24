from src.modules.tasks.recurring.utils.occurrence_utils import (
    generate_occurrence_dates
)

from src.modules.tasks.recurring.utils.reminder_utils import (
    generate_reminder_times as recurring_reminder_times
)

from src.modules.tasks.repeat_until_done.utils.reminder_utils import (
    generate_reminder_times as repeat_until_done_reminder_times
)


def test_recurring_everyday_generation():
    assert generate_occurrence_dates(
        {
            "start_date": "2026-09-15",
            "end_date": "2026-09-18"
        },
        {
            "type": "everyday",
            "custom_dates": []
        }
    ) == [
        "2026-09-15",
        "2026-09-16",
        "2026-09-17",
        "2026-09-18"
    ]


def test_recurring_weekday_generation():
    assert generate_occurrence_dates(
        {
            "start_date": "2026-09-14",
            "end_date": "2026-09-20"
        },
        {
            "type": "weekdays",
            "custom_dates": []
        }
    ) == [
        "2026-09-14",
        "2026-09-15",
        "2026-09-16",
        "2026-09-17",
        "2026-09-18"
    ]


def test_recurring_weekend_generation():
    assert generate_occurrence_dates(
        {
            "start_date": "2026-09-14",
            "end_date": "2026-09-20"
        },
        {
            "type": "weekends",
            "custom_dates": []
        }
    ) == [
        "2026-09-19",
        "2026-09-20"
    ]


def test_custom_dates_are_sorted():
    assert generate_occurrence_dates(
        {
            "start_date": "2026-09-01",
            "end_date": "2026-09-30"
        },
        {
            "type": "custom_dates",
            "custom_dates": [
                "2026-09-24",
                "2026-09-15",
                "2026-09-17"
            ]
        }
    ) == [
        "2026-09-15",
        "2026-09-17",
        "2026-09-24"
    ]


def test_invalid_occurrence_repeat_type_raises():
    import pytest

    with pytest.raises(ValueError):
        generate_occurrence_dates(
            {
                "start_date": "2026-09-01",
                "end_date": "2026-09-30"
            },
            {
                "type": "bad_type",
                "custom_dates": []
            }
        )


def test_recurring_reminder_generation():
    assert recurring_reminder_times(
        "19:00",
        "21:00",
        3
    ) == [
        "19:00",
        "20:00",
        "21:00"
    ]


def test_recurring_single_reminder_uses_start_time():
    assert recurring_reminder_times(
        "19:00",
        "21:00",
        1
    ) == ["19:00"]


def test_recurring_reminder_count_must_be_positive():
    import pytest

    with pytest.raises(ValueError):
        recurring_reminder_times(
            "19:00",
            "21:00",
            0
        )


def test_recurring_reminder_start_must_be_before_end():
    import pytest

    with pytest.raises(ValueError):
        recurring_reminder_times(
            "21:00",
            "19:00",
            2
        )


def test_repeat_until_done_reminder_generation():
    assert repeat_until_done_reminder_times(
        "09:00",
        "10:00",
        3
    ) == [
        "09:00",
        "09:30",
        "10:00"
    ]


def test_repeat_until_done_single_reminder_uses_start_time():
    assert repeat_until_done_reminder_times(
        "09:00",
        "10:00",
        1
    ) == ["09:00"]


def test_repeat_until_done_reminder_count_must_be_positive():
    import pytest

    with pytest.raises(ValueError):
        repeat_until_done_reminder_times(
            "09:00",
            "10:00",
            0
        )


def test_repeat_until_done_reminder_start_must_be_before_end():
    import pytest

    with pytest.raises(ValueError):
        repeat_until_done_reminder_times(
            "10:00",
            "09:00",
            2
        )
