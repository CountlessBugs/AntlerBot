# AntlerBot

一个基于 Python 的 QQ 机器人，通过 NCatBot 与 QQ 交互，使用 LangGraph 驱动 LLM 对话回复, 使用 Mem0 提供长期记忆能力，支持多模态输入、定时任务和权限管理。

## 🚀 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## 🐳 Docker 部署

生产环境 Docker 部署说明见 [docs/deployment/docker.md](docs/deployment/docker.md)。

该方案使用：
- `Dockerfile` 构建 AntlerBot 生产镜像
- `docker-compose.yml` 编排 `antlerbot` 与 `neo4j`
- 外部独立运行的 NapCat 容器，通过连接模式接入

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

### 最小可运行配置

编辑 `.env`，至少填写以下常用项：

| 变量 | 是否常用 | 说明 |
|------|----------|------|
| `LLM_PROVIDER` | 必填 | 模型供应商，如 `openai`、`anthropic`、`ollama` |
| `LLM_MODEL` | 必填 | 模型名称，如 `gpt-5`、`claude-sonnet-4-5`、`deepseek-chat` |
| `OPENAI_API_KEY` | 常见必填 | 对应供应商的 API Key；使用 OpenAI 兼容接口时填写这里 |
| `OPENAI_BASE_URL` | 可选 | 自定义 API 端点 |

> 使用非 OpenAI 供应商时，API Key 应设置为对应的环境变量（如 `ANTHROPIC_API_KEY`）。`OPENAI_API_KEY` 仅在使用 OpenAI 或 OpenAI 兼容接口时需要。

编辑 `config/agent/prompt.txt` 设置机器人的系统提示词。

`config/agent/settings.yaml` 用于控制运行时行为；如果你只是先把机器人跑起来，通常不需要修改大多数字段。

该部分配置仅可实现基本的对话功能。更详细的配置说明、长期记忆和图记忆配置、媒体处理相关配置等请参见高级配置部分。

### 高级配置

以下内容位于独立文档：

- 完整 `.env` 变量说明
- `config/agent/settings.yaml` 全量字段说明
- Mem0 长期记忆配置
- Neo4j 图记忆配置与部署示例
- 媒体处理相关配置

详见 [docs/configuration.md](docs/configuration.md)。

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

项目支持 Mem0 图记忆联想能力。当 `memory.graph` 未启用、图存储不可用，或图初始化失败时，系统会自动回退到纯向量记忆模式。

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
