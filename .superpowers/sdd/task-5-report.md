# Task 5 Report: Manual Context Compaction

## Scope

- Backend only.
- No frontend, Core UI, or unrelated docs touched.
- `/compact` now runs a real session compaction flow instead of returning temporary unavailable.

## RED Evidence

### 1. New compaction tests added first

Added:

- `members/writer/backend/tests/test_session_compaction_service.py`
- updated `members/writer/backend/tests/test_writer_app_server_protocol.py`

### 2. First failing run

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_session_compaction_service.py -q
```

Observed failure:

```text
ModuleNotFoundError: No module named 'app.services.session_compaction_service'
```

Interpretation:

- Failure matched the missing Task 5 backend service.
- Test failed for the expected reason before production code existed.

## GREEN Evidence

### Required test run 1

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_session_compaction_service.py -q
```

Result:

```text
3 passed in 2.49s
```

Covered:

- manual compaction persists `session.context_summary`
- compacted ids and retained count are stored in `session.runtime_state["manual_compaction"]`
- future runtime history excludes compacted messages
- runtime history prepends persisted summary as a `system` item
- Core adapter preserves the summary in model-visible system history
- missing session and insufficient history raise clear errors

### Required test run 2

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_app_server_protocol.py -k "command_execute or command_catalog" -q
```

Result:

```text
6 passed, 69 deselected in 1.09s
```

Covered:

- command catalog still exposes `compact`
- command execution returns real `status: compacted`
- `/compact` persists compaction state through app-server command path
- missing session and short history surface clear command errors

### Extra self-check

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_core_kernel_adapter.py -k "tool_and_internal_roles_filtered_from_history" -q
```

Result:

```text
1 passed, 170 deselected in 1.87s
```

Purpose:

- sanity-check that preserving the new summary system history did not break the nearby narrow adapter expectation that still filters non-conversation roles from the helper view used in that test.

## Files Changed

- `members/writer/backend/app/services/session_compaction_service.py`
- `members/writer/backend/app/services/runtime_input_context.py`
- `members/writer/backend/app/core/writer/core_kernel_adapter.py`
- `members/writer/backend/app/services/command_service.py`
- `members/writer/backend/tests/test_session_compaction_service.py`
- `members/writer/backend/tests/test_writer_app_server_protocol.py`

## What Changed

### 1. Added manual compaction service

- loads active user/assistant history
- ignores rolled-back messages
- excludes already compacted message ids on subsequent runs
- requires more than 6 active messages
- summarizes all older messages and retains the latest 6
- stores:
  - `context_summary`
  - `runtime_state["manual_compaction"]["compacted_message_ids"]`
  - `runtime_state["manual_compaction"]["retained_message_ids"]`
  - `runtime_state["manual_compaction"]["retained_message_count"]`
  - `runtime_state["manual_compaction"]["compacted_at"]`
- returns a real command result with `status: compacted`

### 2. Runtime input now uses persisted compaction state

- loads `session.context_summary`
- prepends it as a `system` history item
- removes any message whose id is marked compacted

### 3. Core adapter now keeps system summary history

- no longer drops `system` history entries from supplied runtime history
- keeps system summary blocks while still filtering unsupported roles
- preserves the total 20-entry cap by prioritizing system entries plus the latest conversation items that still fit

### 4. `/compact` command now executes real work

- replaced temporary unavailable placeholder
- uses the real compaction service through existing command execution path

## Self-Review

- Change stayed within the requested backend-only scope.
- No unrelated worktree changes were reverted.
- Logic is intentionally deterministic and minimal; it uses stored messages directly rather than adding model summarization or new schema.
- Repeated compaction is handled by excluding already compacted message ids from future compaction candidates and runtime history.
- Error paths are explicit:
  - missing session -> `Session not found`
  - too little active history -> `Not enough history to compact`

## Concerns

- No blocking concerns from the required verification set.
- The summary is deterministic text assembled from prior messages, not a semantic abstraction layer. That matches the task brief and keeps the implementation simple, but it also means summary quality is bounded by raw transcript quality.

## Review Fix Follow-Up

### Scope

- Fix reviewer findings on deterministic ordering, summary cap safety, and adapter history ordering.
- No schema change, no model summarization, no expansion beyond requested backend files.

### RED Evidence

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_session_compaction_service.py -q
```

Result:

```text
FAILED test_manual_compaction_uses_stable_id_tiebreak_for_identical_timestamps
FAILED test_manual_compaction_fails_when_summary_has_no_room_for_new_entries
2 failed, 3 passed
```

What failed:

- identical `created_at` rows compacted by SQLite row order instead of a stable secondary key
- a full `context_summary` still allowed new messages to be marked compacted even though their summary text could not fit

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_core_kernel_adapter.py -k "system_user_assistant_history_preserves_incoming_order" -q
```

Result:

```text
FAILED TestMultiTurnHistory::test_system_user_assistant_history_preserves_incoming_order
```

What failed:

- allowed history roles were regrouped with `system` first instead of preserving incoming order

### GREEN Evidence

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_session_compaction_service.py -q
```

Result:

```text
5 passed in 2.67s
```

Covered:

- compaction uses `created_at + id` for deterministic selection
- runtime history uses the same stable tie-break
- summary-cap overflow fails clearly before any new messages are marked compacted

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_core_kernel_adapter.py -k "system_user_assistant_history_preserves_incoming_order" -q
```

Result:

```text
1 passed, 171 deselected in 2.45s
```

Covered:

- adapter now keeps incoming order for `system`, `user`, and `assistant`
- unsupported roles remain filtered
- 20-entry cap still applies after filtering

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_app_server_protocol.py -k "command_execute or command_catalog" -q
```

Result:

```text
6 passed, 69 deselected in 1.23s
```

Covered:

- command protocol stays green after deterministic compaction changes
- `/compact` command path still surfaces clear success and error responses

### Fix Summary

- compaction and runtime history now both order by `created_at` plus stable `id`
- summary building now fails with `Not enough summary space to compact history` instead of truncating newly compacted content
- adapter history keeps the filtered incoming order instead of regrouping `system` items

## Re-review Fix: Keep Compaction Summary Visible After History Cap

### Scope

- Fix the adapter-side history cap so persisted compaction summaries remain model-visible.
- Keep unsupported roles filtered.
- Preserve incoming order in the final model history.

### RED Evidence

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_core_kernel_adapter.py -k "system_user_assistant_history_preserves_incoming_order or system_summary_survives_history_cap" -q
```

Result:

```text
.F
FAILED TestMultiTurnHistory::test_system_summary_survives_history_cap
```

What failed:

- adapter took `filtered_history[-20:]`, so the prepended `system` compaction summary disappeared once 20+ later supported entries existed

### GREEN Evidence

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_core_kernel_adapter.py -k "system_user_assistant_history_preserves_incoming_order or system_summary_survives_history_cap" -q
```

Result:

```text
2 passed, 171 deselected in 2.32s
```

Covered:

- `system` summary survives history capping
- remaining capacity is filled with the latest `user` / `assistant` entries
- final selected history preserves incoming order
- unsupported roles remain filtered

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_session_compaction_service.py -q
```

Result:

```text
5 passed in 2.84s
```

Command:

```powershell
py -3.14 -m pytest members\writer\backend\tests\test_writer_app_server_protocol.py -k "command_execute or command_catalog" -q
```

Result:

```text
6 passed, 69 deselected in 1.37s
```

### Fix Summary

- adapter now reserves cap space for `system` history entries first
- latest supported conversation entries fill the remaining slots
- final emitted order matches the incoming filtered order
