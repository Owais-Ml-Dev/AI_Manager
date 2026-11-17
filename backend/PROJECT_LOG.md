# AI Task Manager — Project Log

Backend-only build (no frontend yet). FastAPI + Supabase (Postgres) + Supabase Auth.
Built incrementally, step by step. This log tracks what exists, how it works, the
decisions behind it, and what's deliberately not built yet.

## Stack

- **Framework:** FastAPI (async), Python
- **Database:** Supabase Postgres, via SQLAlchemy 2.0 async + asyncpg
  - Connects via the **session pooler** (`aws-0-<region>.pooler.supabase.com:5432`), not
    the direct host — the direct host is IPv6-only and didn't work on this network.
- **Migrations:** Alembic (async), `alembic/env.py` reads `DATABASE_URL` from `.env`
- **Auth:** Supabase Auth. Backend never handles passwords — it verifies the ES256 JWT
  Supabase issues, via its public JWKS endpoint (`app/core/security.py`). No shared
  secret needed. `jwt.decode(..., leeway=10)` — without the leeway, normal clock jitter
  between servers causes spurious `ImmatureSignatureError`.
- **Cache (planned, not yet wired up):** Upstash Redis — reserved for future AI
  conversation state, never for task data.
- **AI (not yet built):** Google Gemini — reserved for natural-language intent
  extraction only. Per the spec: Gemini never executes DB writes, calculates
  statistics, or runs reminders. All business logic/arithmetic is plain Python.

## Architecture

Feature-based layout under `app/features/<name>/`, each with its own
`models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`.
Shared infra lives in `app/core/` (`config.py`, `database.py`, `security.py`).

```
app/
  core/            config, db engine/session, auth/JWT verification
  common/          shared exceptions (NotFoundError, ValidationError)
  features/
    tasks/         task CRUD, Eisenhower Matrix view
    reminders/     reminder config (date range + day selection) + reminder times
    occurrences/   per-date tracking for recurring tasks
    history/       append-only event log per task
    dashboard/     main dashboard, per-task analytics, calendar
    reports/       monthly productivity report
```

Every feature's own `get_task(db, task_id, user_id)` call (from `tasks.service`) is the
ownership chokepoint — it 404s (never 403) whether a task doesn't exist or just isn't
yours, so existence is never leaked.

## Data model (tables)

- **`tasks`** — `id, user_id (FK auth.users.id, cascade), title, description, category
  (recurring|one_time), urgent, important, status (pending|completed|overdue|cancelled),
  due_date, due_time, created_at, updated_at`
- **`reminder_configs`** — one per task (either category): `start_date, end_date
  (nullable — null means indefinite, recurring tasks only), day_selection_type
  (every_day|weekdays|weekends|custom_weekdays|custom_dates), custom_weekdays,
  custom_dates`
- **`reminder_times`** — many per reminder_config: `time_of_day` (naive, no timezone yet)
- **`occurrences`** — one row per scheduled date for a recurring task: `occurrence_date,
  status (pending|completed|missed|skipped), completed_at`. Generated lazily (no
  background worker yet) whenever occurrences are read for a task — bounded by
  `end_date`, or a rolling 90-day window if indefinite.
- **`task_history_events`** — append-only: `event_type (created|field_updated|
  priority_changed|status_changed|reopened|schedule_changed), field_name, old_value,
  new_value, occurred_at`

No `recurring_schedules` table — it existed briefly (separate recurrence-type model for
recurring tasks) but was **removed and merged into `reminder_configs`** once we decided
recurring and one-time tasks should share the exact same date-range/day-selection/times
mechanism, differing only in completion behavior (whole-task vs. per-occurrence).

## Endpoints

```
POST    /tasks                                   create
GET     /tasks                                   list (own tasks only)
GET     /tasks/matrix?category=                  Eisenhower Matrix, grouped by quadrant
GET     /tasks/{id}                               get one
PATCH   /tasks/{id}                               partial update
DELETE  /tasks/{id}

PUT     /tasks/{id}/reminder-config                set (upsert) date range + day selection
GET     /tasks/{id}/reminder-config
POST    /tasks/{id}/reminder-config/reminder-times add a time
GET     /tasks/{id}/reminder-config/reminder-times
PATCH   /tasks/{id}/reminder-config/reminder-times/{time_id}
DELETE  /tasks/{id}/reminder-config/reminder-times/{time_id}

GET     /tasks/{id}/occurrences                    list (auto-generates + sweeps missed)
PATCH   /tasks/{id}/occurrences/{occurrence_id}    mark completed|skipped

GET     /tasks/{id}/history                        append-only event log

GET     /dashboard                                  totals, completion %, today's occurrences
GET     /tasks/{id}/analytics                       per-task breakdown (recurring: occurrence
                                                     counts + monthly performance + calendar
                                                     history; one-time: status + completed_at)
GET     /calendar?view=daily|weekly|monthly&anchor_date=
GET     /reports/monthly?year=&month=

GET     /health                                     DB + Redis connectivity check
```

