import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from langchain_core.messages import HumanMessage, AIMessage
import src.core.commands as commands


@pytest.fixture(autouse=True)
def reset_commands():
    yield


# --- Permission loading ---

def test_load_permissions_returns_roles():
    yaml_content = "admin:\n  - 111\ndeveloper:\n  - 222\n"
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        perms = commands.load_permissions()
    assert perms == {"111": commands.ROLE_ADMIN, "222": commands.ROLE_DEVELOPER}


def test_load_permissions_missing_file():
    with patch("os.path.exists", return_value=False):
        perms = commands.load_permissions()
    assert perms == {}


def test_load_permissions_empty_file():
    with patch("builtins.open", mock_open(read_data="")), \
         patch("os.path.exists", return_value=True):
        perms = commands.load_permissions()
    assert perms == {}


def test_load_permissions_duplicate_takes_lower_role(caplog):
    import logging
    yaml_content = "admin:\n  - 111\ndeveloper:\n  - 111\n"
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         caplog.at_level(logging.WARNING, logger="src.core.commands"):
        perms = commands.load_permissions()
    assert perms["111"] == commands.ROLE_DEVELOPER
    assert any("111" in r.message for r in caplog.records)


def test_get_role_admin():
    yaml_content = "admin:\n  - 111\n"
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        assert commands.get_role("111") == commands.ROLE_ADMIN


def test_get_role_developer():
    yaml_content = "developer:\n  - 222\n"
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        assert commands.get_role("222") == commands.ROLE_DEVELOPER


def test_get_role_unknown_user():
    with patch("os.path.exists", return_value=False):
        assert commands.get_role("999") == commands.ROLE_USER


# --- Command dispatch ---

@pytest.mark.anyio
async def test_handle_command_bare_slash_acts_as_help():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        result = await commands.handle_command("222", "/", api, event)
    assert result is True
    api.post_private_msg.assert_called_once()


@pytest.mark.anyio
async def test_handle_command_not_a_command():
    result = await commands.handle_command("111", "hello", AsyncMock(), AsyncMock())
    assert result is False


@pytest.mark.anyio
async def test_handle_command_normal_user_slash_message():
    """Normal users with / messages → treated as normal text (return False)."""
    with patch("os.path.exists", return_value=False):
        result = await commands.handle_command("999", "/help", AsyncMock(), AsyncMock())
    assert result is False


@pytest.mark.anyio
async def test_handle_command_developer_help():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        result = await commands.handle_command("222", "/help", api, event)
    assert result is True
    api.post_private_msg.assert_called_once()


@pytest.mark.anyio
async def test_handle_command_unknown_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        result = await commands.handle_command("222", "/nonexistent", api, event)
    assert result is True
    api.post_private_msg.assert_called_once()
    assert "未知指令" in api.post_private_msg.call_args[1]["text"]
    assert "/help" in api.post_private_msg.call_args[1]["text"]


@pytest.mark.anyio
async def test_handle_command_insufficient_role():
    """Developer trying admin command → 权限不足."""
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        result = await commands.handle_command("222", "/clearcontext", api, event)
    assert result is True
    assert "权限不足" in api.post_private_msg.call_args[1]["text"]


@pytest.mark.anyio
async def test_handle_command_admin_inherits_developer():
    """Admin can use developer commands."""
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        result = await commands.handle_command("111", "/help", api, event)
    assert result is True
    api.post_private_msg.assert_called_once()


# --- /help detail ---

@pytest.mark.anyio
async def test_help_with_specific_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True):
        await commands.handle_command("222", "/help token", api, event)
    text = api.post_private_msg.call_args[1]["text"]
    assert "token" in text


# --- /token ---

@pytest.mark.anyio
async def test_token_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._current_token_usage = 1234
        await commands.handle_command("222", "/token", api, event)
    text = api.post_private_msg.call_args[1]["text"]
    assert "1234" in text
    assert "估算" not in text


# --- /raw ---

@pytest.mark.anyio
async def test_raw_command_with_history():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._history = [HumanMessage("hi"), AIMessage("hello")]
        await commands.handle_command("222", "/raw", api, event)
    text = api.post_private_msg.call_args[1]["text"]
    assert "hi" in text and "hello" in text


@pytest.mark.anyio
async def test_raw_command_empty_history():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._history = []
        await commands.handle_command("222", "/raw", api, event)
    assert "不存在于上下文" in api.post_private_msg.call_args[1]["text"]


# --- /status ---

@pytest.mark.anyio
async def test_status_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    mock_queue = MagicMock()
    mock_queue.qsize.return_value = 0
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent, \
         patch("src.core.commands.scheduler") as mock_sched, \
         patch("src.core.commands.scheduled_tasks") as mock_tasks:
        mock_agent.has_history.return_value = True
        mock_agent._history = [HumanMessage("hi")]
        mock_tasks._load_tasks.return_value = []
        mock_sched._queue = mock_queue
        mock_sched._apscheduler = None
        await commands.handle_command("222", "/status", api, event)
    api.post_private_msg.assert_called_once()


# --- /tasks ---

