# Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production Docker deployment for AntlerBot that runs the app in its own image, runs Neo4j in the same compose stack, and connects to an externally managed NapCat container via WebSocket connection mode.

**Architecture:** Keep local development defaults intact while adding a Docker-specific runtime path. The app image will start through a small entrypoint that renders a Docker NCatBot config from environment variables, and the Python memory layer will read Neo4j connection overrides from environment variables instead of hard-coded secrets in `settings.yaml`. Compose will mount `config/`, `data/`, and `logs/`, run Neo4j on the internal Docker network only, and inject all deployment-specific connection values from `.env`.

**Tech Stack:** Docker, Docker Compose, Python 3.12, python-dotenv, PyYAML, Neo4j official image, pytest

---

## File Map

**Create:**
- `Dockerfile` — production image for AntlerBot
- `.dockerignore` — exclude repo state and runtime data from build context
- `docker-compose.yml` — compose stack for `antlerbot` + `neo4j`
- `docker/entrypoint.sh` — render Docker NCatBot config then start app
- `config/ncatbot.docker.yaml.template` — Docker-specific NCatBot config template using env placeholders
- `tests/test_docker_artifacts.py` — validate Docker artifacts and template wiring

**Modify:**
- `.env.example:1-23` — add Docker/NapCat/Neo4j environment variables
- `config/agent/settings.yaml:50-77` — remove checked-in Neo4j credentials and leave graph behavior config only
- `src/agent/memory.py:87-95,205-247` — add env override resolution for Neo4j graph store config

**Test:**
- `tests/test_memory.py` — cover env override behavior for graph config
- `tests/test_docker_artifacts.py` — cover Dockerfile/compose/template/entrypoint expectations

---

### Task 1: Add failing tests for Docker deployment artifacts and Neo4j env overrides

**Files:**
- Create: `tests/test_docker_artifacts.py`
- Modify: `tests/test_memory.py:430-543`
- Test: `tests/test_memory.py`
- Test: `tests/test_docker_artifacts.py`

- [ ] **Step 1: Write the failing Neo4j env override test in `tests/test_memory.py`**

```python
def test_resolve_graph_store_config_prefers_env_over_yaml(monkeypatch):
    settings = {
        "memory": {
            "graph": {
                "enabled": True,
                "provider": "neo4j",
                "config": {
                    "url": "bolt://localhost:7687",
                    "username": "neo4j",
                    "password": "from-settings",
                    "database": "neo4j",
                },
            }
        }
    }

    monkeypatch.setenv("MEM0_GRAPH_NEO4J_URL", "bolt://neo4j:7687")
    monkeypatch.setenv("MEM0_GRAPH_NEO4J_USERNAME", "graph-user")
    monkeypatch.setenv("MEM0_GRAPH_NEO4J_PASSWORD", "graph-pass")
    monkeypatch.setattr(memory, "_verify_graph_connectivity", lambda provider, config: None)

    with patch("importlib.import_module", return_value=SimpleNamespace()):
        graph_store = memory._resolve_graph_store_config(settings)

    assert graph_store == {
        "provider": "neo4j",
        "config": {
            "url": "bolt://neo4j:7687",
            "username": "graph-user",
            "password": "graph-pass",
            "database": "neo4j",
        },
    }
```

- [ ] **Step 2: Write the failing Docker artifact tests in `tests/test_docker_artifacts.py`**

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_mounts_required_directories_and_hides_neo4j_ports():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    antlerbot = compose["services"]["antlerbot"]
    neo4j = compose["services"]["neo4j"]

    assert "./config:/app/config" in antlerbot["volumes"]
    assert "./data:/app/data" in antlerbot["volumes"]
    assert "./logs:/app/logs" in antlerbot["volumes"]
    assert "ports" not in neo4j


