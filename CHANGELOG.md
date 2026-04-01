# Changelog

## [v0.2.0] - 2026-04-01

### Added
- **Agent Mesh module** - heartbeat, start_heartbeat (daemon thread), report_metric, list_agents, get_agent, kill, resume, list_events
- Mesh module wired as `client.mesh` property (lazy init)
- Dashboard URL: mesh.axme.ai

## 0.1.2 (2026-03-18)

### Bug Fixes
- Fix `ResponseNotRead` crash when SSE streaming encounters HTTP 503 error

### Features
- `listen()` now accepts optional `status` parameter to filter intents by lifecycle status
- Default SSE stream excludes terminal statuses (COMPLETED, FAILED, CANCELED, TIMED_OUT) — agents no longer receive zombie intents

## 0.1.1 (2026-03-13)

- Initial alpha release with full AXME API coverage (96 methods)
- SSE streaming (`listen`, `observe`, `wait_for`)
- Scenario API (`apply_scenario`, `validate_scenario`)
- MCP protocol support (`mcp_initialize`, `mcp_list_tools`, `mcp_call_tool`)
- Intent lifecycle, inbox, webhooks, admin APIs
- Zero external dependencies beyond httpx
