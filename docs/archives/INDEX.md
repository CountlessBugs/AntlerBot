# Archives Index

| 日期 | 归档 | 简介 |
|------|------|------|
| 2026-02-20 | [llm-reply-feature](llm-reply-feature/) | 初始 LLM 回复功能实现 |
| 2026-02-20 | [agent-concurrency-protection](agent-concurrency-protection/) | 用 asyncio.Lock 串行化并发 invoke 调用 |
| 2026-02-20 | [scheduled-tasks](scheduled-tasks/) | APScheduler 定时任务，含 LLM 工具和启动恢复 |
| 2026-02-21 | [scheduler-architecture](scheduler-architecture/) | 提取 scheduler.py，统一队列/优先级/分发逻辑 |
| 2026-02-21 | [auto-summarization](auto-summarization/) | 自动摘要与 session 超时清理 |
| 2026-02-21 | [message-splitting](message-splitting/) | 流式输出按换行拆分为多条 QQ 消息，支持 no-split 标签 |
| 2026-02-22 | [logging-improvements](logging-improvements/) | 为 agent、scheduler、scheduled_tasks 添加结构化 INFO 日志 |
| 2026-02-22 | [sender-name-display](sender-name-display/) | 联系人缓存，改善发送者名称显示（备注、群名片、群备注） |
| 2026-02-23 | [permissions-and-commands](permissions-and-commands/) | 3级权限系统与私聊指令系统，含精确 token 追踪 |
| 2026-02-25 | [message-parsing](message-parsing/) | 消息解析：Phase 1 文本解析 + Phase 2 媒体转述全流程 |
