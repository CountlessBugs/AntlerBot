from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


SITEMAP_URL = "https://docs.mem0.ai/sitemap.xml"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "frameworks" / "mem0"

INCLUDE_PATTERNS = (
    "/open-source/python",
    "/open-source/python-quickstart",
    "/api-reference/memory/",
    "/integrations/langgraph",
    "/integrations/langchain",
    "/open-source/mcp/",
    "/platform/mem0-mcp",
    "/mcp/",
)

EXCLUDE_PATTERNS = (
    "javascript",
    "typescript",
    "vercel-ai-sdk",
    "frontend",
    "react",
    "nextjs",
    "next.js",
    "/js",
    "/ts",
)

NOISE_PATTERNS = (
    "skip to main content",
    "search...",
    "navigation",
    "ask ai",
    "copy",
    "was this page helpful?",
    "suggest edits raise issue",
    "responses are generated using ai and may contain mistakes.",
    "mem0 home page",
    "on this page",
)

START_HINT_PATTERNS = (
    "get started",
    "in this guide",
    "build a personalized",
    "install necessary libraries",
    "prerequisites",
    "overview",
    "from mem0 import",
    "pip install",
)

END_NOISE_PATTERNS = (
    "previous",
    "next",
    "assistant",
)


@dataclass(frozen=True)
class PageResult:
    title: str
    filename: str
    url: str


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 ClaudeCode/1.0"})
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def fetch_sitemap_urls(sitemap_url: str = SITEMAP_URL) -> list[str]:
    xml_text = fetch_text(sitemap_url)
    root = ET.fromstring(xml_text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text.strip() for loc in root.findall("sm:url/sm:loc", namespace) if loc.text]
    return urls


def should_include_url(url: str) -> bool:
    lowered = url.lower()
    if any(pattern in lowered for pattern in EXCLUDE_PATTERNS):
        return False
    return any(pattern in lowered for pattern in INCLUDE_PATTERNS)


def extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "Untitled"
    return collapse_whitespace(unescape(strip_tags(match.group(1)))) or "Untitled"


def extract_main_text(html: str) -> str:
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)

    main_match = re.search(r"<main\b[^>]*>(.*?)</main>", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if main_match:
        content = main_match.group(1)
    else:
        body_match = re.search(r"<body\b[^>]*>(.*?)</body>", cleaned, flags=re.IGNORECASE | re.DOTALL)
        content = body_match.group(1) if body_match else cleaned

    content = re.sub(r"<(nav|header|footer|aside)\b[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"</(h1|h2|h3|h4|h5|h6|p|li|section|article|div|br)>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<li\b[^>]*>", "- ", content, flags=re.IGNORECASE)
    content = unescape(strip_tags(content))

    lines = [collapse_whitespace(line) for line in content.splitlines()]
    lines = [line for line in lines if line]
    lines = [line for line in lines if not is_noise_line(line)]
    lines = trim_noise_boundaries(lines)
    return "\n\n".join(lines)


def is_noise_line(value: str) -> bool:
    lowered = value.lower()
    return any(pattern in lowered for pattern in NOISE_PATTERNS)


def trim_noise_boundaries(lines: list[str]) -> list[str]:
    start_index = 0
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(pattern in lowered for pattern in START_HINT_PATTERNS):
            start_index = index
            break

    trimmed = lines[start_index:]

    end_index = len(trimmed)
    for index, line in enumerate(trimmed):
        lowered = line.lower()
        if any(pattern == lowered for pattern in END_NOISE_PATTERNS):
            end_index = index
            break

    return trimmed[:end_index]


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def url_to_filename(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "index.md"
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return f"{slug}.md"


def write_index(
    output_path: Path,
    sitemap_url: str,
    generated_at: str,
    pages: list[dict] | list[PageResult],
    failures: list[str],
) -> None:
    normalized_pages: list[dict[str, str]] = []
    for page in pages:
        if isinstance(page, PageResult):
            normalized_pages.append(
                {"title": page.title, "filename": page.filename, "url": page.url}
            )
        else:
            normalized_pages.append(page)

    lines = [
        "# Mem0 Documentation Mirror",
        "",
        "## Purpose",
        "",
        "This directory stores a repository-local Markdown mirror of selected mem0 documentation pages that are relevant to the `mem0ai` Python package.",
        "",
        "## Source",
        "",
        f"- Sitemap: `{sitemap_url}`",
        f"- Generated at: `{generated_at}`",
        f"- Selected pages: `{len(normalized_pages)}`",
        "",
        "## Selection Rules",
        "",
        "- Include Python quickstart, open-source Python pages, core memory API pages, Python agent integrations, and a small number of MCP reference pages.",
        "- Exclude JavaScript, TypeScript, frontend SDK, unrelated cookbook, and general marketing pages.",
        "",
        "## File Mapping",
        "",
    ]

    if normalized_pages:
        for page in normalized_pages:
            lines.append(
                f"- [{page['filename']}]({page['filename']}) - {page['title']} - {page['url']}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Failed Pages", ""])
    if failures:
        for failure in failures:
            lines.append(f"- {failure}")
    else:
        lines.append("- None")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_page_markdown(title: str, source_url: str, body: str) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"Source: {source_url}",
            "",
            body.strip(),
            "",
        ]
    )


def sync_mem0_docs() -> tuple[list[PageResult], list[str]]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = fetch_sitemap_urls()
    selected_urls = [url for url in urls if should_include_url(url)]
    pages: list[PageResult] = []
    failures: list[str] = []

    for url in selected_urls:
        try:
            html = fetch_text(url)
            title = extract_title(html)
            body = extract_main_text(html)
            if not body:
                raise ValueError("empty body")
            filename = url_to_filename(url)
            markdown = render_page_markdown(title=title, source_url=url, body=body)
            (OUTPUT_DIR / filename).write_text(markdown, encoding="utf-8")
            pages.append(PageResult(title=title, filename=filename, url=url))
        except Exception:
            failures.append(url)

    write_index(
        output_path=OUTPUT_DIR / "INDEX.md",
        sitemap_url=SITEMAP_URL,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        pages=pages,
        failures=failures,
    )
    return pages, failures


def main() -> None:
    pages, failures = sync_mem0_docs()
    print(f"Synced {len(pages)} pages into {OUTPUT_DIR}")
    print(f"Failed pages: {len(failures)}")


if __name__ == "__main__":
    main()
