## Summary

Implemented a 3-tier permission system and private-chat command system with 14 commands (developer/admin levels), followed by bug fixes and precise token tracking.

## Deviations from Plan

- `/token` changed to track `_current_token_usage` (context token count) precisely instead of estimating
- `/clear_context` renamed to `/clearcontext` (no underscore)
- Added `_current_token_usage` module variable updated after each LLM call; summarize nodes use `output + (prev - input)` formula
- Added duplicate UID detection: when a UID appears in multiple roles in permissions.yaml, the lower role is kept with a warning logged

## Key Decisions

- Permissions file re-read on every command check — no restart needed
- Duplicate UIDs take the lower role (safer)
- `_current_token_usage` updated only for history-modifying reasons (allowlist: user_message, scheduled_task); complex_reschedule excluded
- Summarize node token formula: `output_tokens + (prev - input_tokens)` — summarization calls don't include the system prompt, so input_tokens equals the size of the context being summarized

## Lessons Learned

- `summarize_node` routes `summarize → END`, bypassing `finalize`, so token updates must happen inside the node itself
- On Windows, `NamedTemporaryFile` encoding can be overridden by system locale; `utf-8-sig` is more reliable
- QQ client inline preview decodes with GBK — emoji garbling cannot be fixed at the file encoding level

## Follow-ups

- QQ inline preview emoji garbling is a QQ client limitation with no workaround
