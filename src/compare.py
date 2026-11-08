#!/usr/bin/env python3
"""Compare the migrator's exports with the answer key.  Plain python, tolerant of header names.

    python src/compare.py --profile migrator_profile.csv --load-order migrator_load_order.csv [--mode resolve|literal] [--base ff_main]
Expected migrator headers (case/space/underscore-insensitive; aliases accepted):
  profile:    table, field, row_count, null_count, cardinality   (optional: base)
  load order: table, load_no (or step/order)                      (optional: base, depth)
Rows are matched by (table, field).  Real IDs are not needed.  Rows flagged OBSERVED/WHITESPACE/uncertain in the key
are reported as 'soft' (informational) instead of failures."""
import argparse, csv, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # project root (this file lives in src/)
KEY = os.path.join(HERE, "out", "answer_key")
ALIAS = {"table": ["table", "tablename", "table_name"], "field": ["field", "fieldname", "field_name", "column"],
         "row_count": ["rowcount", "rows", "records", "recordcount", "total"], "null_count": ["nullcount", "nulls", "null"],
         "cardinality": ["cardinality", "distinct", "distinctcount", "uniquecount", "unique"],
         "load_no": ["loadno", "load_no_within_base", "step", "order", "loadorder", "loadposition", "loadstep"],
         "depth": ["depth", "level"], "base": ["base", "baselabel", "basename"]}


def norm(h):
    return re.sub(r"[^a-z0-9]", "", h.lower())


def read(p):
    with open(p, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def col(row, name):
    for k, v in row.items():
        if norm(k) in [norm(a) for a in ALIAS[name]]:
            return v
    return None


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile"); ap.add_argument("--load-order")
    ap.add_argument("--mode", default="resolve", choices=["resolve", "literal"])
    ap.add_argument("--base")
    a = ap.parse_args()
    hard = soft = ok = 0
    if a.profile:
        key = {(r["base"], r["table"], r["field"]): r for r in read(os.path.join(KEY, "expected_profile.csv"))}
        seen = set()
        for r in read(a.profile):
            b = col(r, "base") or a.base
            k = [x for x in key if x[1] == col(r, "table") and x[2] == col(r, "field") and (not b or x[0] == b)]
            if not k:
                print("UNKNOWN FIELD %s.%s" % (col(r, "table"), col(r, "field"))); hard += 1; continue
            e = key[k[0]]; seen.add(k[0])
            for m in ("row_count", "null_count", "cardinality"):
                got, want = num(col(r, m)), num(e[m])
                if want is None or got == want:
                    ok += 1; continue
                if e["flags"] and any(f in e["flags"] for f in ("OBSERVED", "WHITESPACE", "LINK_ARRAY", "FORMULA_ERROR", "API_CREATE", "NAME_MAY", "NEEDS_REAL", "TYPECAST", "PRECISION")):
                    print("soft  %s.%s %s expected %s got %s [%s]" % (k[0][1], k[0][2], m, want, got, e["flags"][:70])); soft += 1
                else:
                    print("FAIL  %s.%s %s expected %s got %s" % (k[0][1], k[0][2], m, want, got)); hard += 1
        missing = [k for k, v in key.items() if k not in seen and v["field_exists"] == "yes" and (not a.base or k[0] == a.base)]
        print("fields in key but absent from migrator output: %d" % len(missing))
    if a.load_order:
        fn = "expected_load_order.csv" if a.mode == "resolve" else "expected_load_order_literal.csv"
        key = {(r["base"], r["table"]): r for r in read(os.path.join(KEY, fn))}
        for r in read(a.load_order):
            b = col(r, "base") or a.base
            k = [x for x in key if x[1] == col(r, "table") and (not b or x[0] == b)]
            if not k:
                print("UNKNOWN TABLE", col(r, "table")); hard += 1; continue
            for m, kn in (("load_no", "load_no_within_base"), ("depth", "depth")):
                got = col(r, m)
                if got is None:
                    continue
                if num(got) == num(key[k[0]][kn]):
                    ok += 1
                else:
                    print("FAIL  %s %s expected %s got %s" % (k[0][1], m, key[k[0]][kn], got)); hard += 1
    print("match=%d soft=%d fail=%d" % (ok, soft, hard))
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
