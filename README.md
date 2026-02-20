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

复制 `.env.example` 为 `.env`，按需修改其中的变量

## 📝 许可证

本项目采用 [MIT License](LICENSE) 开源

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