All endpoints except `/health` require `Authorization: Bearer <supabase-jwt>`.

## Key policy decisions (the spec deliberately leaves these to the implementer)

- **Missed-occurrence deadline:** an occurrence becomes `missed` once its date is
  strictly in the past (server date). No timezone handling yet.
- **Overdue deadline (one-time tasks):** if only `due_date` is set, overdue starts the
  day *after* it (the whole due date counts as on-time). If `due_time` is also set,
  overdue is exact date+time.
- **"Eligible" for completion-rate denominators** (dashboard, per-task analytics,
  monthly report — all consistent): excludes skipped occurrences, excludes
  future-pending occurrences, excludes cancelled one-time tasks.
- **One-time tasks in a monthly report** are in-scope only if `due_date` falls in that
  month; tasks with no due date aren't tied to any month and are excluded.
- **Eisenhower Matrix** in the monthly report is a live snapshot (not filtered to the
  month) — quadrant membership isn't inherently date-bound.
- **Task reopening** (completed → not-completed) is logged as its own history event
  type (`reopened`), distinct from a generic `status_changed`.
- **No background worker yet**: occurrence generation and overdue detection both happen
  via "sync on read" (whenever the relevant list/dashboard/report endpoint is hit), not
  a scheduled job. This is intentional for now — Phase 3 (reminder delivery) is what
  actually needs a worker.

## What's built (phases, per the original spec)

**Phase 1 — Core backend:** done. Task CRUD, categories, priority/status, due
date + overdue detection, reminder config + times (shared by both task types),
recurring occurrence tracking, task history, Supabase Auth + per-user ownership on
every endpoint.

**Phase 2 — Priority & analytics:** done. Eisenhower Matrix, main dashboard,
per-task analytics, calendar (daily/weekly/monthly), monthly productivity report.

**Phase 3 — Reminder system:** data model only (`reminder_configs`/`reminder_times`
exist). Not built: background worker to actually fire reminders, notification
delivery, Upstash Redis connection (`.env` still has placeholder values).

**Phase 4 — Voice AI:** not started. Needs: Gemini API key, Redis-backed conversation
state machine, intent-extraction → structured JSON → Pydantic validation → confirmation
flow, before any AI-initiated write is allowed to execute.

**Phase 5 — Frontend:** out of scope per the original request (backend only).

**Phase 6 — Testing:** manual curl-script regression testing only, run after every
feature addition (tasks CRUD, reminders, occurrences, overdue, history, auth isolation,
matrix, dashboard, analytics, calendar, reports — all independently verified against
real Supabase data with two separate signed-up users to confirm isolation). No
automated `pytest` suite yet, despite `pytest`/`pytest-asyncio` being in
`requirements.txt` since the initial scaffold.

## Bugs found and fixed along the way

- Two separate `delete`/`update` naming collisions where a repository module's own
  function name shadowed the same-named SQLAlchemy import, causing infinite
  self-recursion instead of executing SQL (`tasks/repository.py`, same pattern caught
  twice).
- `get_reminder_config`, `get_schedule` (now removed), and `update_occurrence` initially
  had no ownership check at all — any authenticated user could read/modify another
  user's reminder config, schedule, or occurrences by guessing a task ID. Fixed by
  routing every one through the ownership-checking `get_task`.
- JWT verification used PyJWT's default `leeway=0`, causing intermittent
  `ImmatureSignatureError` from ~tens of milliseconds of ordinary clock drift between
  this server and Supabase's. Fixed with `leeway=10`.
- Postgres enum types created via `op.add_column` (not `op.create_table`) need an
  explicit `sa.Enum(...).create(op.get_bind())` in the migration — Alembic's
  autogenerate doesn't add that automatically outside of table creation. Hit this twice
  (`task_category`, `task_status`, `occurrence_status`) before it became routine.
- Monthly report's per-task completion percentage initially used `scheduled − skipped`
  as the denominator (wrongly including future not-yet-elapsed days), inconsistent with
  the matching overall-recurring-performance formula. Fixed to track per-task
  eligibility (date ≤ today, not skipped) the same way as the aggregate.

## Environment / secrets

`backend/.env` (gitignored, never committed) holds: `DATABASE_URL` (Supabase pooler
connection string), `SUPABASE_URL` (not secret, used for JWKS), `REDIS_URL` (still
placeholder — Upstash not yet configured), `GEMINI_API_KEY` (empty, for Phase 4).
`backend/.env.example` is the template, kept free of real values.
