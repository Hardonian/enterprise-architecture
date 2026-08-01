# enterprise-architecture

**Enterprise Architecture Control Plane (EACP)** — the missing top-level service-group that
wires the entire Hardonian enterprise together.

The Hardonian org runs **58 live repositories** across 10+ architecture layers (identity,
AI inference, governance, finance, delivery, commercial, observability, content, edge,
integration). Until now there was no single layer that *classified, mapped, and probed*
all of them — and 8 repos were orphaned with no layer. This repo fills that gap.

## What it does

- **Discovers** all live Hardonian repos via `gh` (real, not hardcoded).
- **Classifies** each into an architecture layer (service-group).
- **Assigns** the 8 previously-uncategorized repos to a proper layer.
- **Exposes** a FastAPI control plane serving the full enterprise wiring map.
- **Probes** live lab service endpoints (graceful: unreachable ≠ failure).

## Quick start

```bash
uv venv && uv pip install -e .
python -m app.catalog          # regenerate enterprise-catalog.json
uvicorn app.main:app --port 8099
```

Then open `http://localhost:8099/catalog` or `/wiring`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/catalog` | Full 58-repo classified catalog |
| GET | `/layers` | Layer names + counts |
| GET | `/wiring` | Layer → service → endpoint map |
| GET | `/service/{name}/health` | Probe one service |
| GET | `/probe-all` | Probe every known live endpoint |

## Architecture layers

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full layer map and the live-endpoint
wiring table.

## Status

This is the **control-plane layer** of the enterprise. It does not replace any existing repo;
it makes the enterprise *observable as one system*. All other repos remain the owners of their
own domains. EACP is the map, not the territory.

## Endpoints (full control plane)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/catalog` | Full 58-repo classified catalog |
| GET | `/layers` | Layer names + counts |
| GET | `/wiring` | Layer → service → endpoint map |
| GET | `/service/{name}/health` | Probe one service |
| GET | `/probe-all` | Probe every known live endpoint (C-EPYC-native engine) |
| GET | `/openapi` | Ingest live OpenAPI specs from services that expose them |
| GET | `/infrastructure` | Live runtime topology: Docker containers, listening ports, GPU allocation |

## Runtime topology awareness

EACP is enterprise-grade: beyond the 58 GitHub repos, `/infrastructure` discovers the live
substrate — Docker containers (Postgres-pgvector, Redis, Qdrant, Meilisearch, OpenWebUI, n8n,
Portainer, Loki/Promtail/Alertmanager/Blackbox, continuityos, TokenGoblin, kamal-proxy, etc.),
listening ports, and GPU allocation (V100 / P40 / RTX3060). The enterprise is observable as
one system: code + runtime + hardware.