@pytest.mark.anyio
async def test_tasks_command_empty():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.scheduled_tasks") as mock_tasks:
        mock_tasks._load_tasks.return_value = []
        await commands.handle_command("222", "/tasks", api, event)
    assert "无活跃任务" in api.post_private_msg.call_args[1]["text"]


@pytest.mark.anyio
async def test_tasks_command_with_tasks():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.scheduled_tasks") as mock_tasks:
        mock_tasks._load_tasks.return_value = [
            {"name": "test_task", "type": "repeat", "trigger": "cron:0 9 * * *", "run_count": 3}
        ]
        await commands.handle_command("222", "/tasks", api, event)
    text = api.post_private_msg.call_args[1]["text"]
    assert "test_task" in text


# --- /context ---

@pytest.mark.anyio
async def test_context_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent, \
         patch("src.core.commands.tempfile") as mock_tmp:
        mock_agent._history = [HumanMessage("hi")]
        mock_tmp.NamedTemporaryFile.return_value.__enter__ = lambda s: s
        mock_tmp.NamedTemporaryFile.return_value.__exit__ = lambda s, *a: None
        mock_tmp.NamedTemporaryFile.return_value.name = "/tmp/ctx.txt"
        mock_tmp.NamedTemporaryFile.return_value.write = MagicMock()
        await commands.handle_command("222", "/context", api, event)
    api.upload_private_file.assert_called_once()


# --- /prompt ---

@pytest.mark.anyio
async def test_prompt_command():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent.PROMPT_PATH = "/fake/prompt.txt"
        await commands.handle_command("222", "/prompt", api, event)
    api.upload_private_file.assert_called_once()


# --- /log ---

@pytest.mark.anyio
async def test_log_command_today():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.isfile", return_value=True):
        await commands.handle_command("222", "/log", api, event)
    api.upload_private_file.assert_called_once()


@pytest.mark.anyio
async def test_log_command_not_found():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.isfile", return_value=False):
        await commands.handle_command("222", "/log 2020-01-01", api, event)
    assert "未找到" in api.post_private_msg.call_args[1]["text"]


# --- /reload ---

@pytest.mark.anyio
async def test_reload_invalid_arg():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent, \
         patch("src.core.commands.contact_cache") as mock_cc:
        mock_agent._graph = "something"
        await commands.handle_command("111", "/reload badarg", api, event)
    assert mock_agent._graph == "something"
    mock_cc.refresh_all.assert_not_called()
    assert "用法" in api.post_private_msg.call_args[1]["text"]

@pytest.mark.anyio
async def test_reload_config():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._graph = "something"
        await commands.handle_command("111", "/reload config", api, event)
        assert mock_agent._graph is None


@pytest.mark.anyio
async def test_reload_contact():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.contact_cache") as mock_cc:
        await commands.handle_command("111", "/reload contact", api, event)
    mock_cc.refresh_all.assert_called_once()


# --- /summarize ---

@pytest.mark.anyio
async def test_summarize_command():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111

    async def fake_invoke(*a, **kw):
        yield "done"

    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._history = [HumanMessage("x")]
        mock_agent._invoke = fake_invoke
        await commands.handle_command("111", "/summarize", api, event)
    api.post_private_msg.assert_called_once()


# --- /clear_context ---

@pytest.mark.anyio
async def test_clear_context_command():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        await commands.handle_command("111", "/clearcontext", api, event)
    mock_agent.clear_history.assert_called_once()


# --- /context empty ---

@pytest.mark.anyio
async def test_context_command_empty_history():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._history = []
        await commands.handle_command("222", "/context", api, event)
    api.post_private_msg.assert_called_once()
    assert "无内容" in api.post_private_msg.call_args[1]["text"]


# --- /context type name format ---

@pytest.mark.anyio
async def test_context_command_type_names():
    yaml_content = "developer:\n  - 222\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 222
    written = []
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent, \
         patch("src.core.commands.tempfile") as mock_tmp:
        mock_agent._history = [HumanMessage("hi"), AIMessage("hello")]
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: s
        mock_file.__exit__ = lambda s, *a: None
        mock_file.name = "/tmp/ctx.txt"
        mock_file.write = lambda t: written.append(t)
        mock_tmp.NamedTemporaryFile.return_value = mock_file
        await commands.handle_command("222", "/context", api, event)
    content = "".join(written)
    assert "Message" not in content
    assert "[Human]" in content or "[AI]" in content


# --- /reload no args ---

@pytest.mark.anyio
async def test_reload_no_args():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent, \
         patch("src.core.commands.contact_cache") as mock_cc:
        mock_agent._graph = "something"
        await commands.handle_command("111", "/reload", api, event)
        assert mock_agent._graph is None
    mock_cc.refresh_all.assert_called_once()


# --- /summarize empty history ---

@pytest.mark.anyio
async def test_summarize_command_empty_history():
    yaml_content = "admin:\n  - 111\n"
    api = AsyncMock()
    event = AsyncMock()
    event.user_id = 111
    with patch("builtins.open", mock_open(read_data=yaml_content)), \
         patch("os.path.exists", return_value=True), \
         patch("src.core.commands.agent") as mock_agent:
        mock_agent._history = []
        await commands.handle_command("111", "/summarize", api, event)
    text = api.post_private_msg.call_args[1]["text"]
    assert "上下文为空" in text
