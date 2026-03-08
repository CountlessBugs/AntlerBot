# Mem0 Model Configuration Design

## Summary

Add dedicated environment variables for configuring the Mem0 LLM and embedder models.

The Mem0 LLM should follow the existing transcription-model pattern: users may override provider/model/API settings in `.env`, and when those values are omitted, Mem0 falls back to the main chat model configuration.

The Mem0 embedder should also support dedicated environment variables, but default to OpenAI's `text-embedding-3-small` when not explicitly configured.

This design intentionally does not add any new `settings.yaml` fields. Mem0 model selection should remain environment-driven.

## Goals

- Allow users to configure the Mem0 LLM independently from the main chat model.
- Preserve a simple default path where Mem0 reuses the main LLM if no Mem0-specific LLM settings are provided.
- Allow advanced users to override the Mem0 embedder.
- Default the Mem0 embedder to OpenAI `text-embedding-3-small`.
- Keep configuration behavior explicit and documented.

## Non-Goals

- Do not add Mem0 model configuration to `config/agent/settings.yaml`.
- Do not introduce a second configuration source beyond environment variables.
- Do not change existing memory behavior outside of model/config initialization.

## Environment Variables

### Mem0 LLM

Add the following optional environment variables:

- `MEM0_LLM_PROVIDER`
- `MEM0_LLM_MODEL`
- `MEM0_LLM_API_KEY`
- `MEM0_LLM_BASE_URL`

Fallback behavior:

- `MEM0_LLM_PROVIDER` → `LLM_PROVIDER`
- `MEM0_LLM_MODEL` → `LLM_MODEL`
- `MEM0_LLM_API_KEY` → main-model API key resolution
- `MEM0_LLM_BASE_URL` → main-model base URL resolution

### Mem0 Embedder

Add the following optional environment variables:

- `MEM0_EMBEDDER_PROVIDER`
- `MEM0_EMBEDDER_MODEL`
- `MEM0_EMBEDDER_API_KEY`
- `MEM0_EMBEDDER_BASE_URL`

Default behavior:

- provider defaults to `openai`
- model defaults to `text-embedding-3-small`
- API key falls back to `OPENAI_API_KEY`
- base URL falls back to `OPENAI_BASE_URL`

## Configuration Semantics

### Mem0 LLM resolution

Mem0 should resolve its LLM configuration in this order:

1. Mem0-specific environment variables
2. Main chat model environment variables

This mirrors the existing transcription-model override pattern, where a dedicated model may be configured but omission means reuse.

### Mem0 embedder resolution

Mem0 should resolve its embedder configuration in this order:

1. Mem0-specific embedder environment variables
2. OpenAI defaults for provider/model/API transport

This keeps the default behavior predictable and aligned with Mem0's common embedding setup.

## Code Changes

Primary implementation target:

- `src/agent/memory.py`

### Initialization change

Replace the current bare `Memory()` initialization with explicit `MemoryConfig` construction and `Memory(config)`.

### Internal helpers

Add small private helpers in `src/agent/memory.py` to:

- read and normalize Mem0-related environment variables
- resolve fallback behavior for Mem0 LLM
- resolve default/fallback behavior for Mem0 embedder
- construct the `MemoryConfig` object in one place

These helpers should remain local to the memory module so that configuration behavior is centralized.

## Documentation Changes

Update:

- `.env.example`
- `README.md`

Documentation should explain:

- Mem0 can use a dedicated LLM configuration
- if omitted, Mem0 reuses the main LLM
- Mem0 embedder defaults to OpenAI `text-embedding-3-small`
- users may override the embedder with dedicated env vars

No `settings.yaml` documentation changes are required.

## Testing

Update `tests/test_memory.py` to cover:

1. Mem0 LLM falls back to the main LLM when `MEM0_LLM_*` is unset
2. Mem0 LLM uses dedicated settings when `MEM0_LLM_*` is set
3. Mem0 embedder defaults to `openai` + `text-embedding-3-small`
4. Mem0 embedder uses dedicated settings when `MEM0_EMBEDDER_*` is set
5. Mem0 embedder API/base URL fallback to `OPENAI_API_KEY` and `OPENAI_BASE_URL`

Tests should verify the effective configuration passed into Mem0 initialization rather than only checking env presence.

## Error Handling

Configuration should be validated when Mem0 is initialized.

If memory is enabled and the resolved Mem0 configuration is incomplete, initialization should fail with a clear error describing the missing requirement.

Validation should stay minimal and focused on required configuration, avoiding extra abstraction or speculative compatibility logic.

## Rationale

This design keeps the common case simple:

- users who do nothing extra get Mem0 powered by the main chat model plus a sensible default embedder
- users who need control can override Mem0 LLM and embedder independently

It also preserves a single, clear source of truth for model selection: environment variables, matching the existing project pattern for model overrides.
