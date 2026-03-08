from tools.sync_mem0_docs import (
    extract_main_text,
    fetch_text,
    should_include_url,
    url_to_filename,
    write_index,
)


def test_fetch_text_sends_user_agent(monkeypatch):
    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request):
        captured["user_agent"] = request.get_header("User-agent")
        return DummyResponse()

    monkeypatch.setattr("tools.sync_mem0_docs.urlopen", fake_urlopen)

    assert fetch_text("https://docs.mem0.ai/sitemap.xml") == "ok"
    assert captured["user_agent"]


def test_include_python_quickstart_url():
    assert should_include_url("https://docs.mem0.ai/open-source/python-quickstart") is True


def test_include_memory_api_url():
    assert (
        should_include_url("https://docs.mem0.ai/api-reference/memory/add-memories")
        is True
    )


def test_include_langgraph_integration_url():
    assert should_include_url("https://docs.mem0.ai/integrations/langgraph") is True


def test_include_platform_mem0_mcp_reference_url():
    assert should_include_url("https://docs.mem0.ai/platform/mem0-mcp") is True


def test_exclude_irrelevant_frontend_url():
    assert should_include_url("https://docs.mem0.ai/integrations/vercel-ai-sdk") is False


def test_exclude_javascript_quickstart_url():
    assert should_include_url("https://docs.mem0.ai/open-source/javascript-quickstart") is False


def test_extract_main_text_starts_at_meaningful_body_content():
    html = """
    <html>
      <body>
        <main>
          <p>Mem0 home page</p>
          <p>Getting Started</p>
          <p>Open Source</p>
          <p>On this page - Prerequisites</p>
          <p>Get started with Mem0's Python SDK in under 5 minutes.</p>
          <h2>Prerequisites</h2>
          <p>Python 3.10 or higher</p>
        </main>
      </body>
    </html>
    """

    text = extract_main_text(html)

    assert text.startswith("Get started with Mem0's Python SDK in under 5 minutes.")
    assert "Mem0 home page" not in text
    assert "On this page - Prerequisites" not in text


def test_url_to_filename_is_stable():
    assert (
        url_to_filename("https://docs.mem0.ai/api-reference/memory/add-memories")
        == "api-reference-memory-add-memories.md"
    )


def test_write_index_includes_file_mapping_and_failures(tmp_path):
    output_path = tmp_path / "INDEX.md"

    write_index(
        output_path=output_path,
        sitemap_url="https://docs.mem0.ai/sitemap.xml",
        generated_at="2026-03-08T12:00:00Z",
        pages=[
            {
                "title": "Python Quickstart",
                "filename": "open-source-python-quickstart.md",
                "url": "https://docs.mem0.ai/open-source/python-quickstart",
            }
        ],
        failures=["https://docs.mem0.ai/api-reference/memory/delete-memory"],
    )

    content = output_path.read_text(encoding="utf-8")

    assert "https://docs.mem0.ai/sitemap.xml" in content
    assert "2026-03-08T12:00:00Z" in content
    assert "open-source-python-quickstart.md" in content
    assert "https://docs.mem0.ai/open-source/python-quickstart" in content
    assert "https://docs.mem0.ai/api-reference/memory/delete-memory" in content
