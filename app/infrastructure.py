#!/usr/bin/env python3
"""
infrastructure.py — live runtime topology discovery for EACP.
Discovers the actual running enterprise infrastructure: Docker containers,
listening ports, and GPU allocation. This is what makes EACP "enterprise grade":
it maps not just GitHub repos but the live runtime substrate they run on.

All discovery is read-only and graceful (missing tool -> empty section, never error).
"""
from __future__ import annotations
import json, subprocess, os


def _run(cmd, timeout: float = 5.0):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return ""


def discover_docker() -> list[dict]:
    out = _run(["docker", "ps", "--format",
                "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"])
    containers = []
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        containers.append({
            "name": parts[0], "status": parts[1], "image": parts[2],
            "ports": parts[3].replace(", ", ","),
        })
    return containers


def discover_ports() -> list[dict]:
    """Listening TCP ports (localhost)."""
    out = _run(["ss", "-tlnp", "-H"], timeout=5)
    ports = []
    for line in out.strip().splitlines():
        f = line.split()
        # local addr is the 4th field in -H mode
        if len(f) < 4:
            continue
        local = f[3]
        if ":" in local:
            host, port = local.rsplit(":", 1)
            ports.append({"host": host, "port": int(port) if port.isdigit() else port})
    return sorted(ports, key=lambda x: str(x["port"]))


def discover_gpus() -> list[dict]:
    out = _run(["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits"], timeout=8)
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5:
            gpus.append({
                "index": int(parts[0]), "name": parts[1],
                "mem_used_mb": int(parts[2]), "mem_total_mb": int(parts[3]),
                "util_pct": int(parts[4]),
            })
    return gpus


def discover_all() -> dict:
    return {
        "docker_containers": discover_docker(),
        "listening_ports": discover_ports(),
        "gpus": discover_gpus(),
        "summary": {
            "containers": len(discover_docker()),
            "ports": len(discover_ports()),
            "gpus": len(discover_gpus()),
        },
    }


if __name__ == "__main__":
    print(json.dumps(discover_all(), indent=2))
