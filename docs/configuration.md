# 配置说明

本文档汇总 AntlerBot 的完整配置方式。README 中只保留最常用的启动配置；更详细的运行时配置、长期记忆配置和图记忆部署说明统一放在这里。

## 1. 基础启动配置

先复制配置文件：

```bash
cp .env.example .env
cp config/agent/prompt.txt.example config/agent/prompt.txt
```

### 1.1 `.env` 最小可运行配置

要启动机器人，通常至少需要以下配置：

| 变量 | 说明 |
|------|------|
| `NCATBOT_CONFIG_PATH` | NCatBot 配置文件路径，默认是 `config/ncatbot.yaml` |
| `LLM_PROVIDER` | 主模型供应商，如 `openai`、`anthropic`、`ollama` |
| `LLM_MODEL` | 主模型名称 |
| `OPENAI_API_KEY` | 对应供应商的 API Key；使用 OpenAI 兼容接口时填写这里 |
| `OPENAI_BASE_URL` | 可选，自定义 API 端点 |

> 使用非 OpenAI 供应商时，API Key 应设置为对应的环境变量（如 `ANTHROPIC_API_KEY`）。`OPENAI_API_KEY` 仅在使用 OpenAI 或 OpenAI 兼容接口时需要。

### 1.2 完整 `.env` 变量

| 变量 | 说明 |
|------|------|
| `NCATBOT_CONFIG_PATH` | NCatBot 运行配置文件路径 |
| `LLM_PROVIDER` | 主模型供应商，如 `openai`、`anthropic`、`ollama` |
| `LLM_MODEL` | 主模型名称，如 `gpt-5`、`deepseek-chat` |
| `OPENAI_API_KEY` | 主模型 API Key |
| `OPENAI_BASE_URL` | 主模型 API 端点 |
| `TRANSCRIPTION_PROVIDER` | 可选，媒体转录使用的模型供应商；不设则复用 `LLM_PROVIDER` |
| `TRANSCRIPTION_MODEL` | 可选，媒体转录使用的模型名称；不设则复用 `LLM_MODEL` |
| `TRANSCRIPTION_API_KEY` | 可选，媒体转录 API Key；不设则回退到 `OPENAI_API_KEY` |
| `TRANSCRIPTION_BASE_URL` | 可选，媒体转录 API 端点；不设则回退到 `OPENAI_BASE_URL` |
| `MEM0_LLM_PROVIDER` | 可选，Mem0 使用的模型供应商；不设则回退到 `LLM_PROVIDER` |
| `MEM0_LLM_MODEL` | 可选，Mem0 使用的模型名称；不设则回退到 `LLM_MODEL` |
| `MEM0_LLM_API_KEY` | 可选，Mem0 LLM 的 API Key；不设则回退到 `OPENAI_API_KEY` |
| `MEM0_LLM_BASE_URL` | 可选，Mem0 LLM 的 API 端点；不设则回退到 `OPENAI_BASE_URL` |
| `MEM0_EMBEDDER_PROVIDER` | 可选，Mem0 embedding 模型供应商，默认 `openai` |
| `MEM0_EMBEDDER_MODEL` | 可选，Mem0 embedding 模型名称，默认 `text-embedding-3-small` |
| `MEM0_EMBEDDER_API_KEY` | 可选，Mem0 embedding API Key；不设则回退到 `OPENAI_API_KEY` |
| `MEM0_EMBEDDER_BASE_URL` | 可选，Mem0 embedding API 端点；不设则回退到 `OPENAI_BASE_URL` |

### 1.3 `prompt.txt`

编辑 `config/agent/prompt.txt` 以设置机器人的系统提示词。

## 2. `config/agent/settings.yaml`

`config/agent/settings.yaml` 用于控制运行时行为；如果文件缺失，系统会回退到内置默认值。

### 2.1 常用配置

| 字段 | 说明 |
|------|------|
| `temperature` | 模型采样温度 |
| `context_limit_tokens` | 上下文窗口限制，超过时触发自动摘要 |
| `timeout_summarize_seconds` | 无消息多少秒后触发会话摘要 |
| `timeout_clear_seconds` | 会话摘要后多少秒清空历史 |
| `reply_quote_truncate_length` | 回复消息引用的最大截断长度 |
| `memory.enabled` | 是否启用 Mem0 长期记忆 |
| `media.timeout` | 媒体处理超时时间（秒） |
| `media.max_file_size_mb` | 超过此大小的文件直接跳过 |
| `media.transcribe_threshold_mb` | 直传/转录分界阈值（设为 0 始终转录，不设始终直传） |
| `media.sync_process_threshold_mb` | ≤ 此值同步处理，> 此值走异步占位符流程 |
| `media.<类型>.enabled` | 是否处理该类型媒体 |

