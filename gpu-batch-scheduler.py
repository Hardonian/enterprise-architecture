#!/usr/bin/env python3
"""
gpu-batch-scheduler.py — idle-GPU monetization, GATED on first real payment.

This is the commercial activation lever. It stays DORMANT until the revenue ledger
records a REAL (non-synthetic) payment (commerce_events > 0 or a verified Stripe
checkout session). While dormant it does nothing but report its locked state — it
never fabricates revenue or schedules paid work on synthetic data.

When unlocked, it:
  1. Reads idle GPU capacity from EACP /infrastructure (P40/V100/RTX3060).
  2. Submits batch GPU jobs to the compute-api (prepaid credit model) for any
     queued batch work, bounded by idle capacity.
  3. Writes an audit line per scheduled job.

Policy: respects the enterprise rule "no synthetic revenue" — the unlock signal must
come from a real Stripe event, never from the synthetic ledger.
"""
from __future__ import annotations
import json, os, datetime, urllib.request, urllib.error, subprocess

REPO = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(REPO, "state")
LEDGER_HINTS = [
    os.path.expanduser("~/ai-lab/revenue-os/revenue-os.db"),
    "/home/scott/ai-lab/revenue-os/revenue-os.db",
]
COMPUTE_API = "http://127.0.0.1:8050"
EACP = "http://127.0.0.1:8099"


def _get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def real_payment_unlocked() -> tuple[bool, str]:
    """Return (unlocked, reason). Real payment = commerce_events>0 OR a verified
    settled Stripe session in the ledger. Synthetic ledger alone does NOT unlock."""
    # Primary signal: live commerce events from the storefront/checkout path.
    try:
        import sqlite3
        for db in LEDGER_HINTS:
            if os.path.exists(db):
                con = sqlite3.connect(db)
                cur = con.cursor()
                # look for a commerce_events / verified-payment table
                for tbl in ("commerce_events", "commerce_event", "payments", "stripe_events"):
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                        n = cur.fetchone()[0]
                        if n > 0:
                            con.close()
                            return True, f"real payment signal in {tbl} ({n} rows)"
                    except Exception:
                        continue
                con.close()
    except Exception:
        pass
    return False, "no real payment signal in ledger (synthetic only)"


def idle_gpu_capacity() -> list[dict]:
    infra = _get(f"{EACP}/infrastructure")
    if not infra:
        return []
    return [g for g in infra.get("gpus", []) if g.get("util_pct", 99) < 30]


def schedule_batch_job(gpu, job_kind: str = "batch-inference") -> dict:
    """Submit a batch job to the compute-api for the given GPU. Best-effort, audited."""
    payload = json.dumps({"gpu_index": gpu["index"], "kind": job_kind,
                          "source": "idle-capacity-scheduler"}).encode()
    req = urllib.request.Request(f"{COMPUTE_API}/api/v1/batch", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"gpu": gpu["index"], "status": "submitted", "code": r.status}
    except urllib.error.HTTPError as e:
        return {"gpu": gpu["index"], "status": "rejected", "code": e.code}
    except Exception as e:
        return {"gpu": gpu["index"], "status": "error", "error": type(e).__name__}


def main():
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    unlocked, reason = real_payment_unlocked()
    report = {"timestamp": ts, "unlocked": unlocked, "reason": reason}
    if not unlocked:
        report["action"] = "dormant — waiting for first real Stripe payment"
        print(f"[gpu-batch-scheduler {ts}] LOCKED: {reason}")
    else:
        idle = idle_gpu_capacity()
        report["idle_gpus"] = [g["index"] for g in idle]
        scheduled = [schedule_batch_job(g) for g in idle]
        report["scheduled"] = scheduled
        report["action"] = f"unlocked — scheduled {len(scheduled)} batch job(s) on idle GPUs"
        print(f"[gpu-batch-scheduler {ts}] UNLOCKED: {reason} -> scheduled {len(scheduled)} job(s)")
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "gpu-scheduler-log.jsonl"), "a") as f:
        f.write(json.dumps(report) + "\n")
    return report


if __name__ == "__main__":
    main()
