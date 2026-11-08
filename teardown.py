#!/usr/bin/env python3
"""Delete every record in the seeded TRIAL bases (10 per request). Tables/fields stay: Airtable has no table-delete API.

    python teardown.py --dry-run
    python teardown.py --yes
Same safety rules as seed.py: write token only from seed_config.json, base name must start with the trial prefix.
Also removes seed_log.json record/link/attachment state so the next seed starts clean.
"""
import argparse, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seed
from seed import Api, Fatal, API, err_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        cfg = seed.load_config()
        api = Api(cfg, dry=a.dry_run)
        seed.preflight(api, cfg, {"bases": {k: None for k in cfg["bases"]}})
        if not (a.yes or a.dry_run):
            raise Fatal("add --yes to confirm deleting ALL records in: " + ", ".join(cfg["bases"]))
        total = 0
        for label, bid in cfg["bases"].items():
            for name, t in seed.live_tables(api, bid).items():
                ids, offset = [], None
                while True:
                    q = "?pageSize=100&fields%5B%5D=" + urllib.parse.quote(t["fields"][0]["name"]) + ("&offset=" + offset if offset else "")
                    st, js = api.call("GET", "%s/v0/%s/%s%s" % (API, bid, t["id"], q), bid)
                    if st != 200:
                        raise Fatal("list %s failed: %s" % (name, err_text(js)))
                    ids += [r["id"] for r in js["records"]]
                    offset = js.get("offset")
                    if not offset:
                        break
                print("%-28s %5d records" % (name, len(ids)))
                if a.dry_run:
                    continue
                for i in range(0, len(ids), 10):
                    qs = "&".join("records%5B%5D=" + x for x in ids[i:i + 10])
                    st, js = api.call("DELETE", "%s/v0/%s/%s?%s" % (API, bid, t["id"], qs), bid)
                    if st != 200:
                        raise Fatal("delete failed in %s: %s" % (name, err_text(js)))
                total += len(ids)
        if not a.dry_run:
            if os.path.exists(seed.LOG_PATH):
                os.remove(seed.LOG_PATH)
            print("deleted %d records; seed_log.json removed" % total)
    except Fatal as e:
        print("STOP:", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
