# Docker 部署

本文档说明如何使用项目内提供的 Docker 文件部署 AntlerBot。

该部署方案包含：
- 一个 `antlerbot` 应用容器
- 一个由 `docker-compose.yml` 管理的 `neo4j` 容器
- 一个**外部独立运行**的 NapCat 容器（不在当前 compose 中）

## 部署约束

当前 Docker 方案遵循以下约束：

- NapCat **不包含**在当前 `docker-compose.yml` 中
- AntlerBot 通过 NcatBot 连接模式接入外部 NapCat
- `skip_setup` 固定为 `true`
- Neo4j 仅在 Docker 内部网络中提供服务，不暴露宿主机端口
- 挂载目录固定包含 `config/`、`data/`、`logs/`

## 目录与文件

本方案使用以下文件：

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `docker/entrypoint.sh`
- `config/ncatbot.docker.yaml.template`
- `.env.example`

## 前提条件

部署前请先确保：

1. 本机已安装 Docker 与 Docker Compose
2. 你已经准备好所需的 LLM API Key
3. 你可以正常启动并登录 NapCat

## 部署总览

推荐按以下顺序操作：

1. 创建 Docker 共享网络
2. 启动 NapCat，并为当前这套 AntlerBot 选择一个唯一容器名
3. 打开 NapCat WebUI，创建 WebSocket 服务器并记录 token
4. 配置 AntlerBot 的 `.env`
5. 构建并启动 AntlerBot + Neo4j
6. 检查容器状态与运行时配置

## 第一步：创建共享网络

NapCat 与 AntlerBot 不在同一个 compose 中时，最稳妥的做法是让它们加入同一个外部 Docker 网络。

先创建共享网络：

```bash
docker network create antlerbot-shared
```

如果网络已存在，Docker 会提示已存在；这种情况下直接继续即可。

## 第二步：启动 NapCat，并设置唯一容器名

### 为什么不能使用随机容器名

如果直接运行 NapCat 而不指定容器名，Docker 可能会生成随机容器名。这样你很难在 AntlerBot 的 `.env` 中稳定填写 `NAPCAT_WS_URI`。

### 为什么也不建议所有实例都写死成同一个名字

如果同一台机器上要部署多套 AntlerBot，那么每套实例对应的 NapCat 容器名都应该是**唯一的**。否则容器名会冲突，也无法让不同 AntlerBot 清楚地区分自己应该连接哪个 NapCat。

因此，推荐做法是：

- 为**当前这套部署**选择一个唯一 NapCat 容器名
- 把这个名字同步写入当前这套 AntlerBot 的 `NAPCAT_WS_URI`

### 启动要求

无论你使用什么方式启动 NapCat，都要满足以下条件：

- 容器加入 `antlerbot-shared` 网络
- 容器名对当前机器来说唯一，例如 `napcat-bot-a`
- NapCat 已正常登录 QQ
- 后续在 WebUI 中创建 WebSocket 服务器

如果你使用 `docker run`，关键点类似这样：

```bash
docker run -d \
  --name napcat-bot-a \
  --network antlerbot-shared \
  ...你的其他 NapCat 参数...
```

如果你使用单独的 NapCat compose，也请确保：

- `container_name: napcat-bot-a`
- `networks:` 中包含 `antlerbot-shared`
- 该网络声明为外部网络

也就是说，AntlerBot `.env` 里的：

```dotenv
NAPCAT_WS_URI=ws://napcat-bot-a:3001
```

其中 `napcat-bot-a` 必须与你当前这套部署实际使用的 NapCat 容器名一致。

如果你为另一套 AntlerBot 部署了另一个 NapCat，例如 `napcat-bot-b`，那另一套 `.env` 就应写成：

```dotenv
NAPCAT_WS_URI=ws://napcat-bot-b:3001
```

## 第三步：在 NapCat WebUI 中创建 WebSocket 服务器

仅仅启动 NapCat 容器还不够。AntlerBot 依赖的是 NapCat 提供的 WebSocket 服务，因此你还需要在 NapCat WebUI 中手动创建 WebSocket 服务器。

推荐按下面流程操作：

1. 打开 NapCat WebUI
2. 确认 NapCat 已登录 QQ
3. 在 WebUI 中打开网络配置界面
4. 新建一个 **WebSocket 服务器**
5. 监听地址建议设为 `0.0.0.0`
6. 监听端口与 AntlerBot 配置保持一致，本文示例使用 `3001`
7. 保存配置
8. 记录该 WebSocket 服务器的 token

这里有两个关键点：

### 1. 监听地址不要用 `127.0.0.1`

如果 WebSocket 服务只监听 `127.0.0.1`，那它只能被 NapCat 容器自己访问，AntlerBot 容器无法连上。

因此应使用：

- `0.0.0.0`

### 2. 必须把 token 回填到 AntlerBot 环境变量

你在 WebUI 中创建 WebSocket 服务器后，会得到一个 token。这个 token 必须写入 AntlerBot 的 `.env`：

```dotenv
NAPCAT_WS_TOKEN=NapCat WebUI 中设置的 token
```

如果 token 不一致，AntlerBot 即使能连到地址，也无法正常接入 NapCat。

## 第四步：配置 AntlerBot 环境变量

先复制 `.env.example`：

```bash
cp .env.example .env
```

然后至少填写以下变量：

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_api_key

NAPCAT_WS_URI=ws://napcat-bot-a:3001
NAPCAT_WS_TOKEN=your_napcat_token