### 2.2 长期记忆配置

| 字段 | 说明 |
|------|------|
| `memory.agent_id` | Mem0 中用于隔离机器人记忆空间的 `agent_id` |
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

### 2.3 图记忆配置

| 字段 | 说明 |
|------|------|
| `memory.graph.enabled` | 是否启用 Mem0 图记忆联想增强 |
| `memory.graph.provider` | 图存储后端提供者，透传给 Mem0 |
| `memory.graph.config` | 图存储后端配置（如 Neo4j 连接信息），透传给 Mem0 |
| `memory.graph.auto_recall_enabled` | 是否在自动检索时追加图关系联想 |
| `memory.graph.manual_recall_enabled` | 是否在 `recall_memory` 工具中追加图关系联想 |
| `memory.graph.context_max_relations` | 单次注入上下文时最多保留多少条关系联想 |
| `memory.graph.max_hops` | 图联想最大跳数，当前版本仅支持 `1` |
| `memory.graph.context_prefix` | 图关系联想注入到模型前的提示前缀 |

### 2.4 媒体细分配置

| 字段 | 说明 |
|------|------|
| `media.<类型>.enabled` | 是否处理该类型媒体 |
| `media.<类型>.max_duration` | 音频/视频最大时长（秒），超过该时长的媒体将被跳过或裁剪 |
| `media.<类型>.trim_over_limit` | 超时长时是否裁剪（裁剪需要 ffmpeg） |

## 3. Mem0 模型配置回退关系

Mem0 的模型配置方式与转录模型类似：

- 可通过 `MEM0_LLM_*` 单独指定长期记忆使用的 LLM。
- 若未设置，则回退到主模型 `LLM_PROVIDER` / `LLM_MODEL` 及对应连接信息。
- Mem0 embedding 默认使用 `openai` 的 `text-embedding-3-small`。
- 也可通过 `MEM0_EMBEDDER_*` 单独覆盖；若未单独设置连接信息，则回退到 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。

## 4. Neo4j 图数据库搭建

如需启用 Mem0 的图记忆联想能力，推荐优先使用 Docker 部署 Neo4j。

### 4.1 使用 Docker 启动 Neo4j

```bash
docker run -d \
  --name antlerbot-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -v ./data/neo4j:/data \
  neo4j:5.26
```

说明：

- 用户名和密码通过环境变量 `NEO4J_AUTH=neo4j/your-password` 设置，必须与项目配置文件中 `memory.graph.config` 保持一致。
- `7474` 是 Neo4j Browser 的 Web 端口。
- `7687` 是 Bolt 连接端口，AntlerBot 通过它连接图数据库。

### 4.2 验证 Neo4j 是否启动成功

启动后可在浏览器中打开：

- `http://localhost:7474`

### 4.3 在 AntlerBot 中配置图数据库连接

编辑 `config/agent/settings.yaml`：

```yaml
memory:
  graph:
    enabled: true
    provider: "neo4j"
    config:
      url: bolt://localhost:7687
      username: "neo4j"
      password: "your-password"
      database: "neo4j"
```

请确保：

- `username` 与 Docker 启动命令中的 `NEO4J_AUTH` 用户名一致，默认为 `neo4j`。
- `password` 与 Docker 启动命令中的 `NEO4J_AUTH` 密码一致。
- `url` 指向 Neo4j 的 Bolt 地址；默认本机部署通常为 `bolt://localhost:7687`。
- `database` 默认使用 `neo4j`。

### 4.4 启用后的行为说明

当 `memory.graph.enabled: true` 时，系统会在长期记忆检索时附加图关系联想能力。

如果图数据库未启用、不可连接，或初始化失败，系统会自动回退到纯向量记忆模式，不影响基础长期记忆功能。

## 5. 其他配置文件

### 5.1 `config/permissions.yaml`

用于配置三级权限：普通用户 < 开发者 < 管理员。

```yaml
developer:
  - 123456789   # QQ号
admin:
  - 987654321
```

### 5.2 `config/tasks.json`

用于持久化定时任务定义，重启后会自动恢复。
