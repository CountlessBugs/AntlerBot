## Summary

Implemented a production-oriented Docker deployment for AntlerBot with a dedicated app image, an internal Neo4j service, and connection-mode integration with an externally managed NapCat container. The final deployment flow also adds detailed operator documentation for shared-network setup, NapCat container naming, WebUI WebSocket server creation, and token wiring.

## Deviations from Plan

- The original plan assumed separate Neo4j graph username/password environment variables; the final implementation simplified credentials to `NEO4J_AUTH` plus `MEM0_GRAPH_NEO4J_URL`.
- The final configuration also removed graph credential fields from `settings.yaml`, leaving only behavior settings plus `database`.
- Deployment documentation was expanded substantially beyond the original minimal deliverable to cover multi-instance NapCat naming and WebUI setup steps.

## Key Decisions

- Keep NapCat outside the main compose stack and require WebSocket connection mode with `skip_setup: true`.
- Use a dedicated Docker entrypoint to render runtime NCatBot config from environment variables.
- Keep Neo4j internal to the Docker network and avoid exposing host ports.
- Use `NEO4J_AUTH` as the single credential source for both Neo4j container auth and AntlerBot graph-memory auth.
- Require each deployment on the same machine to use a unique NapCat container name and matching `NAPCAT_WS_URI`.

## Lessons Learned

- Docker deployment docs need to cover operator workflow, not just file-level configuration, especially for external services like NapCat.
- Reusing `NEO4J_AUTH` reduces duplicate configuration, but it requires careful handling of healthchecks and runtime parsing.
- For multi-instance deployments, container naming and shared-network guidance must be explicit to avoid cross-instance confusion.

## Follow-ups

- Consider adding a minimal standalone NapCat compose example to the deployment docs.
- Consider adding a final archive commit for the documentation archive itself if the user wants archival changes committed separately.