def test_docker_compose_injects_napcat_and_neo4j_environment():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    antlerbot_env = compose["services"]["antlerbot"]["environment"]
    neo4j_env = compose["services"]["neo4j"]["environment"]

    assert antlerbot_env["NAPCAT_WS_URI"] == "${NAPCAT_WS_URI}"
    assert antlerbot_env["NAPCAT_WS_TOKEN"] == "${NAPCAT_WS_TOKEN}"
    assert antlerbot_env["MEM0_GRAPH_NEO4J_URL"] == "${MEM0_GRAPH_NEO4J_URL}"
    assert neo4j_env["NEO4J_AUTH"] == "${NEO4J_AUTH}"


def test_ncatbot_docker_template_uses_connection_mode():
    template = (ROOT / "config" / "ncatbot.docker.yaml.template").read_text(encoding="utf-8")

    assert "ws_uri: ${NAPCAT_WS_URI}" in template
    assert "ws_token: ${NAPCAT_WS_TOKEN}" in template
    assert "skip_setup: true" in template


def test_dockerfile_uses_entrypoint_script():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'COPY docker/entrypoint.sh /app/docker/entrypoint.sh' in dockerfile
    assert 'ENTRYPOINT ["/app/docker/entrypoint.sh"]' in dockerfile
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:
```bash
pytest tests/test_memory.py -k graph_store -v
pytest tests/test_docker_artifacts.py -v
```

Expected:
- `tests/test_memory.py` fails because env override behavior is not implemented yet.
- `tests/test_docker_artifacts.py` fails because the Docker files do not exist yet.

- [ ] **Step 4: Commit the failing test baseline**

```bash
git add tests/test_memory.py tests/test_docker_artifacts.py
git commit -m "test: define docker deployment expectations"
```

---

### Task 2: Implement Neo4j environment override support for graph memory config

**Files:**
- Modify: `src/agent/memory.py:87-95,205-247`
- Modify: `config/agent/settings.yaml:50-77`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Implement env override helpers in `src/agent/memory.py`**

Update the env helper section to add graph-specific overlay logic:

```python
def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _apply_graph_env_overrides(config: dict) -> dict:
    return {
        **config,
        "url": _get_env("MEM0_GRAPH_NEO4J_URL") or config.get("url"),
        "username": _get_env("MEM0_GRAPH_NEO4J_USERNAME") or config.get("username"),
        "password": _get_env("MEM0_GRAPH_NEO4J_PASSWORD") or config.get("password"),
    }
```

- [ ] **Step 2: Apply the overlay inside `_resolve_graph_store_config`**

Replace the config construction at `src/agent/memory.py:214-247` with:

```python
def _resolve_graph_store_config(settings: dict) -> dict | None:
    graph_settings = settings.get("memory", {}).get("graph", {})
    if not graph_settings.get("enabled"):
        return None

    max_hops = graph_settings.get("max_hops", 1)
    if max_hops != 1:
        raise RuntimeError("memory.graph.max_hops currently only supports value 1.")

    provider = graph_settings.get("provider", "neo4j")
    config = {
        key: str(value) if value is not None and not isinstance(value, str) else value
        for key, value in dict(graph_settings.get("config", {})).items()
    }
    if provider in {"neo4j", "memgraph"}:
        config = _apply_graph_env_overrides(config)

    required_fields_by_provider = {
        "neo4j": ("url", "username", "password"),
        "memgraph": ("url", "username", "password"),
    }
    provider_graph_modules = {
        "neo4j": "mem0.memory.graph_memory",
        "memgraph": "mem0.memory.graph_memory",
    }
    missing_fields = [field for field in required_fields_by_provider.get(provider, ()) if not config.get(field)]
    if missing_fields:
        raise RuntimeError(
            f"memory.graph.config missing required fields for {provider}: {', '.join(missing_fields)}"
        )

    graph_module = provider_graph_modules.get(provider)
    if graph_module is not None:
        try:
            importlib.import_module(graph_module)
            _patch_mem0_neo4jgraph_signature_compat()
            _verify_graph_connectivity(provider, config)
        except Exception as exc:
            raise RuntimeError(
                f"memory.graph provider '{provider}' is unavailable or unreachable"
            ) from exc

    return {
        "provider": provider,
        "config": config,
    }
```

- [ ] **Step 3: Remove checked-in Neo4j secrets from `config/agent/settings.yaml`**

Replace the graph config block with:

