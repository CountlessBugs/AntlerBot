# LLM Reply Feature — Summary

## 实现内容

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/core/agent.py` | LangGraph 工作流、LLM 初始化、共享历史、`load_prompt()` |
| `src/core/message_handler.py` | 消息格式化、优先级批处理队列、NcatBot 回调注册 |
| `src/core/__init__.py`, `src/__init__.py` | 包文件 |
| `config/agent/prompt.txt.example` | 系统提示词示例 |
| `tests/test_agent.py` | agent 模块测试（8 个） |
| `tests/test_message_handler.py` | message_handler 模块测试（12 个） |

### 修改文件

- `main.py` — 使用 `register(bot)` 注册回调
- `.env.example` — 新增 `LLM_PROVIDER`、`LLM_MODEL`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`
- `.gitignore` — 新增 `config/agent/prompt.txt`
- `CLAUDE.md` — 更新项目状态和结构说明
- `README.md` — 新增配置说明

---

## 关键设计决策

**优先级批处理**：`_batch_pending` 将当前正在处理的消息来源（`_current_source`）排在最前，其余来源按首次出现顺序分组。同一来源的多条消息合并为一次 LLM 调用。

**共享历史**：所有来源（群聊、私聊）共用一个 `_history` 列表，体现"单一对话上下文"的设计意图。

**`invoke()` 不加锁**：处理循环 `_process_loop` 串行执行，`invoke()` 不会并发调用，因此无需 `asyncio.Lock` 保护历史记录。这是有意的设计，不是遗漏。

**供应商包友好报错**：`init_chat_model` 抛出 `ImportError` 时，捕获并重新抛出带有 `pip install <package>` 提示的错误，覆盖 11 个常见供应商。

---

## 代码审查发现的问题

### 已修复

1. **`PROMPT_PATH` 相对路径**（Critical）
   原来使用 `"config/agent/prompt.txt"`，相对于进程 cwd 解析。从非项目根目录启动时会在错误位置创建文件。
   → 改为 `os.path.join(os.path.dirname(__file__), ...)` 锚定到文件位置。

2. **缺少环境变量时报 `KeyError`**（Critical）
   用户忘记配置 `.env` 时看到裸 `KeyError: 'LLM_PROVIDER'`，不知所措。
   → 改为 `RuntimeError("LLM_PROVIDER is not set. Copy .env.example to .env and configure it.")`。

3. **`globals()["_processing"] = True` 作用域问题**（Critical）
   `on_group`/`on_private` 是 `register()` 内的闭包，没有 `global _processing` 声明，用 `globals()` 写入不规范，重构时容易出错。
   → 提取模块级 `_enqueue()` 函数，正确声明 `global _processing`，回调简化为 `await _enqueue(...)`。

### 未修复（有意忽略）

- **`invoke()` 并发安全**：审查建议加锁，但项目设计保证串行调用，无需修改。
- **`_group_name_cache` 无限增长**：已知限制，当前规模下不是问题。

---

## 经验总结

- **TDD 有效捕获接口设计问题**：先写测试迫使明确 `_batch_pending` 的返回结构，避免了实现后再调整接口。
- **代码审查值得做**：三个 Critical 问题（路径、环境变量、作用域）都是实现时未注意到的，审查后一次性修复比上线后排查省力得多。
- **`globals()` 是代码异味**：在闭包中修改模块级变量时，提取为模块级函数是正确做法，不要用 `globals()` 绕过作用域规则。
- **友好的错误信息是功能**：`ImportError` 和 `RuntimeError` 的提示信息直接决定用户能否自助解决配置问题，值得认真对待。
