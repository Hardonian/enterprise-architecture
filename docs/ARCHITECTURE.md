# Enterprise Architecture — Hardonian

The enterprise is **58 live repositories** organized into **architecture layers** (service-groups).
This repo — `enterprise-architecture` (the **Enterprise Architecture Control Plane, EACP**) —
is the missing top-level service-group that wires all of them into one coherent system.

## Why this layer existed

Every other layer had repos; **none tied them together**. The 8 previously-uncategorized
repos (Hardonian, FlexibleAccessible, nick-morfopos-strategic, claude-builders-bounty,
hardonia-audit-pack, b2b-rust-api-opportunity-suite, migration-factory, teemot) had no
home. EACP classifies them, exposes a single wiring map, and probes live service health.

## Layers (service-groups)

| Layer | Count | Representative repos |
|---|---|---|
| Identity & Access | 2 | identity-entitlement-broker, Keys |
| AI Inference Runtime | 7 | ollama-router, llm-inference-api, comfyui-api, ai-lab, ai-lab-command-center, ai-lab-audit-api(+staging) |
| Governance & Evidence | 8 | ReadyLayer, Reach, truthcore, Requiem, workproof-exchange, MissionLedger, webhook-witness, EvidenceVault, hardonia-audit-pack |
| Finance & Cost | 4 | Settler, TokenGoblin, finops-autopilot, settler-gateway |
| Delivery & Pipelines | 8 | Zeo, fabricd, edgevec, JobForge, MEL-MeshEdgeLayer, enterprise-integration-fabric, cloudflare-deploy-template, Nautilus, migration-factory |
| Commercial & Checkout | 5 | storefront, hardonia-compute-api, hardonia-checkout-api, commercial-architecture-simulator, Operator-OS-Marketplace, b2b-rust-api-opportunity-suite, FlexibleAccessible |
| Observability & Ops | 8 | growth-autopilot, support-autopilot, tfstate-drift-inspector, floyo, continuityos, labsentry, cloudflare-app-ops-dashboard, prompt-ops-hardonia-packs |
| Content & Docs | 5 | apva-framework, JupyterNotebooks, gbmds, api-changelog-radar, doc-intel-api |
| Edge & Cloudflare | 2 | thermalos-web, cloudflare-launch-portfolio |
| Integration Fabric | 1 | golden-path-platform |
| Enterprise Portal & Strategy | 8 | Hardonian, nick-morfopos-strategic, claude-builders-bounty, teemot |

(See `enterprise-catalog.json` for the authoritative, generated mapping — it is rebuilt by
`python -m app.catalog` and reflects the live org state.)

## Control plane endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /catalog` | Full classified catalog (58 repos) |
| `GET /layers` | Layer names + counts |
| `GET /wiring` | Layer → services → endpoint map |
| `GET /service/{name}/health` | Probe one known service endpoint |
| `GET /probe-all` | Probe every service with a known live endpoint (graceful) |

## Wiring to the live lab

The control plane probes known EPYC/HX370 endpoints (graceful: unreachable = `down`, not error):
- ai-lab-command-center → :8090/health
- hardonia-compute-api → :8050/health
- ollama-router → :11438/api/tags
- comfyui-api → :8188/
- hardonia-checkout-api → :8012/health
- ai-lab-audit-api → :8011/health

## Run it

```
uv venv && uv pip install -e .
python -m app.catalog        # regenerate enterprise-catalog.json
uvicorn app.main:app --port 8099
```