```yaml
  graph:
    enabled: false
    provider: "neo4j"
    config:
      url: ""
      username: ""
      password: ""
      database: "neo4j"
```

Keep the remaining behavior fields (`auto_recall_enabled`, `manual_recall_enabled`, `context_max_relations`, `max_hops`, `context_prefix`) unchanged below this block.

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:
```bash
pytest tests/test_memory.py -k graph_store -v
```

Expected:
- Existing graph store tests still pass.
- The new env override test passes.

- [ ] **Step 5: Commit the config override implementation**

```bash
git add src/agent/memory.py config/agent/settings.yaml tests/test_memory.py
git commit -m "fix: load neo4j graph config from environment"
```

---

### Task 3: Add production Docker runtime files for AntlerBot and Neo4j

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `docker-compose.yml`
- Create: `docker/entrypoint.sh`
- Create: `config/ncatbot.docker.yaml.template`
- Modify: `.env.example:1-23`
- Test: `tests/test_docker_artifacts.py`

- [ ] **Step 1: Create `.dockerignore`**

```dockerignore
.git
.claude
.venv
__pycache__/
.pytest_cache/
*.pyc
*.pyo
*.pyd
*.log
.env
config/
data/
logs/
napcat/
ncatbot_plugins/
```

- [ ] **Step 2: Create the production `Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
```

- [ ] **Step 3: Create `config/ncatbot.docker.yaml.template`**

```yaml
root: '248296719'
bt_uin: '1413080999'
enable_webui_interaction: false
debug: false
github_proxy: null
check_ncatbot_update: true
skip_ncatbot_install_check: false
websocket_timeout: 15
napcat:
  ws_uri: ${NAPCAT_WS_URI}
  ws_token: ${NAPCAT_WS_TOKEN}
  ws_listen_ip: localhost
  webui_uri: http://localhost:6099
  webui_token: ""
  enable_webui: false
  check_napcat_update: false
  stop_napcat: false
  remote_mode: true
  report_self_message: false
  report_forward_message_detail: true
plugin:
  plugins_dir: ncatbot_plugins
  plugin_whitelist: []
  plugin_blacklist: []
  skip_plugin_load: false
```

- [ ] **Step 4: Create `docker/entrypoint.sh` to render config and start the app**

```bash
#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import os
from pathlib import Path

template_path = Path("/app/config/ncatbot.docker.yaml.template")
output_path = Path("/tmp/ncatbot.yaml")
content = template_path.read_text(encoding="utf-8")
for name in ("NAPCAT_WS_URI", "NAPCAT_WS_TOKEN"):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    content = content.replace(f"${{{name}}}", value)
output_path.write_text(content, encoding="utf-8")
PY

export NCATBOT_CONFIG_PATH=/tmp/ncatbot.yaml
exec python main.py
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
services:
  neo4j:
    image: neo4j:5-community
    restart: unless-stopped
    environment:
      NEO4J_AUTH: ${NEO4J_AUTH}
    volumes:
      - ./data/neo4j/data:/data
      - ./logs/neo4j:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p \"${NEO4J_PASSWORD}\" 'RETURN 1;' || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 20

  antlerbot:
    build:
      context: .
    restart: unless-stopped
    depends_on:
      neo4j:
        condition: service_healthy
    env_file:
      - .env
    environment:
      NCATBOT_CONFIG_PATH: /tmp/ncatbot.yaml
      NAPCAT_WS_URI: ${NAPCAT_WS_URI}
      NAPCAT_WS_TOKEN: ${NAPCAT_WS_TOKEN}
      MEM0_GRAPH_NEO4J_URL: ${MEM0_GRAPH_NEO4J_URL}
      MEM0_GRAPH_NEO4J_USERNAME: ${MEM0_GRAPH_NEO4J_USERNAME}
      MEM0_GRAPH_NEO4J_PASSWORD: ${MEM0_GRAPH_NEO4J_PASSWORD}
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./logs:/app/logs

networks:
  default:
    name: antlerbot
```
```

- [ ] **Step 6: Expand `.env.example` with Docker deployment variables**

Append these lines after the existing provider variables:

```dotenv
NAPCAT_WS_URI=ws://napcat:3001
NAPCAT_WS_TOKEN=

