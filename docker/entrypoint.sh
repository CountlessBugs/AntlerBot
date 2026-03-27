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
