# Docker 部署设计

## 背景

AntlerBot 需要在 Docker 中部署，但项目依赖的 NapCat 必须作为独立容器运行，不能与 AntlerBot 打包在同一个容器中。根据 NcatBot 文档，Docker 环境下应使用连接模式，通过 WebSocket 连接外部 NapCat，并开启 `skip_setup: true` 跳过本地 NapCat 安装。

本次部署还需要同时提供 Neo4j 服务，并确保项目运行所需的 `config/`、`data/`、`logs/` 目录以挂载卷形式持久化。

## 目标

提供一套面向生产的 Docker 部署文件，使用户可以：

- 使用 Docker 镜像运行 AntlerBot
- 通过 `docker compose up -d` 启动 AntlerBot 与 Neo4j
- 让 AntlerBot 通过连接模式访问独立运行的 NapCat 容器
- 通过宿主机挂载持久化 `config/`、`data/`、`logs/`
- 让 AntlerBot 在 Docker 内网中访问 Neo4j，而不向宿主机暴露 Neo4j 端口

## 范围

本次设计包含：

- AntlerBot 的生产用 `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `.env.example` 的 Docker 部署变量补充
- 为 Docker 部署调整相关配置文件

本次设计不包含：

- NapCat 容器本身的编排文件
- Kubernetes / Swarm / CI/CD 配置
- 对业务逻辑的额外重构
- 暴露 Neo4j 到宿主机

## 总体架构

部署由两个受当前 compose 管理的服务组成：

### 1. antlerbot

- 由项目内 `Dockerfile` 构建 Python 运行镜像
- 启动命令为项目主程序入口
- 挂载宿主机 `config/`、`data/`、`logs/`
- 通过环境变量读取外部 NapCat 地址与 token
- 通过 Docker 内部网络访问 `neo4j` 服务

### 2. neo4j

- 使用官方 Neo4j 镜像
- 不向宿主机暴露端口
- 通过内部网络向 `antlerbot` 提供 Bolt 服务
- 将 Neo4j 数据与日志持久化到宿主机目录

### 3. napcat（外部）

- 不纳入当前 `docker-compose.yml`
- 必须作为外部独立容器存在
- AntlerBot 通过 NcatBot 连接模式接入其 WebSocket 服务
- AntlerBot 部署前需要保证该外部 NapCat 地址可达

## 配置策略

### 1. 挂载目录

AntlerBot 容器挂载以下宿主机目录：

- `./config:/app/config`
- `./data:/app/data`
- `./logs:/app/logs`

用途如下：

- `config/`：保存 NcatBot 配置、agent 配置、权限配置、任务配置
- `data/`：保存项目运行数据，包括 Mem0 / qdrant 等本地持久化数据
- `logs/`：保存项目日志

Neo4j 额外挂载自己的宿主机子目录，避免和应用数据混杂，例如：

- `./data/neo4j/data:/data`
- `./logs/neo4j:/logs`

## 2. 环境变量与配置文件分工

采用 `.env + 挂载配置目录` 的方式：

### 保留在配置文件中的内容

保留在 `config/agent/settings.yaml` 或 `config/ncatbot.yaml` 中的内容主要是功能和行为配置，例如：

- 长期记忆功能开关
- recall / auto_store / graph 联想行为配置
- media 处理配置
- NcatBot 非敏感默认配置

### 迁移到 `.env` 的内容

敏感信息和部署环境相关地址迁移到 `.env`：

- NapCat WebSocket 地址
- NapCat WebSocket token
- Neo4j URL
- Neo4j username
- Neo4j password
- 其他已有 LLM / provider 密钥继续保留在 `.env`

这样可以避免：

- 将密钥直接提交到仓库
- 在 `settings.yaml` 中写死 Docker 专属地址（如 `neo4j`）
- 本地运行与 Docker 部署相互冲突

## NapCat 连接模式设计

Docker 部署时，NcatBot 必须使用连接模式，而不是本地安装 NapCat。

`config/ncatbot.yaml` 的目标配置形态应满足以下约束：

- 使用 WebSocket 地址连接外部 NapCat
- 使用 token 进行鉴权
- `skip_setup: true`
- 不依赖本地安装 NapCat

典型目标配置如下：

```yaml
adapters:
  - type: napcat
    platform: qq
    enabled: true
    config:
      ws_uri: ws://napcat:3001
      ws_token: your_token
      skip_setup: true
```

在本项目中，`ws_uri` 不应写死为 `napcat`，而应通过环境变量或部署时配置注入，以便对接外部独立容器。

## Neo4j 配置设计

当前 `config/agent/settings.yaml` 中图记忆配置包含：

- `url`
- `username`
- `password`
- `database`

其中：

- `password` 必须迁移出配置文件
- `url` 建议迁移出配置文件，因为 Docker 中不能继续使用 `localhost`
- `username` 一并迁移，保持来源一致
- `database` 可保留在 `settings.yaml` 中，继续作为行为配置的一部分

Docker 部署下，Neo4j URL 的典型值应为：

- `bolt://neo4j:7687`

