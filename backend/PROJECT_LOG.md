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

## Live testing, assistant hardening, region move, model choice (2026-11-18/19)

**Test tooling** (`backend/manual/`): `manual_tests.http` (VS Code REST Client
walkthrough of every endpoint; login read from `manual/.env`, gitignored),
`gemini_e2e.py` (automated sign-up/login + full assistant conversation against the REAL
Gemini, DB-checked after every message, per-call latency/tokens/model version, report
to `manual/reports/`, gitignored; `--reworded` runs phrasings that appear nowhere in the
prompt), `gemini_model_bench.py` (same 16 messages to several models, speed + graded
accuracy). Pytest suite: 72 tests.

**Assistant bugs found by the live runs, fixed with regression tests:**
- Task selection trapped the user: anything but a number re-asked "which one?" forever
  (even "no") until the 10-min state expired. Now "no" cancels, an out-of-range number
  re-asks, anything else is treated as a new request.
- Gemini read "make X urgent" as `create_task` -> confirming created a duplicate. Prompt
  now spells out create vs change_priority/update/complete/delete; Python also warns
  before confirming a create whose exact title already exists.
- Task lookup was substring-only: "feeding the cat" didn't find "Feed the cat",
  "passport wala task" found nothing. Now deterministic: substring first, then
  all-key-words match after removing filler words and simple stemming. Never guesses —
  several matches still ask the user to pick. (A vector DB was considered and rejected:
  overkill for matching within one user's own task list, adds an AI call and
  nondeterminism.)
- A prompt example matched a test message word for word ("call it Water the plants"),
  inflating that test. Replaced with a neutral example; the `--reworded` set guards
  against this.
- Gemini down/slow now replies "The assistant is busy... try again" and keeps the
  in-progress request (was "didn't understand", which blamed the user's wording).
  `GeminiUnavailableError` (timeout/network/429/5xx) vs `GeminiError` (unusable answer).
- "no"/"cancel" with nothing pending is answered by rule ("Nothing to cancel."), no
  Gemini call; it also cancels a half-collected request.

**Latency.** Measured, not assumed: the DB was in Tokyo (~300 ms per round trip from
India) and requests make several sequential round trips (connection pre-ping + BEGIN,
prepare + execute per new statement, COMMIT) -> list tasks 3.4s, assistant "yes" 6.5s,
dashboard 9.6s. Moved to a new Supabase project in **Mumbai (ap-south-1)**, same
migrations: round trip 6 ms; list tasks 0.07s, "yes" 0.19s, dashboard 0.23s; pytest
~15 min -> 33s. Gemini is now ~95% of assistant response time.

**Gemini model.** Benchmarked on the real prompt (2026-11-19): `gemini-3.1-flash-lite`
31/32 correct, median 1.2s; `gemini-3.5-flash-lite` (what `-latest` resolved to) 30/32,
median 4.5s. `gemini-2.5-flash` / `-lite` are retired for new users; `gemini-3.8-flash`
allows only 20 requests/day on the free tier (unusable without a paid plan). Now pinned
to `gemini-3.1-flash-lite` (override with `GEMINI_MODEL`). Requests use
`responseMimeType: application/json`; all answer parts are joined; unparseable answers
log `finishReason` + model version (a rare cut-off answer was seen once, cause not yet
confirmed). Timeout 8s per attempt + 1 retry: 4s was tried and cut off real 4-8s
answers; 8s gave 0 user-visible failures in 33 calls. Free tier also rate-limits per
minute (429), which the fast backend can now hit.

## Environment / secrets

`backend/.env` (gitignored, never committed) holds: `DATABASE_URL` (Supabase pooler
connection string), `SUPABASE_URL` (not secret, used for JWKS), `REDIS_URL` (Upstash,
TLS), `GEMINI_API_KEY`, optional `GEMINI_MODEL`. `backend/.env.test` holds the pytest accounts
and publishable key; `backend/manual/.env` the manual-testing login.
`backend/.env.example` is the template, kept free of real values.
