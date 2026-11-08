#!/usr/bin/env python3
"""OPTIONAL. Deliberately exceed 5 req/s on ONE trial base to provoke an HTTP 429 for testing the migrator's backoff.

    python src/burst_429.py --yes [--table "Retail Locations"] [--threads 12] [--seconds 6]
Read-only (GET list, pageSize=1). Airtable then blocks that base for ~30 s; never run it while a seed or migration is running.

Testing a 403: use the MIGRATOR's read-only token (not the write token) against (a) a base it was not granted, or
(b) a write call such as POST /v0/meta/bases/{id}/tables. Expect 403 (some cases may return 404 or 401; unverified,
record what you see). Do not use the write token for this.
"""
import argparse, collections, os, sys, threading, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--base", default="ff_main")
    ap.add_argument("--table", default="Retail Locations")
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--seconds", type=float, default=6)
    a = ap.parse_args()
    try:
        cfg = seed.load_config()
        api = seed.Api(cfg)
        seed.preflight(api, cfg, {"bases": {k: None for k in cfg["bases"]}})
    except seed.Fatal as e:
        print("STOP:", e); sys.exit(2)
    if not a.yes:
        print("add --yes to run"); return
    bid = cfg["bases"][a.base]
    t = seed.live_tables(api, bid)[a.table]
    url = "%s/v0/%s/%s?pageSize=1" % (seed.API, bid, t["id"])
    tally, lock, end = collections.Counter(), threading.Lock(), time.time() + a.seconds

    def work():
        while time.time() < end:
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + api._token})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    c = r.status
            except urllib.error.HTTPError as e:
                c = e.code
            except Exception:
                c = 0
            with lock:
                tally[c] += 1
    th = [threading.Thread(target=work) for _ in range(a.threads)]
    [x.start() for x in th]; [x.join() for x in th]
    print("status counts:", dict(tally), "(429 expected; base is throttled ~30 s)")


if __name__ == "__main__":
    main()
