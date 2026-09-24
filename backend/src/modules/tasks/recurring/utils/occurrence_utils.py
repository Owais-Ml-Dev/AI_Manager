from datetime import datetime, timedelta

def parse_date(date_string):
    return datetime.strptime(date_string, "%Y-%m-%d")

def format_date(date_value):
    return date_value.strftime("%Y-%m-%d")

def generate_everyday_dates(start_date, end_date):
    current_date = parse_date(start_date)
    final_date = parse_date(end_date)
    scheduled_dates = []

    while current_date <= final_date:
        scheduled_dates.append(format_date(current_date))
        current_date += timedelta(days=1)

    return scheduled_dates

def generate_weekday_dates(start_date, end_date):
    current_date = parse_date(start_date)
    final_date = parse_date(end_date)
    scheduled_dates = []

    while current_date <= final_date:
        if current_date.weekday() < 5:
            scheduled_dates.append(format_date(current_date))
        current_date += timedelta(days=1)

    return scheduled_dates

def generate_weekend_dates(start_date, end_date):
    current_date = parse_date(start_date)
    final_date = parse_date(end_date)
    scheduled_dates = []

    while current_date <= final_date:
        if current_date.weekday() >= 5:
            scheduled_dates.append(format_date(current_date))
        current_date += timedelta(days=1)

    return scheduled_dates

def generate_custom_dates(custom_dates):
    return sorted(custom_dates)

def generate_occurrence_dates(duration, repeat):
    start_date = duration["start_date"]
    end_date = duration["end_date"]
    repeat_type = repeat["type"]

    if repeat_type == "everyday":
        return generate_everyday_dates(start_date, end_date)

    if repeat_type == "weekdays":
        return generate_weekday_dates(start_date, end_date)

    if repeat_type == "weekends":
        return generate_weekend_dates(start_date, end_date)

    if repeat_type == "custom_dates":
        return generate_custom_dates(repeat.get("custom_dates", []))

    raise ValueError("Unsupported recurring repeat type.")
