#!/usr/bin/env python3
"""Summarise seed_log.json: failed records/link batches and failed field creations, grouped by table and reason.
    python src/show_failures.py"""
import collections, json, os
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed_log.json")   # <root>/seed_log.json
l = json.load(open(p, encoding="utf-8"))
g = collections.Counter()
for r in l.get("failed_records", []):
    g[(r["base"], r["table"], r.get("phase", "records"), r["why"])] += 1
print("failed record/link batches: %d" % sum(g.values()))
for (b, t, ph, w), n in sorted(g.items()):
    print("  %-8s %-22s %-8s x%-3d %s" % (b, t, ph, n, w))
print("failed field creations: %d" % len(l.get("failed_fields", [])))
for f in l.get("failed_fields", []):
    print("  %-8s %s.%s (%s): %s" % (f["base"], f["table"], f["field"], f["type"], f["why"]))