MEM0_GRAPH_NEO4J_URL=bolt://neo4j:7687
MEM0_GRAPH_NEO4J_USERNAME=neo4j
MEM0_GRAPH_NEO4J_PASSWORD=
NEO4J_PASSWORD=
NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
```

- [ ] **Step 7: Run the Docker artifact tests and verify they pass**

Run:
```bash
pytest tests/test_docker_artifacts.py -v
```

Expected:
- Compose mounts `config/`, `data/`, and `logs/`.
- Neo4j has no host `ports` mapping.
- Docker template uses WebSocket connection mode with `skip_setup: true`.
- Dockerfile uses the entrypoint script.

- [ ] **Step 8: Commit the Docker runtime files**

```bash
git add Dockerfile .dockerignore docker-compose.yml docker/entrypoint.sh config/ncatbot.docker.yaml.template .env.example tests/test_docker_artifacts.py
git commit -m "feat: add docker deployment stack"
```

---

### Task 4: Verify end-to-end deployment shape and keep local workflow intact

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker/entrypoint.sh`
- Test: `tests/test_memory.py`
- Test: `tests/test_docker_artifacts.py`

- [ ] **Step 1: Build the image to verify the Dockerfile is valid**

Run:
```bash
docker compose build antlerbot
```

Expected:
- The image builds successfully.
- `pip install -r requirements.txt` succeeds.
- The entrypoint script is copied and marked executable.

- [ ] **Step 2: Run the focused Python test suite**

Run:
```bash
pytest tests/test_memory.py tests/test_docker_artifacts.py -v
```

Expected:
- All graph-config and Docker artifact tests pass together.

- [ ] **Step 3: Start the compose stack with filled `.env` values and inspect service state**

Run:
```bash
docker compose up -d neo4j antlerbot
docker compose ps
```

Expected:
- `neo4j` is `healthy`.
- `antlerbot` is `running`.
- No Neo4j host ports are published.

- [ ] **Step 4: Inspect the rendered runtime config inside the app container**

Run:
```bash
docker compose exec antlerbot python - <<'PY'
from pathlib import Path
print(Path('/tmp/ncatbot.yaml').read_text(encoding='utf-8'))
PY
```

Expected:
- The rendered file contains the resolved `ws_uri` and `ws_token` values.
- `skip_setup: true` is present.
- The app is not using `localhost:3001` unless the user explicitly set that in `.env`.

- [ ] **Step 5: Commit any final fixes from verification**

```bash
git add Dockerfile docker-compose.yml docker/entrypoint.sh config/ncatbot.docker.yaml.template .env.example src/agent/memory.py config/agent/settings.yaml tests/test_memory.py tests/test_docker_artifacts.py
git commit -m "test: verify docker deployment workflow"
```

---

## Self-Review Checklist

### Spec coverage
- Production image for AntlerBot: covered by Task 3.
- Compose-managed `antlerbot` + `neo4j`: covered by Task 3 and Task 4.
- External NapCat via connection mode: covered by `config/ncatbot.docker.yaml.template` and Task 4 runtime inspection.
- Mount `config/`, `data/`, `logs/`: covered by Task 3 tests and compose file.
- Neo4j internal only: covered by compose test asserting no `ports` on `neo4j`.
- Move Neo4j URL/username/password out of checked-in settings: covered by Task 2.

### Placeholder scan
- No `TODO`/`TBD` markers remain.
- Every code-changing step includes concrete code or exact file content.
- Every verification step includes exact commands and expected outcomes.

### Type consistency
- Neo4j env variable names are consistent across tests, compose, entrypoint, and memory resolution:
  - `MEM0_GRAPH_NEO4J_URL`
  - `MEM0_GRAPH_NEO4J_USERNAME`
  - `MEM0_GRAPH_NEO4J_PASSWORD`
- NapCat env variable names are consistent across compose, entrypoint, and template:
  - `NAPCAT_WS_URI`
  - `NAPCAT_WS_TOKEN`
