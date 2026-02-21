## Summary

Added `asyncio.Lock()` to `agent.py` so concurrent `invoke()` calls execute sequentially rather than overlapping.

## Deviations from Plan

None.

## Key Decisions

- Lock is module-level (`_lock`), keeping it simple and avoiding class refactoring.

## Lessons Learned

- Resetting the lock in the test fixture (`reset_agent_state`) is necessary since asyncio locks are not reusable across event loops in some test setups.

## Follow-ups

None.
