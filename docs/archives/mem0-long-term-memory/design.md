# Mem0-Based Long-Term Memory System Design

## Overview

This document defines the first version of a long-term memory system for AntlerBot using the local OSS Mem0 stack. The goal is to add cross-session memory without disrupting the current conversation flow, queueing model, or short-term history behavior.

Version 1 deliberately keeps the design simple:
- Use Mem0 OSS locally.
- Use a single global memory scope via `agent_id`.
- Rely on Mem0's built-in memory extraction, update, and search behavior as much as possible.
- Do not implement custom reranking, decay, relationship weighting, or graph-based recall in this version.
- Store memories only after summarization is triggered.
- Retrieve memories automatically before each reply and also expose a manual recall tool.

## Goals

- Add persistent long-term memory across conversations.
- Keep the current `_history` and summarization behavior intact.
- Avoid blocking the main scheduler queue on memory persistence.
- Minimize additional logic outside Mem0.
- Keep the design extensible for future metadata, graph memory, and relationship-aware recall.

## Non-Goals

The following are explicitly out of scope for version 1:
- Custom reranking of retrieved memories.
- Custom decay or forgetting formulas.
- Relationship-distance weighting.
- Graph-database-based associative recall.
- Metadata-based search or filtering.
- Per-message long-term memory writes.
- Specialized long-term memory modeling for media content.

## Core Decisions

### Memory backend
- Use local OSS Mem0, not the hosted platform.
- Use a single `agent_id` scope for all long-term memory in version 1.

### Storage strategy
- Do not send raw message history directly to Mem0.
- Reuse the existing summarization trigger.
- After the bot finishes generating a summary, send the summary text to Mem0.
- Mem0 is responsible for extracting, merging, and updating memories from that summary text.
- Memory persistence must run asynchronously and must not block the main queue.

### Retrieval strategy
- Before every reply, automatically run one Mem0 search.
- Retrieval uses a dynamic context window instead of a fixed number of prior messages.
- Retrieved memories are filtered by configurable score threshold and max item count.
- If no memories remain after filtering and deduplication, do not inject any additional `SystemMessage`.
- If memories remain, inject them as one separate `SystemMessage`.

### Metadata
- Version 1 does not store any metadata.
- This avoids incorrect attribution because stored input is summary text, which may cover multiple senders and multiple message types.

### Deduplication
- Track retrieved memory IDs that have already been injected during the current summarization cycle.
- Do not inject the same memory twice within the same cycle.
- Reset the seen-memory set when summarization is triggered.
- Memory IDs are used only for logging and deduplication, not injected into model context.

## Architecture

### Existing components that remain unchanged
- `src/runtime/scheduler.py` remains the centralized queue and sole caller of `agent._invoke`.
- `src/agent/agent.py` continues to manage `_history`, summarization, and the LangGraph flow.
- Existing short-term history and timeout summarization stay in place.

### New memory integration layer
Add a dedicated module, suggested path:
- `src/agent/memory.py`

This module should encapsulate:
1. Mem0 initialization.
2. Automatic retrieval before reply generation.
3. Query window construction and normalization.
4. Manual recall tool behavior.
5. Asynchronous storage after summarization.
6. Seen-memory tracking helpers.

This keeps `src/agent/agent.py` focused on orchestration rather than Mem0 details.

## Retrieval Design

### Automatic retrieval timing
Automatic retrieval runs before each normal reply.

It should execute during the reply path before the main LLM call is made, so any retrieved long-term memory can be injected into the prompt as a separate `SystemMessage`.

### Query window construction
Version 1 uses a dynamic query window:
- Always include the current user message.
- Walk backward through recent history.
- Stop when the accumulated window reaches a configured limit measured with `count_tokens_approximately`.

This is preferred over a fixed three-message window because it handles mixed Chinese/English text more fairly and better adapts to variable message lengths.

### Text normalization for retrieval
Before sending text to Mem0 search:
- Remove XML tags.
- Preserve text inside tags.
- Insert spaces between adjacent preserved segments when needed.
- Collapse repeated whitespace.
- Trim leading and trailing whitespace.

Example:

Input:
`你好<image>一只小猫趴在地上</image>它很可爱`

Normalized query text:
`你好 一只小猫趴在地上 它很可爱`

### Media handling during retrieval
Media handling differs depending on whether the media content has already been turned into text.

Rules:
- If a previous message contains media that has not been converted into text, skip that message when building the retrieval query window.
- If the current user message contains media that has not been converted into text, skip automatic retrieval for this turn.
- If media has already been converted into text, use that text normally as part of the retrieval query.

This avoids querying Mem0 with incomplete or misleading context.

### Retrieval result handling
After calling Mem0 search:
- Filter by the configured automatic-retrieval score threshold.
- Limit results by the configured automatic-retrieval max item count.
- Remove any memory whose ID has already been injected during the current summarization cycle.

If the final list is empty:
- Do not inject any additional `SystemMessage`.

If the final list is non-empty:
- Format the memories into a single long-term-memory `SystemMessage`.

### Retrieval injection format
Injected memories should be presented as a plain system context block without memory IDs.

Example shape:

```text
The following long-term memories may be relevant to the current conversation. Use them only when relevant and do not mechanically repeat them.

- ...
- ...
- ...
```

