# AI Task Manager — Project Log

Backend-only build (Android frontend comes later). FastAPI + Supabase (Postgres +
Auth) + Upstash Redis + Google Gemini + Firebase Cloud Messaging. Built step by
step. This log records what exists, how it works, the decisions behind it, test
results, and what's left.

## Current status (2026-11-19, commit `2e7cb41`)

Backend Phase 1 is complete and verified: 33 endpoints, 9 tables, 16 migrations,
137 automated tests passing (run with Firebase enabled), live Gemini conversations
passing, real Firebase project verified. Not yet pushed to GitHub (repository access
pending). See [Remaining work](#remaining-work).

## Stack

- **Framework:** FastAPI (async), Python 3.10
- **Database:** Supabase Postgres in **Mumbai (`ap-south-1`)**, via SQLAlchemy 2.0
  async + asyncpg, through the session pooler (`aws-1-ap-south-1.pooler.supabase.com`;
  the direct host is IPv6-only). ~6 ms per round trip from India.
- **Migrations:** Alembic (async); 16 migrations, every one verified to upgrade AND
  roll back cleanly (`manual/check_migrations.py`).
- **Auth:** Supabase Auth. The backend never handles passwords; it verifies the ES256
  JWT via Supabase's public JWKS (`app/core/security.py`), `leeway=10` for clock jitter.
- **Redis:** Upstash (TLS). Scratch space only: assistant conversation state (10-min
  TTL) and Gemini model-quota memory. Never task data.
- **AI:** Google Gemini, intent extraction ONLY (text -> validated JSON). Fallback
  chain `gemini-3.1-flash-lite > gemini-3.5-flash-lite > gemini-3.8-flash`. Gemini
  never writes data, computes statistics or runs reminders — Python does.
- **Push:** Firebase Cloud Messaging HTTP v1, service-account auth signed with the
  existing PyJWT/cryptography (no Google SDK dependency).
- **Time zones:** per user (IANA names), `tzdata` package for Windows.

## Architecture

Feature-based layout: each feature has `models.py`, `schemas.py`, `repository.py`,
`service.py`, `router.py`.

```
app/
  core/            config, database, security (JWT), redis, gemini (+ gemini_quota),
                   fcm (push), timezones
  common/          shared exceptions (NotFoundError, ValidationError)
  features/
    tasks/         CRUD, Eisenhower matrix, pause/resume
    reminders/     schedule (date range + day selection), reminder times,
                   deliveries, background worker loop
    occurrences/   per-day tracking for recurring tasks
    history/       append-only event log per task
    maintenance/   time-driven changes (overdue, missed, paused days) — worker only
    dashboard/     dashboard, per-task analytics, calendar
    reports/       monthly productivity report
    assistant/     Gemini conversation state machine, dispatcher, reply matcher
    profile/       user settings (time zone)
    notifications/ in-app inbox, device tokens, reminder delivery + push
manual/            hand-run tools: REST walkthrough, live Gemini runs, model
                   benchmark, migration check, Firebase check
```

**Rules that hold everywhere:**
- **Ownership:** every task-scoped call goes through `tasks.service.get_task(db, id,
  user_id)`, which 404s whether a task doesn't exist or isn't yours (existence never
  leaked).
- **Reads only read.** GET endpoints never write (a test spies on SQL across all 17
  read URLs). Time-driven changes are made by the worker.
- **Atomic writes.** Repositories only flush; each public write commits once, so a
  change, its history and its reminder/occurrence side effects are saved together or
  not at all. Exception: the worker's per-delivery claim commits on its own (it's
  what stops two processes sending the same reminder).
- **Time:** absolute moments are stored in UTC; calendar concepts (due dates/times,
  occurrence days, reminder times-of-day, "today") are the owner's local time.

## Data model (tables)

- **`tasks`** — `user_id` (FK auth.users, cascade), `title, description, category
  (recurring|one_time), urgent, important, status (pending|completed|overdue|cancelled|
  paused), due_date, due_time, created_at, updated_at`. DB stores enum names
  (`'PENDING'`), the API uses values (`"pending"`).
