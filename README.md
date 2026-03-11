# AntlerBot

一个基于 Python 的 QQ 机器人，通过 NCatBot 与 QQ 交互，使用 LangGraph 驱动 LLM 对话回复, 使用 Mem0 提供长期记忆能力，支持多模态输入、定时任务和权限管理。

## 🚀 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## 📦 依赖管理

本项目使用 [pip-tools](https://github.com/jazzband/pip-tools) 管理依赖：

- `requirements.in`：直接依赖列表（手动维护）
- `requirements.txt`：由 pip-compile 自动生成的完整锁定依赖

**安装依赖：**
```bash
pip install -r requirements.txt
```

**添加/更新依赖：**
```bash
# 1. 编辑 requirements.in，添加新依赖
# 2. 重新生成 requirements.txt
pip-compile --index-url=https://mirrors.aliyun.com/pypi/simple/ --output-file=requirements.txt requirements.in
# 3. 安装新依赖
pip install -r requirements.txt
```

## ⚙️ 配置

```bash
cp .env.example .env
cp config/agent/prompt.txt.example config/agent/prompt.txt
```

编辑 `.env`：

| 变量 | 说明 |
|------|------|
| `LLM_PROVIDER` | 模型供应商，如 `openai`、`anthropic`、`ollama` |
| `LLM_MODEL` | 模型名称，如 `gpt-5`、`deepseek-chat` |
| `OPENAI_API_KEY` | 对应供应商的 API Key |
| `OPENAI_BASE_URL` | 可选，自定义 API 端点 |
| `TRANSCRIPTION_PROVIDER` | 可选，媒体转录使用的模型供应商（不设则复用 `LLM_PROVIDER`） |
| `TRANSCRIPTION_MODEL` | 可选，媒体转录使用的模型名称（不设则复用 `LLM_MODEL`） |
| `TRANSCRIPTION_API_KEY` | 可选，转录模型的 API Key（不设则复用 `OPENAI_API_KEY`） |
| `TRANSCRIPTION_BASE_URL` | 可选，转录模型的 API 端点（不设则复用 `OPENAI_BASE_URL`） |
| `MEM0_LLM_PROVIDER` | 可选，Mem0 使用的模型供应商（不设则回退到 `LLM_PROVIDER`） |
| `MEM0_LLM_MODEL` | 可选，Mem0 使用的模型名称（不设则回退到 `LLM_MODEL`） |
| `MEM0_LLM_API_KEY` | 可选，Mem0 LLM 的 API Key（不设则回退到 `OPENAI_API_KEY`） |
| `MEM0_LLM_BASE_URL` | 可选，Mem0 LLM 的 API 端点（不设则回退到 `OPENAI_BASE_URL`） |
| `MEM0_EMBEDDER_PROVIDER` | 可选，Mem0 embedding 模型供应商（默认 `openai`） |
| `MEM0_EMBEDDER_MODEL` | 可选，Mem0 embedding 模型名称（默认 `text-embedding-3-small`） |
| `MEM0_EMBEDDER_API_KEY` | 可选，Mem0 embedding 的 API Key（不设则回退到 `OPENAI_API_KEY`） |
| `MEM0_EMBEDDER_BASE_URL` | 可选，Mem0 embedding 的 API 端点（不设则回退到 `OPENAI_BASE_URL`） |

> 使用非 OpenAI 供应商时，API Key 应设置为对应的环境变量（如 `ANTHROPIC_API_KEY`），`OPENAI_API_KEY` 仅在使用 OpenAI 兼容接口时需要。
>
> Mem0 的模型配置方式与转录模型类似：可通过 `MEM0_LLM_*` 单独指定长期记忆使用的 LLM；若未设置，则回退到主模型 `LLM_PROVIDER` / `LLM_MODEL` 及对应连接信息。Mem0 embedding 默认使用 `openai` 的 `text-embedding-3-small`，也可通过 `MEM0_EMBEDDER_*` 单独覆盖；若未单独设置连接信息，则回退到 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。

编辑 `config/agent/prompt.txt` 设置机器人的系统提示词。

`config/agent/settings.yaml` 控制运行时行为（可选，缺失时使用内置默认值）：

| 字段 | 说明 |
|------|------|
| `temperature` | 模型采样温度 |
| `context_limit_tokens` | 上下文窗口限制，超过时触发自动摘要 |
| `timeout_summarize_seconds` | 无消息多少秒后触发会话摘要 |
| `timeout_clear_seconds` | 会话摘要后多少秒清空历史 |
| `reply_quote_truncate_length` | 回复消息引用的最大截断长度 |
| `memory.enabled` | 是否启用 Mem0 长期记忆 |
| `memory.agent_id` | Mem0 中用于隔离机器人记忆空间的 agent_id |
| `memory.auto_recall_enabled` | 是否在用户发言前自动检索相关长期记忆（仅作为当前轮临时上下文注入，不写入持久对话历史） |
| `memory.auto_store_enabled` | 是否在摘要后异步写入长期记忆 |
| `memory.auto_recall_query_token_limit` | 自动检索查询窗口的近似 token 上限 |
| `memory.auto_recall_score_threshold` | 自动检索结果的最低相似度阈值 |
| `memory.auto_recall_max_memories` | 自动检索最多注入多少条长期记忆 |
| `memory.auto_recall_system_prefix` | 自动检索注入到模型前的系统提示前缀 |
| `memory.recall_<等级>_score_threshold` | `recall_memory` 工具在对应 effort 下的最低相似度阈值 |
| `memory.recall_<等级>_max_memories` | `recall_memory` 工具在对应 effort 下的最大返回条数 |
| `memory.reset_seen_on_summary` | 摘要或清空上下文后，是否重置本会话内的记忆计数与上下文锁定状态 |
| `memory.vector_store.provider` | 向量存储后端提供者，透传给 Mem0，默认 `qdrant` |
| `memory.vector_store.config` | 向量存储后端配置，默认持久化到 `data/mem0/qdrant` |
| `memory.graph.enabled` | 是否启用 Mem0 图记忆联想增强 |
| `memory.graph.provider` | 图存储后端提供者，透传给 Mem0 |
| `memory.graph.config` | 图存储后端配置（如 Neo4j 连接信息），透传给 Mem0 |
| `memory.graph.auto_recall_enabled` | 是否在自动检索时追加图关系联想 |
| `memory.graph.manual_recall_enabled` | 是否在 `recall_memory` 工具中追加图关系联想 |
| `memory.graph.context_max_relations` | 单次注入上下文时最多保留多少条关系联想 |
| `memory.graph.max_hops` | 图联想最大跳数，当前版本仅支持 `1` |
| `memory.graph.context_prefix` | 图关系联想注入到模型前的提示前缀 |
| `media.timeout` | 媒体处理超时时间（秒） |
| `media.max_file_size_mb` | 超过此大小的文件直接跳过 |
| `media.transcribe_threshold_mb` | 直传/转录分界阈值（设为 0 始终转录，不设始终直传） |
| `media.sync_process_threshold_mb` | ≤ 此值同步处理，> 此值走异步占位符流程 |
| `media.<类型>.enabled` | 是否处理该类型媒体 |
| `media.<类型>.max_duration` | 音频/视频最大时长（秒），超过该时长的媒体将被跳过或裁剪 |
| `media.<类型>.trim_over_limit` | 超时长时是否裁剪（裁剪需要 ffmpeg） |

使用非 OpenAI 供应商时需安装对应包，例如：
```bash
pip install langchain-anthropic   # Anthropic
pip install langchain-ollama      # Ollama
```

## 🔐 权限与指令

在 `config/permissions.yaml` 中配置权限（缺失时自动创建）：

```yaml
developer:
  - 123456789   # QQ号
admin:
  - 987654321
```

三级权限：普通用户 < 开发者 < 管理员。

普通用户无法使用指令。具有权限的用户在私聊中发送 `/` 开头的消息触发指令（不进入 LLM 上下文）：

**开发者指令：**

| 指令 | 说明 |
|------|------|
| `/help` | 列出可用指令或查看指令详情。直接输入"/"等同于"/help" |
| `/token` | 查看当前上下文 token 数量 |
| `/context` | 查看当前上下文 |
| `/prompt` | 查看当前系统提示词 |
| `/raw` | 显示 Agent 上下文中最后一轮对话的原始内容 |
| `/log` | 导出日志文件 |
| `/status` | 显示 Bot 状态 |
| `/tasks` | 查看定时任务列表 |

**管理员指令（含开发者指令）：**

| 指令 | 说明 |
|------|------|
| `/reload` | 重载配置和联系人缓存 |
| `/summarize` | 总结当前上下文 |
| `/clearcontext` | 清空上下文 |

## 💬 消息解析与媒体处理

收到的 QQ 消息会被结构化解析为 LLM 可读的 XML 标签格式，支持以下消息段类型：

| 消息段 | 说明 |
|--------|------|
| 文本 | 直接输出文本内容 |
| @ | 解析为 `<at>` 标签 |
| 表情 | 解析为 `<face>` 标签 |
| 回复 | 异步获取原消息内容，解析为 `<reply>` 标签（受 `reply_quote_truncate_length` 截断） |
| 图片/音频/视频/文件 | 根据媒体配置进行处理 |

### 媒体处理

媒体文件根据 `settings.yaml` 中的 `media` 配置进行处理（详见配置部分），支持两种模式：

- **直传（passthrough）**：文件大小 ≤ `transcribe_threshold_mb` 时，下载并 base64 编码后直接发送给 LLM（多模态输入）
- **转录（transcribe）**：文件大小 > `transcribe_threshold_mb` 时，由单独的 LLM 调用生成文字描述。支持使用不同模型进行转录。

## ⏰ 定时任务

LLM 可通过工具调用创建和取消定时任务，任务持久化存储于 `config/tasks.json`，重启后自动恢复。

支持三种任务类型：

| 类型 | 说明 |
|------|------|
| `once` | 指定时间执行一次 |
| `repeat` | 按 cron 表达式重复执行 |
| `complex_repeat` | 每次执行后由 LLM 决定下次触发时间或取消 |

## 🧠 长期记忆系统

项目使用 Mem0 提供长期记忆能力。

系统目前支持三种长期记忆相关行为：

- **自动检索**：在用户发言前，根据最近一段对话构造查询，自动检索相关长期记忆。
- **异步存储**：在会话摘要生成后，自动将摘要异步写入长期记忆。
- **主动检索工具**：Agent 可通过 `recall_memory` 工具按不同努力程度检索长期记忆。

Mem0 图记忆联想是可选增强能力，继续复用同一个 `recall_memory` 工具与自动检索流程；当 `memory.graph` 未启用、图存储不可用，或图初始化失败时，系统会自动回退到纯向量记忆模式，并继续复用 `memory.vector_store` 中配置的持久化向量库，而不会退回临时 `/tmp/qdrant` 路径。

自动检索到的长期记忆只会作为当前轮的临时系统上下文参与推理，不会写入持久 `_history`；主动调用 `recall_memory` 工具检索到的内容会进入当前对话上下文。

## 🙏 致谢

本项目基于以下优秀的开源项目构建：

- [LangGraph](https://github.com/langchain-ai/langgraph)
- [NapCat](https://github.com/NapNeko/NapCatQQ)
- [NCatBot](https://github.com/ncatbot/ncatbot)
- [Mem0](https://github.com/mem0ai/mem0)

## 📝 许可证

本项目采用 [MIT License](LICENSE) 开源

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
