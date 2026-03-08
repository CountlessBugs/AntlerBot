# Mem0 Documentation Mirror Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a repeatable local documentation mirror for the `mem0ai` Python package by syncing selected mem0 docs pages into repository Markdown files.

**Architecture:** Add a small standalone sync script that fetches the mem0 sitemap, filters Python-relevant URLs, downloads selected pages, extracts readable content, and writes Markdown files plus an index into `docs/frameworks/mem0/`. Keep the implementation dependency-light and deterministic so reruns remain stable.

**Tech Stack:** Python, requests, standard library HTML/text processing, pytest if tests are added

---

### Task 1: Inspect repository conventions for utility scripts and docs placement

**Files:**
- Review: `AGENTS.md`
- Review: `docs/frameworks/`
- Review: `requirements.in`

**Step 1: Confirm the target directories already exist or need creation**

Run: `ls docs && ls docs/frameworks`
Expected: `docs/` exists, `docs/frameworks/` exists.

**Step 2: Confirm no existing mem0 mirror already exists**

Run: `ls docs/frameworks/mem0`
Expected: directory missing or empty.

**Step 3: Do not add new third-party dependencies unless extraction quality clearly requires them**

Implementation note: prefer `requests` only if already available transitively; otherwise use `urllib` from the standard library.

**Step 4: Commit**

```bash
git add docs/plans/mem0-doc-mirror-design.md docs/plans/2026-03-08-mem0-doc-mirror.md
git commit -m "docs: add mem0 doc mirror design and plan"
```

### Task 2: Create the output directory structure and initial index scaffold

**Files:**
- Create: `docs/frameworks/mem0/INDEX.md`

**Step 1: Write the initial placeholder index**

Include sections for:
- purpose
- source site
- selection rules
- generated files
- failed pages

**Step 2: Run a quick read check**

Run: `python - <<'PY'
from pathlib import Path
p = Path('docs/frameworks/mem0/INDEX.md')
print(p.exists(), p.read_text(encoding='utf-8')[:120])
PY`
Expected: file exists and prints the header.

**Step 3: Commit**

```bash
git add docs/frameworks/mem0/INDEX.md
git commit -m "docs: scaffold mem0 mirror directory"
```

### Task 3: Write a failing URL selection test or dry-run assertion

**Files:**
- Create: `tests/test_sync_mem0_docs.py`
- Create: `tools/sync_mem0_docs.py`

**Step 1: Write a focused test for URL filtering behavior**

```python
from tools.sync_mem0_docs import should_include_url


def test_include_python_quickstart_url():
    assert should_include_url("https://docs.mem0.ai/open-source/python-quickstart") is True


def test_exclude_irrelevant_frontend_url():
    assert should_include_url("https://docs.mem0.ai/integrations/vercel-ai-sdk") is False
```

**Step 2: Run the test to verify it fails**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: FAIL because `tools.sync_mem0_docs` or `should_include_url` does not exist yet.

**Step 3: Commit nothing yet**

Wait until implementation exists.

### Task 4: Implement sitemap fetching and URL filtering

**Files:**
- Modify: `tools/sync_mem0_docs.py`
- Test: `tests/test_sync_mem0_docs.py`

**Step 1: Write minimal implementation for URL filtering helpers**

Include:
- `fetch_sitemap_urls()`
- `should_include_url(url: str) -> bool`
- explicit include patterns for Python and memory API pages
- explicit exclude patterns for JS/TS/frontend pages

**Step 2: Keep include/exclude rules readable and data-driven**

Use top-level tuples/lists such as:

```python
INCLUDE_PREFIXES = (...)
EXCLUDE_SUBSTRINGS = (...)
```

**Step 3: Run tests**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: PASS for the filtering tests.

**Step 4: Commit**

```bash
git add tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py
git commit -m "feat: add mem0 doc URL selection"
```

### Task 5: Implement HTML fetching and content extraction

**Files:**
- Modify: `tools/sync_mem0_docs.py`
- Test: `tests/test_sync_mem0_docs.py`

**Step 1: Add a focused extraction test using a tiny HTML fixture string**

```python
from tools.sync_mem0_docs import extract_main_text


def test_extract_main_text_prefers_body_content():
    html = """
    <html><body><nav>Nav</nav><main><h1>Title</h1><p>Hello world</p></main></body></html>
    """
    text = extract_main_text(html)
    assert "Title" in text
    assert "Hello world" in text
```