Memory IDs should instead be written to logs for debugging and traceability.

## Storage Design

### Storage trigger
Long-term memory storage occurs only when the existing summarization flow is triggered.

Version 1 does not store long-term memory on every message and does not add a separate immediate-write path.

### Storage input
The storage input is the summary text already produced by the current summarization mechanism.

The design intentionally avoids sending raw structured messages, XML-tagged message content, or raw media descriptions directly to Mem0. Using summary text reduces noise and lowers the chance that transient media descriptions are incorrectly treated as durable facts.

### Storage execution
Storage must run asynchronously:
- Once summary text is available, launch a background async task.
- The task submits the summary text to Mem0.
- The main queue and reply flow do not wait for completion.
- Successes and failures are logged.

Storage is best-effort only. A storage failure must not break user-visible conversation handling.

## Manual Recall Tool

### Purpose
Provide a tool that the agent can call to actively search long-term memory when needed.

### Inputs
The recall tool accepts:
- Query text.
- Effort level: low, medium, or high.

### Behavior
Each effort level maps to its own retrieval settings:
- Score threshold.
- Maximum number of returned memories.

These settings are separate from automatic retrieval settings.

### Output format
The tool returns a formatted memory block, not raw JSON and not a second-stage summary.

Example shape:

```text
Retrieved the following long-term memories with medium effort:

1. ...
2. ...
3. ...
```

If no matching memories are found:

```text
No long-term memories matched the query.
```

The wording shown to the user-facing model should not include quotation marks around the effort label.

## Configuration

Add a new `memory` section to settings.

Suggested version-1 configuration items:

```yaml
memory:
  enabled: false
  agent_id: antlerbot
  auto_recall_enabled: true
  auto_store_enabled: true
  auto_recall_query_token_limit: 400
  auto_recall_score_threshold: 0.75
  auto_recall_max_memories: 5
  auto_recall_system_prefix: "The following long-term memories may be relevant to the current conversation. Use them only when relevant and do not mechanically repeat them."
  recall_low_score_threshold: 0.85
  recall_low_max_memories: 3
  recall_medium_score_threshold: 0.70
  recall_medium_max_memories: 6
  recall_high_score_threshold: 0.55
  recall_high_max_memories: 10
  reset_seen_on_summary: true
```

The exact defaults can be tuned during implementation, but version 1 should separate automatic retrieval settings from manual recall settings.

## Integration Points

### `src/agent/agent.py`
Expected integration points:
- Initialize memory support during agent setup.
- Before the main LLM invocation for user messages, request an optional retrieval `SystemMessage` from the memory module.
- After summarization completes, hand the resulting summary text to the memory module for asynchronous storage.
- Reset the seen-memory set when summarization is triggered.

### `src/messaging/parser.py` and related message processing
The memory module will depend on already-available parsed/normalized textual content from the existing message pipeline. Any additional helper used for XML stripping and whitespace normalization should be shared rather than duplicated if a suitable helper already exists.

## Error Handling

### Automatic retrieval failure
If Mem0 search fails:
- Log the failure.
- Skip long-term memory injection for that turn.
- Continue normal reply generation.

### Asynchronous storage failure
If Mem0 add fails:
- Log the failure.
- End the background task.
- Do not retry in a way that blocks conversation processing.

### Recall tool failure
If the recall tool fails:
- Return a clear failure message to the model.
- Let the model continue without long-term memory results.

## Logging

Version 1 should log enough information to debug behavior without leaking extra content into model context.

Useful log data includes:
- Whether automatic retrieval was attempted or skipped.
- Why retrieval was skipped.
- Retrieved memory IDs.
- Retrieved scores.
- Which results were removed by thresholding.
- Which results were removed because they were already seen.
- Whether asynchronous storage succeeded or failed.

## Testing Strategy

### Unit tests for memory helpers
Add tests for:
1. XML normalization with whitespace preservation.
2. Dynamic retrieval window construction using approximate token limits.
3. Skipping prior messages with non-textualized media.
4. Skipping automatic retrieval when the current message contains non-textualized media.
5. Threshold filtering and max-count truncation.
6. Seen-memory ID deduplication.
7. Recall effort level mapping.

### Integration tests
Add tests for:
1. Successful automatic retrieval injects one extra `SystemMessage`.
2. Empty retrieval injects no extra `SystemMessage`.
3. Retrieval failure does not break reply generation.
4. Summarization triggers asynchronous Mem0 storage.
5. Storage failure does not block or fail the main flow.
6. Seen-memory IDs reset when summarization is triggered.

## Future Evolution

This design intentionally leaves room for later upgrades, including:
- Reintroducing metadata once the write format becomes more structured.
- User- and group-scoped memory alongside global memory.
- Relationship-aware reranking.
- Custom forgetting or freshness behavior.
- Mem0 graph memory integration.
- More sophisticated media-aware memory extraction.

## Summary

Version 1 integrates Mem0 as a lightweight long-term memory layer for AntlerBot by:
- querying before every reply,
- storing only after summarization,
- keeping storage asynchronous,
- avoiding custom memory ranking logic,
- and preserving the current short-term conversation architecture.

This provides a pragmatic first step that is simple enough to implement safely while leaving clear room for future evolution.
