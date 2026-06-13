# Module Boundaries V1

This project is split into a central scheduler/product system and a local browser executor.

## Central Server

New central code should prefer these domain import paths:

- `intelligence_engine.jobs`: job lifecycle, queue, maintenance, materialization, diagnostics
- `intelligence_engine.accounts`: platform accounts, login sessions, local agents, agent bindings
- `intelligence_engine.content`: content identities, snapshots, comments, workflow, media
- `intelligence_engine.reference_library`: reference library items, selection, rule profiles
- `intelligence_engine.operations`: operations center read/write workflows
- `intelligence_engine.rules`: operation rules and rule profile management
- `intelligence_engine.organization`: users, employees, roles, organization inventory

Existing implementations may still live under `services/` and `storage/repositories/`.
The facade packages are the migration boundary: new code should import through the domain package first.

## Shared Contracts

Central server and Local Agent share HTTP contract types through the repository-level `shared_contracts` package.

The package intentionally covers only cross-process protocol data:

- Agent capabilities and heartbeat shape
- Job claim/start/progress/complete/fail payloads
- Ingestion payloads
- Account-login claim payloads
- Shared platform/job/error enums

Product-only or UI-only schemas should stay in `central_server/intelligence_engine/domain`.

## Local Agent

New Local Agent runtime code should prefer:

- `local_agent_runtime.core`: runtime and local bridge entrypoints
- `local_agent_runtime.connectors.base`: connector protocol and registry
- `local_agent_runtime.connectors.<platform>`: platform-specific execution and normalization

Platform connectors should expose a stable capability/support/execute boundary so future platforms do not expand the core runtime loop.

## Migration Rules

1. Do not add new large route sections to `api/product_routes.py`; create a focused route module or service first.
2. Do not mutate Job lifecycle fields directly from routes; use `JobRepository` or the `jobs` domain package.
3. Do not add new central/local duplicate protocol enums; add them to `shared_contracts` and extend the alignment tests.
4. Keep repository methods persistence-focused; cross-entity business workflows belong in service/domain modules.
5. Keep compatibility paths for legacy task templates until the migration backlog is empty.

