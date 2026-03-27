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
    assert antlerbot_env["NEO4J_AUTH"] == "${NEO4J_AUTH}"
    assert neo4j_env["NEO4J_AUTH"] == "${NEO4J_AUTH}"



def test_ncatbot_docker_template_uses_connection_mode():
    template = (ROOT / "config" / "ncatbot.docker.yaml.template").read_text(encoding="utf-8")

    assert "ws_uri: ${NAPCAT_WS_URI}" in template
    assert "ws_token: ${NAPCAT_WS_TOKEN}" in template
    assert "skip_setup: true" in template



def test_docker_compose_uses_external_shared_network():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["neo4j"]["networks"] == ["antlerbot-shared"]
    assert compose["services"]["antlerbot"]["networks"] == ["antlerbot-shared"]
    assert compose["networks"]["antlerbot-shared"] == {"external": True}



def test_docker_compose_healthcheck_reads_username_and_password_from_neo4j_auth():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    healthcheck = compose["services"]["neo4j"]["healthcheck"]["test"][1]

    assert 'user="$${NEO4J_AUTH%%/*}"' in healthcheck
    assert 'password="$${NEO4J_AUTH#*/}"' in healthcheck
    assert 'cypher-shell -u "$$user" -p "$$password"' in healthcheck



def test_dockerfile_uses_entrypoint_script():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'COPY docker/entrypoint.sh /app/docker/entrypoint.sh' in dockerfile
    assert 'ENTRYPOINT ["/app/docker/entrypoint.sh"]' in dockerfile



def test_dockerfile_filters_windows_only_pywin32_dependency_for_linux_build():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "grep -v '^pywin32==' requirements.txt > requirements.docker.txt" in dockerfile
    assert 'pip install --no-cache-dir -r requirements.docker.txt' in dockerfile
