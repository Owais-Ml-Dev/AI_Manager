# Assistant Draft Flow

Task requests now follow this boundary:

```text
User text
  -> Gemini structured JSON parser
  -> server-owned assistant draft
  -> deterministic missing-field validation
  -> deterministic duplicate / target matching
  -> Flutter confirmation
  -> deterministic task executor
  -> existing task services / repositories
  -> MongoDB
```

## Gemini responsibilities

Gemini receives only:
- the current user message,
- the current server draft,
- the user's local date/time and timezone.

Gemini does **not** receive the user's task database. It cannot create, update,
delete, complete, or store tasks. It returns JSON constrained by Gemini's
`responseSchema`.

## Backend responsibilities

- stores drafts in `assistant_drafts`,
- expires abandoned drafts after one hour using a MongoDB TTL index,
- determines required/missing fields,
- defaults assistant priority deterministically when the user did not state it,
- finds likely duplicates with MongoDB filters + RapidFuzz,
- finds existing-task targets without Gemini,
- validates the final command with the normal task validators,
- atomically claims a draft before execution so it cannot run twice,
- calls the existing task services and repositories.

## API

### Preview / continue a draft

`POST /api/assistant/task-command/preview`

```json
{
  "message": "Remind me to study every day",
  "timezone": "+05:30",
  "draft_id": "optional-existing-draft-id"
}
```

Possible `status` values:
- `needs_input`
- `needs_target_selection`
- `duplicate_review`
- `ready`

### Select an ambiguous existing task

`POST /api/assistant/task-command/select-target`

```json
{
  "draft_id": "...",
  "task_id": "..."
}
```

### Execute a confirmed draft

`POST /api/assistant/task-command/execute`

```json
{
  "draft_id": "...",
  "confirmed": true,
  "duplicate_decision": "create_new",
  "candidate_id": null
}
```

For a duplicate update, use `duplicate_decision: "update_existing"` and send
one of the server-provided `candidate_id` values.

## New dependency

```text
rapidfuzz>=3.0,<4
```