但该值仍应通过 `.env` 提供，避免写死在仓库默认配置中。

## 容器启动与依赖关系

### antlerbot

- 依赖 `neo4j`
- 启动时读取挂载目录中的配置
- 启动时读取 `.env` 注入的连接参数
- 默认执行项目入口程序

### neo4j

- 由 compose 负责启动
- 使用认证信息初始化数据库
- 不暴露宿主机端口，仅供内部访问

### napcat

- 不属于当前 compose 的启动依赖图
- 由用户在外部单独启动
- 文档中需要明确说明：只有在 AntlerBot 所在网络能够访问该 NapCat 地址时，机器人才能正常工作

## 需要交付的文件

### 1. `Dockerfile`

职责：

- 基于 Python 镜像创建运行环境
- 安装项目依赖
- 复制项目源码
- 设置工作目录与默认启动命令

设计要求：

- 不安装 NapCat
- 兼容挂载 `config/`、`data/`、`logs/`
- 适合作为生产镜像使用

### 2. `.dockerignore`

职责：

- 排除 `.git`、虚拟环境、缓存、测试缓存、日志、运行数据等
- 缩小镜像构建上下文

### 3. `docker-compose.yml`

职责：

- 编排 `antlerbot` 与 `neo4j`
- 加载 `.env`
- 定义挂载卷、网络、启动依赖
- 不暴露 Neo4j 到宿主机

### 4. `.env.example`

职责：

- 提供 Docker 部署所需变量模板
- 明确区分需要用户填写的敏感值和可按默认值使用的连接值

### 5. 配置文件调整

可能涉及：

- `config/ncatbot.yaml`
- `config/agent/settings.yaml`
- 如有需要，也可能涉及配置加载逻辑，以支持环境变量覆盖

## 数据流

### 消息链路

1. 外部 NapCat 容器接收 QQ 消息
2. NapCat 通过 WebSocket 将事件推送给 AntlerBot
3. AntlerBot 经 NcatBot 处理消息事件
4. AntlerBot 在需要图记忆时访问 Neo4j
5. AntlerBot 将本地运行数据写入挂载的 `data/`
6. AntlerBot 将运行日志写入挂载的 `logs/`

### 配置链路

1. Docker Compose 读取 `.env`
2. Compose 将环境变量注入 `antlerbot` / `neo4j`
3. AntlerBot 读取挂载的 `config/` 文件
4. AntlerBot 结合环境变量完成 NapCat 与 Neo4j 的最终连接配置

## 错误处理与运行约束

### NapCat 不可达

若外部 NapCat 地址不可达，AntlerBot 无法连接 QQ 网关。部署文档需要明确：

- 先确认外部 NapCat 已启动
- 再确认 `NAPCAT_WS_URI` 与 token 正确
- 再启动 AntlerBot

### Neo4j 未就绪

即使 `neo4j` 容器已创建，也可能尚未接受连接。部署实现应尽量减少因启动顺序导致的错误，例如：

- 使用基础依赖关系
- 尽量让配置与连接目标稳定
- 必要时在实现中加入适度的容器级健康检查或等待策略

### 本地运行与 Docker 运行共存

设计需要避免把 Docker 专属地址写死进仓库默认配置。否则将导致：

- 本地运行时错误地尝试连接 `neo4j`
- Docker 运行时错误地尝试连接 `localhost`

因此最终实现应以环境变量覆盖机制为主。

## 测试与验收标准

完成后应满足以下验收标准：

1. 可以成功构建 AntlerBot 镜像
2. `docker compose up -d` 能启动 `antlerbot` 和 `neo4j`
3. `antlerbot` 可以读取挂载的 `config/`、`data/`、`logs/`
4. `antlerbot` 的 NcatBot 配置处于连接模式，并启用 `skip_setup: true`
5. `antlerbot` 可以按环境变量配置访问外部 NapCat
6. `antlerbot` 可以通过 `bolt://neo4j:7687` 形式的内网地址访问 Neo4j
7. Neo4j 不向宿主机暴露端口
8. Neo4j 用户名、密码、URL 不再直接写死在 `config/agent/settings.yaml` 中

## 实施边界

为了保持本次工作聚焦，实施阶段只应修改与 Docker 部署直接相关的内容，不做以下扩展：

- 不补充额外的可观测性栈
- 不引入反向代理
- 不引入额外的数据库管理工具
- 不新增与当前部署无关的抽象层

## 推荐实施结论

采用方案 A：

- 使用生产镜像部署 AntlerBot
- 使用 `docker-compose.yml` 编排 AntlerBot 与 Neo4j
- NapCat 作为外部独立容器，由 AntlerBot 通过连接模式接入
- 使用 `.env` 管理 NapCat 与 Neo4j 的地址和凭据
- 使用挂载卷持久化 `config/`、`data/`、`logs/`

该方案最符合当前项目约束，且对生产部署最直接、最清晰。
