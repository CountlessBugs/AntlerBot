# Mem0 Documentation Mirror Design

## Goal

Create a repository-local mirror of mem0 documentation that covers only the pages relevant to the `mem0ai` Python package, so the project can reference mem0 usage and API details without depending on live web access.

## Scope

The mirror should:

- live under `docs/frameworks/mem0/`
- store extracted documentation as Markdown
- be reproducible via a local sync script
- prioritize pages relevant to Python SDK usage and memory APIs
- exclude unrelated JavaScript, frontend, and broad platform marketing content

The mirror is intended as a developer-facing reference for implementation work in this repository. It is not intended to be a full offline clone of the mem0 website.

## Directory Layout

```text
AntlerBot/
├─ docs/
│  └─ frameworks/
│     └─ mem0/
│        ├─ INDEX.md
│        └─ *.md
└─ tools/
   └─ sync_mem0_docs.py
```

## Selected Source Categories

The sync process should keep only pages that are strongly related to `mem0ai` Python usage:

1. Python quickstart and open-source Python pages
2. Core memory API reference pages
3. Python-relevant configuration and component pages when they are needed to understand `mem0ai`
4. Python agent/framework integrations that may inform later integration work
5. A very small number of MCP-related reference pages for comparison only

The sync process should exclude:

- JavaScript / TypeScript SDK pages
- frontend-specific integrations
- general platform marketing pages
- cookbook pages unrelated to Python agents
- unrelated product areas that do not help with local `mem0ai` integration

## Sync Strategy

The sync script should:

1. fetch the mem0 sitemap
2. filter URLs through explicit include/exclude rules
3. download each selected page
4. extract readable main content from HTML
5. convert the extracted text to Markdown-like output
6. write stable filenames into `docs/frameworks/mem0/`
7. regenerate `INDEX.md` with page title, local file path, and source URL

## File Naming

Generated files should use stable English slug-based names derived from the source path, for example:

- `open-source-python-quickstart.md`
- `api-reference-memory-add-memories.md`
- `platform-mem0-mcp.md`

This keeps filenames predictable and easy to grep.

## Index Format

`INDEX.md` should include:

- a short explanation of how the mirror is produced
- the selection rules at a high level
- the source sitemap URL
- the generation timestamp
- a table or list mapping local files to source URLs
- a short list of any failed pages if sync was partial

## Error Handling

The script should stay simple:

- continue when one page fails
- record failed URLs in the generated index
- avoid retry loops and heavy recovery logic
- overwrite generated files on rerun

## Verification

A successful sync should be verified by checking that:

1. `docs/frameworks/mem0/` contains Markdown files
2. `INDEX.md` is generated and readable
3. several key pages contain meaningful body content rather than navigation chrome
4. rerunning the script produces stable filenames and does not create duplicate variants

## Non-Goals

This work does not include:

- integrating a documentation MCP server
- mirroring the entire mem0 site
- translating documentation into Chinese
- building runtime memory integration with mem0 yet

## Follow-Up

After this mirror exists, implementation work on the mem0-based memory system can use the local Markdown files as the primary documentation source.
