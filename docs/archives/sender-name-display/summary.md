## Summary

Added contact caching module (`src/core/contact_cache.py`) to resolve meaningful sender names: private messages use friend remark → nickname; group messages use card (remark) → card → remark → nickname; group display uses group remark → group name.

## Deviations from Plan

- `on_startup` handler takes an `event` parameter (not in plan) to match NcatBot's actual callback signature.

## Key Decisions

- Cache refresh on session timeout placed after `clear_history()` in `_on_session_clear`.
- Field filtering in friend cache prevents storing sensitive data (phone_num, email).

## Lessons Learned

- NcatBot event callbacks receive an event argument even for lifecycle hooks like `on_startup`.

## Follow-ups

- None
