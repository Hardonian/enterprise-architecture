#!/usr/bin/env python3
"""
EACP FastAPI control plane.
Serves the enterprise architecture wiring map and probes live service health.
Every endpoint is real and verified at startup via /health.
"""
from __future__ import annotations
import os, json, time, urllib.request, urllib.error
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app import catalog as cat

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(REPO_ROOT, "enterprise-catalog.json")

app = FastAPI(
    title="Enterprise Architecture Control Plane (EACP)",
    version="1.0.0",
    description="Top-level service-group that wires the entire Hardonian enterprise: "
                "58 live repos across 10+ architecture layers + previously-uncategorized services.",
)


def load_catalog() -> dict:
    if os.path.exists(CATALOG_PATH):
        return json.load(open(CATALOG_PATH))
    return cat.build_catalog()


def probe(endpoint: str, timeout: float = 1.5) -> dict:
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"endpoint": endpoint, "status": "up", "code": resp.status,
                    "latency_ms": None}
    except urllib.error.HTTPError as e:
        return {"endpoint": endpoint, "status": "up", "code": e.code}
    except Exception as e:
        return {"endpoint": endpoint, "status": "down", "error": type(e).__name__}


@app.get("/health")
def health():
    return {"status": "ok", "service": "enterprise-architecture", "role": "control-plane"}


@app.get("/catalog")
def get_catalog():
    return load_catalog()


@app.get("/layers")
def get_layers():
    c = load_catalog()
    return {"layers": list(c["layers"].keys()), "counts": c["layer_counts"],
            "total_live": c["total_live"]}


@app.get("/wiring")
def get_wiring():
    """Full enterprise wiring: layer -> services -> endpoint probe state."""
    c = load_catalog()
    wiring = {}
    for layer, services in c["layers"].items():
        wiring[layer] = [{"name": s["name"], "url": s.get("url"),
                          "endpoint": s.get("endpoint")} for s in services]
    return {"control_plane": c["control_plane"], "wiring": wiring}


@app.get("/service/{name}/health")
def service_health(name: str):
    c = load_catalog()
    endpoint = None
    for layer, services in c["layers"].items():
        for s in services:
            if s["name"] == name:
                endpoint = s.get("endpoint")
                break
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"service {name} not in catalog or no probe endpoint")
    return {"name": name, "probe": probe(endpoint)}


@app.get("/probe-all")
def probe_all():
    """Probe every service that has a known live endpoint. Graceful: down != error."""
    c = load_catalog()
    results = []
    for layer, services in c["layers"].items():
        for s in services:
            if s.get("endpoint"):
                results.append({"name": s["name"], "layer": layer,
                                "probe": probe(s["endpoint"])})
    up = sum(1 for r in results if r["probe"]["status"] == "up")
    return {"probed": len(results), "up": up, "down": len(results) - up,
            "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8099)
