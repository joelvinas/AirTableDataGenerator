#!/usr/bin/env python3
"""Diff the LIVE trial-base schema (Metadata API, read-only calls) against out/schema/<label>.schema.json.
Run after `seed.py --phase schema` and the manual UI steps.  Reads the token from seed_config.json (never printed).
Checks: missing/extra tables and fields, type mismatches, link target, prefersSingleRecordLink, inverse presence,
leftover '__delete_me__' fields, select-choice drift.  Exit code 1 if anything is wrong."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seed

HERE = seed.HERE


def main():
    try:
        cfg = seed.load_config()
        api = seed.Api(cfg)
        seed.preflight(api, cfg, {"bases": {k: None for k in cfg["bases"]}})
    except seed.Fatal as e:
        print("STOP:", e); sys.exit(2)
    bad = 0
    for label, bid in cfg["bases"].items():
        exp = json.load(open(os.path.join(HERE, "out", "schema", label + ".schema.json"), encoding="utf-8"))
        live = seed.live_tables(api, bid)
        etid = {t["id"]: t["name"] for t in exp["tables"]}
        for et in exp["tables"]:
            lt = live.get(et["name"])
            if not lt:
                print("MISSING TABLE %s/%s" % (label, et["name"])); bad += 1; continue
            lf = {f["name"]: f for f in lt["fields"]}
            efn = {f["id"]: f for f in et["fields"]}
            for f in et["fields"]:
                x = lf.get(f["name"])
                if not x:
                    print("MISSING FIELD %s.%s (%s)" % (et["name"], f["name"], f["type"])); bad += 1; continue
                if x["type"] != f["type"]:
                    print("TYPE %s.%s expected %s got %s" % (et["name"], f["name"], f["type"], x["type"])); bad += 1; continue
                if f["type"] == "multipleRecordLinks":
                    eo, lo = f["options"], x.get("options", {})
                    if lo.get("prefersSingleRecordLink") != eo.get("prefersSingleRecordLink"):
                        print("SINGLE-LINK PREF %s.%s expected %s got %s (manual UI step)" % (et["name"], f["name"], eo.get("prefersSingleRecordLink"), lo.get("prefersSingleRecordLink"))); bad += 1
                    if live_target(live, lo) != etid.get(eo["linkedTableId"]):
                        print("LINK TARGET %s.%s differs" % (et["name"], f["name"])); bad += 1
                    if bool(eo.get("inverseLinkFieldId")) != bool(lo.get("inverseLinkFieldId")):
                        print("INVERSE PRESENCE %s.%s expected %s (manual UI step to delete inverse for one-way links)" % (et["name"], f["name"], bool(eo.get("inverseLinkFieldId")))); bad += 1
                if f["type"] in ("singleSelect", "multipleSelects"):
                    ec = [c["name"] for c in f["options"]["choices"]]
                    lc = [c["name"] for c in x["options"]["choices"]]
                    if ec != lc:
                        print("CHOICES %s.%s expected %d got %d (typecast may add one after records phase)" % (et["name"], f["name"], len(ec), len(lc)))
            extra = set(lf) - {f["name"] for f in et["fields"]}
            for n in sorted(extra):
                print("%s %s.%s" % ("LEFTOVER" if n.startswith("__delete_me__") else "EXTRA FIELD", et["name"], n)); bad += 1
        for n in set(live) - {t["name"] for t in exp["tables"]}:
            print("EXTRA TABLE %s/%s (delete the placeholder table in the UI)" % (label, n))
    print("live schema check: %d problem(s)" % bad)
    sys.exit(1 if bad else 0)


def live_target(live, lo):
    for n, t in live.items():
        if t["id"] == lo.get("linkedTableId"):
            return n


if __name__ == "__main__":
    main()