MEM0_GRAPH_NEO4J_URL=bolt://neo4j:7687
NEO4J_AUTH=neo4j/your_neo4j_password
```

说明：

- `NAPCAT_WS_URI` 指向外部 NapCat 容器提供的 WebSocket 地址
- `NAPCAT_WS_URI` 中的主机名必须与当前这套部署使用的 NapCat 容器名一致
- `NAPCAT_WS_TOKEN` 必须与 NapCat WebUI 中创建的 WebSocket 服务器 token 一致
- `MEM0_GRAPH_NEO4J_URL` 在 Docker 部署中通常使用 `bolt://neo4j:7687`
- `NEO4J_AUTH` 同时作为 Neo4j 容器认证配置和 AntlerBot 图记忆连接凭据来源，格式为 `用户名/密码`
- `config/agent/settings.yaml` 中不应再写死 Neo4j 的 URL、用户名、密码，实际连接参数由 `.env` 提供

## 第五步：准备挂载目录与配置文件

Compose 会挂载以下目录：

- `./config:/app/config`
- `./data:/app/data`
- `./logs:/app/logs`

首次部署前请确认这些目录存在并已准备好需要的配置文件。

至少检查：

- `config/agent/prompt.txt`
- `config/agent/settings.yaml`
- `config/ncatbot.docker.yaml.template`

## 第六步：构建并启动 AntlerBot

### 1. 构建镜像

```bash
docker compose build antlerbot
```

### 2. 启动服务

```bash
docker compose up -d
```

### 3. 查看状态

```bash
docker compose ps
```

正常情况下你会看到：

- `neo4j` 处于运行状态
- `antlerbot` 已启动

## 第七步：部署后检查

### 1. 检查共享网络中的容器

```bash
docker network inspect antlerbot-shared
```

重点确认：

- 当前这套部署对应的 NapCat 容器在该网络中
- `antlerbot` 容器在该网络中
- `neo4j` 容器在该网络中

### 2. 检查 AntlerBot 运行时 NcatBot 配置

可以用以下命令检查运行时渲染结果：

```bash
docker compose run --rm --no-deps --entrypoint python antlerbot -c 'from pathlib import Path; print(Path("/tmp/ncatbot.yaml").read_text(encoding="utf-8"))'
```

重点确认：

- `ws_uri` 是否为预期 NapCat 地址
- `ws_token` 是否已注入
- `skip_setup: true` 是否存在
- `remote_mode: true` 是否存在

## NapCat 接入方式说明

Docker 部署下，AntlerBot 不会在容器内安装或启动 NapCat。

容器启动时，`docker/entrypoint.sh` 会基于 `config/ncatbot.docker.yaml.template` 渲染出运行时 NcatBot 配置，并注入：

- `NAPCAT_WS_URI`
- `NAPCAT_WS_TOKEN`

最终配置会使用：

- 连接模式（`remote_mode: true`）
- `skip_setup: true`

这意味着：

- 你必须先确保外部 NapCat 已运行
- AntlerBot 容器必须能访问 `NAPCAT_WS_URI`
- 如果地址或 token 错误，AntlerBot 将无法连接 QQ 网关

## Neo4j 说明

当前 `docker-compose.yml` 会管理 `neo4j` 服务，但**不会**暴露宿主机端口。

也就是说：

- AntlerBot 可以通过 `bolt://neo4j:7687` 在内部网络访问 Neo4j
- 宿主机不会直接暴露 Neo4j Bolt / HTTP 端口

Neo4j 数据与日志默认持久化到：

- `./data/neo4j/data`
- `./logs/neo4j`

## 常见问题

### 1. `env file .env not found`

说明当前目录下缺少 `.env` 文件。

处理方式：

```bash
cp .env.example .env
```

然后补全实际部署变量。

### 2. AntlerBot 无法连接 NapCat

优先检查：

1. NapCat 是否已经启动并登录 QQ
2. NapCat 容器名是否与 `NAPCAT_WS_URI` 中主机名一致
3. NapCat 是否加入了 `antlerbot-shared` 网络
4. WebUI 中是否已经创建 WebSocket 服务器
5. WebSocket 服务是否监听在 `0.0.0.0`
6. `NAPCAT_WS_TOKEN` 是否与 WebUI 中配置一致
7. 端口是否与 `NAPCAT_WS_URI` 一致

### 3. Neo4j 长时间未就绪

优先检查：

1. `NEO4J_AUTH` 是否与 Neo4j 当前实际认证信息一致
2. `data/neo4j/data` 是否存在旧数据导致认证信息不一致
3. 容器日志中是否有数据库初始化失败信息

### 4. 容器内 NcatBot 配置是否正确

可以用以下命令检查运行时渲染结果：

```bash
docker compose run --rm --no-deps --entrypoint python antlerbot -c 'from pathlib import Path; print(Path("/tmp/ncatbot.yaml").read_text(encoding="utf-8"))'
```

重点确认：

- `ws_uri` 是否为预期 NapCat 地址
- `ws_token` 是否已注入
- `skip_setup: true` 是否存在
- `remote_mode: true` 是否存在

## 本地运行兼容性

本次 Docker 部署方案不会把 Docker 专属地址写死到默认运行逻辑中。

- 本地运行仍可继续使用原有方式启动
- Docker 部署所需的 Neo4j 与 NapCat 地址通过 `.env` 注入
- `src/agent/memory.py` 仅在环境变量存在时覆盖图数据库连接配置
