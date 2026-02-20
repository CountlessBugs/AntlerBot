# AntlerBot

一个基于 Python 的 QQ 机器人，通过 NapCat 与 QQ 交互，使用 LangGraph 驱动 LLM 对话回复

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## 依赖管理

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

## 配置

```bash
cp .env.example .env
cp config/agent/prompt.txt.example config/agent/prompt.txt
```

编辑 `.env`：

| 变量 | 说明 |
|------|------|
| `LLM_PROVIDER` | 模型供应商，如 `openai`、`anthropic`、`ollama` |
| `LLM_MODEL` | 模型名称，如 `gpt-4o`、`claude-3-5-sonnet-20241022` |
| `OPENAI_API_KEY` | 对应供应商的 API Key |
| `OPENAI_BASE_URL` | 可选，自定义 API 端点 |

编辑 `config/agent/prompt.txt` 设置机器人的系统提示词。

使用非 OpenAI 供应商时需安装对应包，例如：
```bash
pip install langchain-anthropic   # Anthropic
pip install langchain-ollama      # Ollama
```

## 📝 许可证

本项目采用 [MIT License](LICENSE) 开源

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