- **`reminder_configs`** — one per task: `start_date, end_date` (null = indefinite,
  recurring only), `day_selection_type (every_day|weekdays|weekends|custom_weekdays|
  custom_dates), custom_weekdays, custom_dates`.
- **`reminder_times`** — many per config: `time_of_day` (owner's local clock).
- **`reminder_deliveries`** — one per (time, day): `scheduled_for` (timestamptz, UTC),
  `status (scheduled|sent|cancelled|failed), sent_at`. Unique (time, scheduled_for).
- **`occurrences`** — one per scheduled day of a recurring task: `occurrence_date,
  status (pending|completed|missed|skipped), completed_at`. Unique (task, date).
- **`task_history_events`** — append-only: `event_type (created|field_updated|
  priority_changed|status_changed|reopened|schedule_changed|became_overdue|
  occurrence_missed|paused|resumed), field_name, old_value, new_value, occurred_at`.
- **`user_settings`** — `user_id` (PK), `timezone`.
- **`device_tokens`** — FCM token per installed app: `user_id, token` (unique),
  `platform, created_at, last_seen_at`.
- **`notifications`** — inbox: `user_id, task_id` (set null if task deleted),
  `delivery_id` (unique: one per reminder), `kind, title, body, push_status
  (sent|no_devices|failed|disabled|pending), created_at, read_at`.

## Endpoints (33)

```
POST    /tasks                                  create
GET     /tasks                                  list own tasks
GET     /tasks/matrix?category=                 Eisenhower matrix by quadrant
GET     /tasks/{id}                             get one
PATCH   /tasks/{id}                             partial update (can't pause/unpause)
DELETE  /tasks/{id}
POST    /tasks/{id}/pause                       pending|overdue -> paused
POST    /tasks/{id}/resume                      {due_date?, due_time?}; 409
                                                new_due_date_required if it passed

PUT     /tasks/{id}/reminder-config             set schedule (regenerates everything)
GET     /tasks/{id}/reminder-config
POST    /tasks/{id}/reminder-config/reminder-times
GET     /tasks/{id}/reminder-config/reminder-times
PATCH   /tasks/{id}/reminder-config/reminder-times/{time_id}
DELETE  /tasks/{id}/reminder-config/reminder-times/{time_id}
GET     /tasks/{id}/reminder-config/deliveries  times shown in the user's zone

GET     /tasks/{id}/occurrences                 read-only
PATCH   /tasks/{id}/occurrences/{occ_id}        completed|skipped (pending only)
GET     /tasks/{id}/history                     times shown in the user's zone

GET     /dashboard
GET     /tasks/{id}/analytics
GET     /calendar?view=daily|weekly|monthly&anchor_date=
GET     /reports/monthly?year=&month=

POST    /assistant/message                      {message, input: text|voice}

GET     /me/settings                            {timezone, is_default}
PUT     /me/settings                            {timezone} — re-plans upcoming reminders

POST    /devices                                {token, platform} register a phone
GET     /devices                                token shown as last 8 chars only
DELETE  /devices/{token}                        on logout
GET     /notifications?unread_only=&limit=      inbox, newest first
GET     /notifications/unread-count
POST    /notifications/{id}/read
POST    /notifications/read-all

GET     /health                                 DB, Redis, Gemini model availability
```

All except `/health` require `Authorization: Bearer <supabase-jwt>`. CORS: only
origins in `CORS_ORIGINS` (default none; the Android app is unaffected).

## Key policy decisions

- **Overdue (one-time):** date-only -> overdue from local midnight after the due date
  (the whole day counts as on time); with a due_time -> once that local date+time
  passes. Judged in the owner's zone; set by the worker within ~30 s.
- **Missed (recurring):** a pending day becomes missed once that local day has ended.
- **Paused:** no reminders (future ones removed, the sweep cancels stragglers), never
  overdue, passing recurring days become *skipped* (not missed), excluded from
  completion %. Resuming a one-time task whose due date passed asks for a new date.
- **Completion % "eligible":** excludes skipped days, future days, cancelled and
  paused one-time tasks. Same rule for dashboard, analytics and monthly report.
- **Reminders:** generated 90 days ahead (rolling, extended daily); a reminder more than
  1 hour late (e.g. server was down) is cancelled, not sent; at most 500 per sweep.
- **Due times float with the user:** "17:00" means 17:00 wherever the user is now, like
  reminder times. Changing zone re-plans upcoming reminders; sent ones stay.
- **Daylight saving:** a nonexistent local time fires right after the jump; a repeated
  one fires on its first occurrence.
- **Reopening** (completed -> other) is its own history event, `reopened`.
- **Monthly report:** one-time tasks count in the month of their due date; the matrix
  is a live snapshot.

## Background worker (`app/features/reminders/worker.py`)

Runs inside the API process (FastAPI lifespan). Every 30 s: (1) maintenance —
overdue, missed, paused days skipped, each with its history event, as single SQL
statements judged in each owner's zone; (2) reminder sweep — claim each due delivery
atomically, then deliver (inbox + push) or cancel (task done/paused/cancelled, day
completed/skipped, or stale). Once per UTC day: extend every schedule's 90-day horizon.
Safe with several server processes.

## AI assistant (`app/features/assistant/`)

Text in -> Gemini returns intent JSON -> Pydantic validates against an allowlist ->
Python asks for missing details -> Python asks to confirm -> only on "yes" does the
dispatcher call the SAME services the API uses. Intents: create (one-time or
recurring with schedule), update, delete, complete, change priority, list, stats,
set reminders on an existing task, pause, resume. Yes/no/choice replies (incl. spoken
and Hinglish: "yeah do it", "haan", "nahi", "the second one", "dusra") are matched by
Python without calling Gemini; a reply only confirms if every word is a yes/filler
word ("yes but call it X" is a changed request). Conversation state in Redis.

## Notifications (`app/features/notifications/`, `app/core/fcm.py`)

Each reminder the worker claims -> an inbox entry (always, once per delivery) -> push to
every registered device via FCM. Android: priority HIGH, channel `task_reminders`,
1-hour TTL. Dead tokens removed. Push outcome stored on the entry. Without
`FIREBASE_CREDENTIALS_FILE`, push is off and the inbox still works.

## Testing

- **Automated (pytest): 137 tests**, real Supabase DB + Redis with two dedicated test
  accounts; only Gemini and Google's FCM network are faked. Files: unit logic 34,
  assistant 28, reminders 14, tasks 13, notifications 12, state & history 10, time
  zones 10, Gemini fallback 7, analytics 5, CORS 4. ~75 s.
- **Mutation checks:** for each core guarantee added in Steps 1–5, the protecting test
  was shown to FAIL when the code was deliberately broken, then restored.
- **Manual tools (`manual/`):** `manual_tests.http` (VS Code REST Client walkthrough),
  `gemini_e2e.py` (live Gemini conversations, sets: main 31 steps, `--reworded` 19,
  `--step4` 15, `--force-fallback`), `gemini_model_bench.py`, `check_migrations.py`
  (temporary DB, upgrade -> downgrade -> upgrade, compares schema incl. enum values),
  `check_fcm.py` (validates the real Firebase setup without delivering anything).

---

## History

### Initial build (2026-11-17)

Phase 1 core (task CRUD, categories, priority/status, due date + overdue, reminder
config + times shared by both task types, recurring occurrences, history, Supabase Auth
+ ownership), Phase 2 analytics (matrix, dashboard, per-task analytics, calendar,
monthly report), reminder worker, Redis + Gemini assistant, then pytest (68 tests) and
worker hardening. Recurring tasks briefly had their own `recurring_schedules` table;
it was merged into `reminder_configs` once both task types shared one schedule model,
differing only in completion (whole task vs per day).

### Bugs found and fixed along the way

- Repository functions named `delete`/`update` shadowed the SQLAlchemy imports,
  causing infinite self-recursion (caught twice in `tasks/repository.py`).
- `get_reminder_config`, `get_schedule` (removed) and `update_occurrence` initially had
  no ownership check — any user could read/modify another's by guessing an id. All now
  go through `get_task`.
- JWT `leeway=0` caused intermittent `ImmatureSignatureError` from clock drift -> 10 s.
- Enum types added via `op.add_column` need an explicit `.create()` in the migration.
- Monthly report per-task % used a denominator including future days -> per-task
  eligibility.

### Live testing, assistant hardening, region move, model choice (2026-11-18/19)

**Assistant bugs found by the live runs, fixed with regression tests:**
- Task selection trapped the user ("which one?" forever). Now "no" cancels, an
  out-of-range number re-asks, anything else is a new request.
- Gemini read "make X urgent" as create -> duplicate. Prompt clarified; Python warns
  before creating a task whose exact title exists.
- Task lookup was substring-only. Now: substring, then all key words after removing
  filler and stemming (a vector DB was considered and rejected: overkill for one user's
  task list, adds an AI call and nondeterminism).
- A prompt example matched a test message word for word; replaced, and the
  `--reworded` set guards against it.
- Gemini down/slow -> "The assistant is busy... try again", request kept.
- "no"/"cancel" with nothing pending is answered by rule.

**Latency.** The DB was in Tokyo (~300 ms per round trip; requests make several) ->
list 3.4 s, "yes" 6.5 s, dashboard 9.6 s. Moved to Mumbai: 6 ms; list 0.07 s, "yes"
0.19 s, dashboard 0.23 s; pytest ~15 min -> ~33 s.

**Gemini model.** Benchmarked on the real prompt: `gemini-3.1-flash-lite` 31/32,
median 1.2 s; `gemini-3.5-flash-lite` 30/32, 4.5 s. `gemini-2.5-flash(-lite)` retired
for new users; `gemini-3.8-flash` 20 requests/day free. JSON response mode; all answer
parts joined; timeout 8 s + 1 retry (4 s cut off real answers).

**Tried and removed: hedged requests** — the duplicate won 2 of 13 times and the extra
calls hit the free per-minute quota. Never committed.

**Broken answers retried:** Gemini occasionally sends JSON cut off mid-object with
`finishReason=STOP`; an unusable answer gets one retry.

**Model fallback with quota memory** (`app/core/gemini_quota.py`): a 429/404 marks the
model in Redis (`gemini:exhausted:<model>`) with Google's `retryDelay` as expiry; the
same request moves to the next model; later requests skip it; it returns automatically.
Timeouts/503s never switch models. Fails open if Redis is down. Verified live (a real
per-minute 429 switched 3.1 -> 3.5 and back after 57 s). Accepted trade-offs: 3.5 is
~4x slower; 3.8 Flash scored 0/16 right after its reset and is kept as last resort by
choice (~17 s wait then "busy" if both lite models are exhausted).

### Steps 1–5 (2026-11-19)

**Step 1 — `0473211`: migration rollbacks, status default, CORS.**
- 7 migrations could not be rolled back: `3b75c057dcec` created its foreign key
  unnamed (`drop_constraint(None)`), now named `tasks_user_id_fkey` (the name Postgres
  already used, so existing DBs unchanged); `25fdf7de77ad` created an enum twice on
  rollback; `64070b3e391e`, `5eb63c795857`, `f03b02de7da9`, `1125e38689c2`,
  `bda9ebf29c28` left their enum types behind. Proven with `check_migrations.py`.
- Task status `server_default` used the value (`pending`) instead of the stored name
  (`PENDING`), unlike the other status columns.
- CORS was `*`; now `CORS_ORIGINS` only, no credentials, only the methods/headers used.
- Tests: 89 passed.

**Step 2 — `80abd79`: per-user time zones.** `user_settings` + `GET/PUT /me/settings`
(default `Asia/Kolkata`; names validated against Python and Postgres). All 18
server-clock uses replaced; overdue detection is one SQL statement using each owner's
zone; `reminder_deliveries.scheduled_for` became timestamptz (migration `524dcf696aa4`);
changing zone re-plans reminders; daylight-saving rules as above. Tests use UTC+14 and
UTC-11 zones so dates always differ. Tests: 99 passed; live Gemini 30/30.

**Step 3 — `5b008ac`: reads stop writing; pause/resume; atomic history.** The 12
GET-time writes moved to the worker's maintenance step; automatic `became_overdue` and
`occurrence_missed` events (one SQL statement each, recorded once even with two
workers); pause/resume endpoints with `paused`/`resumed` events and the
new-due-date rule; repositories flush, services commit once (migration
`4187cbe11e04`). Tests: 109 passed (incl. zero SQL writes across 17 GET URLs);
live Gemini 30/30.

**Step 4 — `bab76b7`: assistant features.** Recurring tasks with schedules, reminders
on existing tasks, pause/resume, one-time due times, offer-to-create for reminders on
unknown tasks, `input: voice|text`, rule-based spoken/Hinglish replies. Atomicity fix
before commit: `reminders_service.replace_schedule` saves schedule + times + deliveries
+ occurrences + history in one transaction; a new recurring task and its schedule are
one transaction; failed confirmed actions roll back (regression tests fail mid-save).
Live runs found and fixed: Gemini returns `null` for empty lists; "meditation" didn't
find "meditate" (5-letter shared-prefix match); "remind me to X" read as an existing-task
reminder; "do it" read as option 2. Tests: 125 passed; live Gemini step4 15/15, main
31/31, reworded 19/19.

**Step 5 — `2e7cb41`: notifications.** Inbox, device registration, FCM push from the
worker (migration `2c6bac4cc341`); replaces the log-only stub. Firebase project
`ai-task-manager-cf064` created; key stored in `backend/secrets/` (gitignored);
`check_fcm.py` confirmed Google accepts the key, project and message format. Tests:
137 passed with Firebase enabled. Every commit searched for the real secret values
(DB password, Gemini key, Redis token, test passwords, Firebase key): none present.

## Remaining work

**Needs you:**
- GitHub push: access for `fidarimex-owais` to `Owais-Ml-Dev/AI_Manager` (or push as
  that account). Nothing has been pushed yet: all 12 commits exist only locally.
- Reset the Mumbai database password (it was shared in chat), then update `.env`.
- Pause/delete the old Tokyo Supabase project; then remove its commented-out lines
  from `.env`.

**Android phase (planned, not started):** get the FCM token and `POST /devices` (and
`DELETE` on logout); request the notification permission (Android 13+); create the
`task_reminders` channel; real on-phone delivery test (`check_fcm.py --token <t>
--send`); speech-to-text with Android's recognizer, sending `input: "voice"`; send the
device zone to `PUT /me/settings` at login; add any web origin to `CORS_ORIGINS`.

**Known gaps / limitations:**
- Completing or skipping a recurring *day* is not recorded in task history (overdue,
  missed, paused/resumed and task status changes are).
- Failed pushes are not retried (the inbox entry always exists).
- Overdue/missed appear up to ~30 s after the moment (worker interval).
- The worker runs inside the API process; a deployment must keep at least one API
  process running.
- The assistant can't set `custom_dates` schedules (the API can).
- Gemini free tier: per-minute and daily limits; `gemini-3.8-flash` unreliable as
  last resort; a paid tier would give steadier speed.
- No deployment yet (host near Mumbai to keep latency low).

## Environment / secrets

All gitignored, never committed (verified):
- `backend/.env`: `DATABASE_URL`, `SUPABASE_URL` (not secret), `REDIS_URL`,
  `GEMINI_API_KEY`, optional `GEMINI_MODELS`, `DEFAULT_TIMEZONE`, `CORS_ORIGINS`,
  `FIREBASE_CREDENTIALS_FILE=secrets/firebase-service-account.json`.
- `backend/secrets/firebase-service-account.json`: Firebase private key.
- `backend/.env.test`: pytest accounts + Supabase publishable key.
- `backend/manual/.env`: manual-testing login.

`backend/.env.example` and `backend/manual/.env.example` are templates without real
values.
