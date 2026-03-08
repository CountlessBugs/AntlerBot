from tools.sync_mem0_docs import should_include_url


def test_include_python_quickstart_url():
    assert should_include_url("https://docs.mem0.ai/open-source/python-quickstart") is True


def test_exclude_irrelevant_frontend_url():
    assert should_include_url("https://docs.mem0.ai/integrations/vercel-ai-sdk") is False
