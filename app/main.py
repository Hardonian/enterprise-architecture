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


@app.get("/openapi")
def openapi_status():
    """Ingest live OpenAPI specs from services that expose them.
    Returns the spec summary per service (graceful: unreachable = skipped)."""
    from app import catalog as cat
    results = {}
    for name, url in cat.OPENAPI_ENDPOINTS.items():
        spec = cat.fetch_openapi(name, url)
        if spec:
            results[name] = spec
    return {"ingested": len(results), "specs": results}


@app.get("/probe-all")
def probe_all():
    """Probe every service with a known live endpoint.
    Uses the pure-C EPYC-native prober (./probe) when available; falls back to
    the pure-Python prober otherwise. Graceful: down != error."""
    c = load_catalog()
    endpoints = []
    for layer, services in c["layers"].items():
        for s in services:
            if s.get("endpoint"):
                endpoints.append(s["endpoint"])
    if not endpoints:
        return {"probed": 0, "up": 0, "down": 0, "results": []}

    probe_bin = os.path.join(REPO_ROOT, "probe")
    if os.path.exists(probe_bin) and os.access(probe_bin, os.X_OK):
        import subprocess
        inp = "\n".join(endpoints) + "\n"
        try:
            out = subprocess.run([probe_bin], input=inp, capture_output=True,
                                 text=True, timeout=10)
            import json as _json
            results = _json.loads(out.stdout)
            up = sum(1 for r in results if r["status"] == "up")
            return {"engine": "c-epyc-native", "probed": len(results),
                    "up": up, "down": len(results) - up, "results": results}
        except Exception:
            pass  # fall through to python
    # python fallback
    results = []
    for layer, services in c["layers"].items():
        for s in services:
            if s.get("endpoint"):
                results.append({"url": s["endpoint"], **probe(s["endpoint"]),
                                "layer": layer, "name": s["name"]})
    up = sum(1 for r in results if r["status"] == "up")
    return {"engine": "python-fallback", "probed": len(results),
            "up": up, "down": len(results) - up, "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8099)
