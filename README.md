# AntlerBot

一个基于 Python 的 QQ 机器人，通过 NapCat 与 QQ 交互，使用 LangGraph 驱动 LLM 对话回复

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

> 使用非 OpenAI 供应商时，API Key 应设置为对应的环境变量（如 `ANTHROPIC_API_KEY`），`OPENAI_API_KEY` 仅在使用 OpenAI 兼容接口时需要。

编辑 `config/agent/prompt.txt` 设置机器人的系统提示词。

`config/agent/settings.yaml` 控制运行时行为（可选，缺失时使用内置默认值）：

| 字段 | 说明 |
|------|------|
| `context_limit_tokens` | 上下文窗口限制，超过时触发自动摘要 |
| `timeout_summarize_seconds` | 无消息多少秒后触发会话摘要 |
| `timeout_clear_seconds` | 会话摘要后多少秒清空历史 |
| `reply_max_length` | 回复消息引用的最大截断长度 |
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
| 回复 | 异步获取原消息内容，解析为 `<reply>` 标签（受 `reply_max_length` 截断） |
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

## 📝 许可证

本项目采用 [MIT License](LICENSE) 开源

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
