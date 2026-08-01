#!/usr/bin/env python3
"""
enterprise-architecture — Enterprise Architecture Control Plane (EACP)
The missing top-level service-group that wires the entire Hardonian enterprise:
58 live repos across 10 architecture layers + 8 previously-uncategorized services.

This module is the single source of truth for the enterprise wiring map.
It classifies every live repo, assigns orphaned services to a layer, and
exposes the wiring graph used by the FastAPI control plane.
"""
from __future__ import annotations
import json, subprocess, datetime, os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Canonical enterprise architecture layers (the "service groups")
LAYERS = {
    "Identity & Access": ["identity", "keys", "entitlement", "auth"],
    "AI Inference Runtime": ["ollama", "inference", "comfyui", "llm-", "ai-lab", "models"],
    "Governance & Evidence": ["ready", "reach", "truth", "evidence", "mission", "witness", "workproof", "requiem", "audit-pack"],
    "Finance & Cost": ["settler", "token", "finops", "billing", "gateway"],
    "Delivery & Pipelines": ["zeo", "jobforge", "nautilus", "fabric", "mesh", "edge", "delivery", "deploy", "migration", "factory"],
    "Commercial & Checkout": ["checkout", "compute-api", "storefront", "commercial", "marketplace", "b2b", "opportunity"],
    "Observability & Ops": ["labsentry", "support", "growth", "continuity", "floyo", "tfstate", "drift", "ops", "sentry", "prompt-ops"],
    "Content & Docs": ["jupyter", "prompt", "apva", "gbmds", "doc-intel", "notebook", "changelog"],
    "Edge & Cloudflare": ["cloudflare", "edge", "thermal", "web"],
    "Integration Fabric": ["integration", "golden-path", "fabric"],
    "Enterprise Portal & Strategy": ["hardonian", "strategic", "bounty", "flexible", "teemot", "nick"],
}

# Manual overrides for repos the heuristic mis-classifies
OVERRIDES = {
    "hardonia-audit-pack": "Governance & Evidence",
    "b2b-rust-api-opportunity-suite": "Commercial & Checkout",
    "migration-factory": "Delivery & Pipelines",
    "claude-builders-bounty": "Enterprise Portal & Strategy",
    "FlexibleAccessible": "Commercial & Checkout",
    "nick-morfopos-strategic": "Enterprise Portal & Strategy",
    "teemot": "Enterprise Portal & Strategy",
    "Hardonian": "Enterprise Portal & Strategy",
}

# Known live lab endpoints (EPYC / HX370) that the control plane can probe.
# Graceful fallback if unreachable (lab not on this host).
SERVICE_ENDPOINTS = {
    "ai-lab-command-center": "http://localhost:8090/health",
    "hardonia-compute-api": "http://localhost:8050/health",
    "ollama-router": "http://localhost:11438/api/tags",
    "comfyui-api": "http://localhost:8188/",
    "hardonia-checkout-api": "http://localhost:8012/health",
    "ai-lab-audit-api": "http://localhost:8011/health",
}


def classify(name: str) -> str:
    if name in OVERRIDES:
        return OVERRIDES[name]
    n = name.lower()
    for layer, keys in LAYERS.items():
        for k in keys:
            if k in n:
                return layer
    return "Uncategorized"


def discover_live_repos() -> list[dict]:
    r = subprocess.run(
        ["gh", "repo", "list", "Hardonian", "--limit", "300",
         "--json", "name,isArchived,description,url,primaryLanguage,updatedAt"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        # fallback to committed catalog if gh unavailable
        cat = load_committed_catalog()
        return cat.get("repos", [])
    repos = json.loads(r.stdout)
    return [x for x in repos if not x.get("isArchived")]


def build_catalog() -> dict:
    repos = discover_live_repos()
    layers: dict[str, list] = {}
    for r in repos:
        layer = classify(r["name"])
        layers.setdefault(layer, []).append({
            "name": r["name"], "url": r.get("url"),
            "lang": r.get("primaryLanguage"),
            "desc": (r.get("description") or "")[:90],
            "endpoint": SERVICE_ENDPOINTS.get(r["name"]),
        })
    # sort layers, ensure all canonical layers present
    ordered = {l: sorted(layers.get(l, []), key=lambda x: x["name"]) for l in LAYERS}
    if "Uncategorized" in layers:
        ordered["Uncategorized"] = sorted(layers["Uncategorized"], key=lambda x: x["name"])
    counts = {l: len(v) for l, v in ordered.items()}
    return {
        "generated": datetime.date.today().isoformat(),
        "control_plane": "enterprise-architecture (EACP)",
        "total_live": len(repos),
        "layers": ordered,
        "layer_counts": counts,
        "uncategorized": [x["name"] for x in ordered.get("Uncategorized", [])],
    }


def load_committed_catalog() -> dict:
    p = os.path.join(REPO_ROOT, "enterprise-catalog.json")
    if os.path.exists(p):
        return json.load(open(p))
    return {"repos": []}


if __name__ == "__main__":
    cat = build_catalog()
    out = os.path.join(REPO_ROOT, "enterprise-catalog.json")
    json.dump(cat, open(out, "w"), indent=2)
    print(f"Wrote {out}: {cat['total_live']} repos, {len(cat['layers'])} layers")
    print("Uncategorized:", cat["uncategorized"])
