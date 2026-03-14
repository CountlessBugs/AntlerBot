## Summary

Implemented Mem0 graph memory associations for AntlerBot so both automatic recall and `recall_memory` can combine vector memory hits with relation-based associative context. The final implementation also hardens the runtime with graph preflight checks, vector-only fallback behavior, and a persistent local Qdrant vector store under the project `data` directory.

## Deviations from Plan

- The ignored local `config/agent/settings.yaml` was not committed; tracked changes were limited to agent defaults, the example settings file, README documentation, tests, and runtime code.
- The implementation added vector-store persistence support under `memory.vector_store` because the original fallback path relied on Mem0's temporary default Qdrant path, which reset data across restarts and could fail on Windows file locking.
- A compatibility patch was added for Mem0 Neo4j environments so graph initialization issues fail closed into vector-only mode instead of surfacing as scheduler crashes.

## Key Decisions

- Kept all Mem0 integration logic concentrated in `src/agent/memory.py`, with `src/agent/agent.py` limited to settings defaults and nested settings merge behavior.
- Reused the existing automatic recall path and `recall_memory` tool instead of introducing a separate graph-specific recall tool.
- Formatted graph associations as Chinese `联想关系` lines layered on top of existing `记忆` output so graph recall remains an enhancement, not a separate response mode.
- Enforced `memory.graph.max_hops == 1` and used `memory.graph.context_prefix` directly in both automatic and manual recall output paths.
- Added explicit `memory.vector_store` defaults so local Qdrant state persists under the repository `data/mem0/qdrant` path and the graph fallback path reuses the same vector store configuration.

## Lessons Learned

- Mem0 graph support can fail before query time because of missing provider dependencies or bad provider config, so preflight validation and narrow fallback boundaries are necessary.
- YAML implicit typing can silently coerce graph credentials and database names, so example values for ambiguous strings should be quoted and runtime normalization is still worth testing.
- Mem0's default local Qdrant setup is not suitable for this project on Windows because temporary-path resets and file locks can turn a graph fallback into a startup/runtime failure.

## Follow-ups

- Users still need to install the graph provider dependency set required by their chosen `memory.graph.provider` (for Neo4j this includes `langchain-neo4j`) before enabling graph memory in production.
- Future work could expose additional persistent vector-store backends beyond local Qdrant if the project later needs remote storage or multi-process sharing.
