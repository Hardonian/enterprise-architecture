#!/usr/bin/env python3
"""
eacp-monitor — continuous enterprise health monitor.
Runs EACP's probe engine against the live lab, writes a timestamped JSON report,
and emits a one-line summary to stdout (for systemd journal capture).

Intended to run on a 15-min systemd user timer. Idempotent + non-fatal.
"""
import json, subprocess, os, datetime, urllib.request, urllib.error

REPO = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(REPO, "state")
os.makedirs(STATE_DIR, exist_ok=True)


def probe_all() -> dict:
    """Call the live EACP /probe-all endpoint; fall back to the C binary directly."""
    # prefer the running control plane
    try:
        with urllib.request.urlopen("http://127.0.0.1:8099/probe-all", timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        pass
    # fall back: run the C binary on the known endpoints
    binp = os.path.join(REPO, "probe")
    if os.path.exists(binp):
        urls = ["http://localhost:8090/health", "http://localhost:8050/health",
                "http://localhost:11438/api/tags", "http://localhost:8188/",
                "http://localhost:8012/health", "http://localhost:8011/health"]
        out = subprocess.run([binp], input="\n".join(urls) + "\n",
                             capture_output=True, text=True, timeout=10)
        try:
            return {"engine": "c-epyc-native", "results": json.loads(out.stdout)}
        except Exception:
            return {"engine": "none", "results": []}
    return {"engine": "none", "results": []}


def main():
    rep = probe_all()
    results = rep.get("results", [])
    up = sum(1 for r in results if r.get("status") == "up")
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    report = {"timestamp": ts, "engine": rep.get("engine"),
              "probed": len(results), "up": up, "down": len(results) - up,
              "results": results}
    # also capture live runtime topology trend (containers / ports / gpus)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8099/infrastructure", timeout=5) as r:
            infra = json.loads(r.read())
        report["topology"] = infra.get("summary", {})
    except Exception:
        pass
    out_path = os.path.join(STATE_DIR, f"probe-{ts[:10]}.json")
    # append-line jsonl for trending
    with open(os.path.join(STATE_DIR, "probe-history.jsonl"), "a") as f:
        f.write(json.dumps(report) + "\n")
    # keep latest snapshot
    with open(os.path.join(STATE_DIR, "probe-latest.json"), "w") as f:
        json.dump(report, f, indent=2)
    topo = report.get("topology", {})
    topo_s = f"containers={topo.get('containers')} ports={topo.get('ports')} gpus={topo.get('gpus')}" if topo else "topology=n/a"
    print(f"[eacp-monitor {ts}] engine={rep.get('engine')} up={up}/{len(results)} {topo_s}")


if __name__ == "__main__":
    main()
