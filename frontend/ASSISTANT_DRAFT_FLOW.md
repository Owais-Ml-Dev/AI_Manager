# Assistant Draft UI

The Assistant now keeps only the server `draft_id` while a task request is in
progress.

- Missing values are asked by the backend.
- A short reply such as `14 days` continues the same server draft.
- Ambiguous existing tasks are shown for user selection.
- Possible duplicates show `Create new`, `Update selected existing task`, and
  `Cancel`.
- The execute request sends only the `draft_id` and the user's decision; it no
  longer sends editable command JSON back to the server.
- The Gemini API key is still sent only to the preview/parser request, not to
  execution.