**Step 2: Run the test to verify failure if helper is not implemented**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: FAIL for missing extraction function.

**Step 3: Implement minimal extraction**

Approach:
- prefer `<main>` content if present
- otherwise fall back to `<body>`
- strip scripts/styles
- collapse extra whitespace
- produce simple Markdown-ish plain text, not perfect semantic conversion

**Step 4: Re-run tests**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py
git commit -m "feat: extract mem0 docs content into markdown text"
```

### Task 6: Implement file naming and index generation

**Files:**
- Modify: `tools/sync_mem0_docs.py`
- Modify: `docs/frameworks/mem0/INDEX.md`
- Test: `tests/test_sync_mem0_docs.py`

**Step 1: Add tests for stable filename generation**

```python
from tools.sync_mem0_docs import url_to_filename


def test_url_to_filename_is_stable():
    assert url_to_filename("https://docs.mem0.ai/api-reference/memory/add-memories") == "api-reference-memory-add-memories.md"
```

**Step 2: Implement deterministic filename generation**

Rules:
- drop domain
- replace `/` with `-`
- strip duplicate separators
- append `.md`
- map homepage-like pages to a readable filename

**Step 3: Implement `write_index(...)`**

Index should include:
- generation timestamp
- selected URLs count
- file-to-URL mapping
- failed URLs list

**Step 4: Run tests**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py docs/frameworks/mem0/INDEX.md
git commit -m "feat: generate mem0 mirror filenames and index"
```

### Task 7: Implement end-to-end sync command

**Files:**
- Modify: `tools/sync_mem0_docs.py`

**Step 1: Add a CLI entrypoint**

Support running:

```bash
python tools/sync_mem0_docs.py
```

**Step 2: End-to-end flow**

The script should:
- fetch sitemap
- filter URLs
- fetch selected pages
- extract text
- write markdown files
- write `INDEX.md`
- print a concise summary

**Step 3: Run the sync**

Run: `python tools/sync_mem0_docs.py`
Expected: several Markdown files appear under `docs/frameworks/mem0/` and the index is updated.

**Step 4: Sanity-check key generated files**

Run: `python - <<'PY'
from pathlib import Path
base = Path('docs/frameworks/mem0')
for name in ['INDEX.md', 'open-source-python-quickstart.md', 'api-reference-memory-add-memories.md']:
    p = base / name
    print(name, p.exists())
    if p.exists():
        print(p.read_text(encoding='utf-8')[:200])
PY`
Expected: files exist where selected and contain readable content.

**Step 5: Commit**

```bash
git add tools/sync_mem0_docs.py docs/frameworks/mem0/
git commit -m "feat: sync mem0 documentation into repository"
```

### Task 8: Verify repeatability and refine selection rules

**Files:**
- Modify: `tools/sync_mem0_docs.py` if needed
- Modify: `docs/frameworks/mem0/INDEX.md` via script output

**Step 1: Re-run the sync script**

Run: `python tools/sync_mem0_docs.py`
Expected: stable filenames, no duplicate variants, deterministic index layout.

**Step 2: Manually inspect the generated page list**

Check whether only Python-relevant pages were included.

**Step 3: If irrelevant pages slipped in, tighten the include/exclude rules**

Prefer simple rule adjustments instead of complex classifiers.

**Step 4: Re-run the tests and sync script**

Run: `pytest tests/test_sync_mem0_docs.py -v && python tools/sync_mem0_docs.py`
Expected: tests pass, output remains stable.

**Step 5: Commit**

```bash
git add tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py docs/frameworks/mem0/
git commit -m "refactor: refine mem0 documentation sync rules"
```

### Task 9: Final verification

**Files:**
- Verify: `tools/sync_mem0_docs.py`
- Verify: `docs/frameworks/mem0/`
- Verify: `tests/test_sync_mem0_docs.py`

**Step 1: Run the targeted test suite**

Run: `pytest tests/test_sync_mem0_docs.py -v`
Expected: PASS.

**Step 2: Run any broader lightweight checks if needed**

Run: `python tools/sync_mem0_docs.py`
Expected: PASS with summary output.

**Step 3: Review git diff**

Run: `git diff -- docs/frameworks/mem0 tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py`
Expected: only the intended mirror script, tests, and generated docs changed.

**Step 4: Commit**

```bash
git add tools/sync_mem0_docs.py tests/test_sync_mem0_docs.py docs/frameworks/mem0/
git commit -m "test: verify mem0 documentation mirror workflow"
```
