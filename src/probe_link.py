#!/usr/bin/env python3
"""Diagnose one failing link field. Shows the live field definition and tries ONE record, printing Airtable's full reply.
    python src/probe_link.py "Items" "Collection" [--base ff_main] [--typecast] [--row N]
Costs ~3 calls. Writes the same value the link pass would write (one record), nothing else. Token is never printed."""
import argparse, json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seed

ap = argparse.ArgumentParser()
ap.add_argument("table"); ap.add_argument("field")
ap.add_argument("--base", default="ff_main")
ap.add_argument("--typecast", action="store_true")
ap.add_argument("--row", type=int, default=0, help="which row (0 = first with a value for this field)")
a = ap.parse_args()
try:
    cfg = seed.load_config(); api = seed.Api(cfg)
    seed.preflight(api, cfg, {"bases": {k: None for k in cfg["bases"]}})
    schema = seed.build_schema(); log = seed.load_log()
    base = schema["bases"][a.base]; bid = cfg["bases"][a.base]
    t = [x for x in base["tables"] if x["name"] == a.table][0]
    tmap = {x["key"]: x for x in base["tables"]}
    live = seed.live_tables(api, bid)
    lt = live[a.table]
    fld = [f for f in lt["fields"] if f["name"] == a.field][0]
    show = json.loads(json.dumps(fld))
    ch = show.get("options", {}).get("choices")
    if ch and len(ch) > 4:
        show["options"]["choices"] = ch[:3] + ["... %d choices in total, first 3 shown" % len(ch)]
    print("LIVE FIELD TYPE:", fld["type"])
    print("LIVE FIELD:", json.dumps(show, indent=1))
    tgt = tmap[t["by_name"][a.field]["link"]["target"]]
    print("expected target table:", tgt["name"], "->", live[tgt["name"]]["id"])
    ids = log["records"].get("%s/%s" % (a.base, t["key"]), {})
    tids = log["records"].get("%s/%s" % (a.base, tgt["key"]), {})
    rows = [r for r in seed.read_jsonl(a.base, t["key"]) if a.field in r["links"] and r["key"] in ids]
    r = rows[a.row]
    arr = [tids.get(k) for k in r["links"][a.field]]
    print("row %s -> record %s; sending %s = %s (keys %s)" % (r["key"], ids[r["key"]], a.field, arr, r["links"][a.field]))
    body = {"records": [{"id": ids[r["key"]], "fields": {a.field: arr}}]}
    if a.typecast:
        body["typecast"] = True
    st, js = api.call("PATCH", "%s/v0/%s/%s" % (seed.API, bid, lt["id"]), bid, body)
    print("STATUS", st); print(json.dumps(js, indent=1)[:1500])
except seed.Fatal as e:
    print("STOP:", e); sys.exit(2)
