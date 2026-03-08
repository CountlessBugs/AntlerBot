## Summary

Implemented environment-variable-based Mem0 model configuration so the memory store can use dedicated LLM and embedding settings while preserving fallback behavior to the main model and OpenAI defaults.

## Deviations from Plan

- The plan's intermediate commit steps were not followed exactly during implementation; instead, the completed code changes were committed in two final commits covering code and documentation.
- No final follow-up commit was needed because verification passed without additional fixes.

## Key Decisions

- Kept all Mem0 model resolution logic local to `src/agent/memory.py`.
- Matched the fallback pattern used by transcription model settings for Mem0 LLM configuration.
- Defaulted Mem0 embeddings to OpenAI `text-embedding-3-small` while allowing dedicated `MEM0_EMBEDDER_*` overrides.
- Left `config/agent/settings.yaml` unchanged and used `.env`-based configuration only.

## Lessons Learned

- Focused constructor-level tests are enough to validate Mem0 configuration assembly without requiring a live Mem0 backend.
- Keeping provider/model fallback logic in one module makes the behavior easier to verify and document.

## Follow-ups

- None.
