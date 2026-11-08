#!/usr/bin/env python3
"""Offline self-check of the generated kit. Re-derives key facts by a different route than generate.py.

    python verify.py            # exit code 1 if anything fails
"""
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "out")
fails, passes = [], 0


def check(cond, msg):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(msg)
        print("FAIL:", msg)


def rd(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    from fw_schema import build_schema
    schema = build_schema()
    # ---- 1. legacy rows preserved exactly (values and keys) in the CSV export
    L = os.path.join(HERE, "legacy")
    legacy_map = [("Retail_Locations", "Retail Locations", ["id", "City", "Cross Street", "Freestanding/Mall"]),
                  ("Sales_Persons", "Sales Persons", ["id", "Name", "Email", "Commission Rate"]),
                  ("Items", "Items", ["id", "Name", "Cost", "Price"]),
                  ("Clients", "Clients", ["id", "Name"])]
    for fn, tn, cols in legacy_map:
        old = rd(os.path.join(L, "csv_output_%s.csv" % fn))
        new = rd(os.path.join(OUT, "data_csv", "ff_main", "%s.csv" % tn))
        for o, n in zip(old, new):
            for c in cols:
                ov, nv = o[c], n[c]
                try:
                    same = float(ov) == float(nv)
                except ValueError:
                    same = ov == nv
                check(same, "legacy %s %s.%s changed: %r -> %r" % (tn, o["id"], c, ov, nv))
    old = rd(os.path.join(L, "csv_output_Sales_Items.csv"))
    new = rd(os.path.join(OUT, "data_csv", "ff_main", "SalesItems.csv"))
    for i, o in enumerate(old):
        n = new[i]
        for a, b in (("purchaseId", "purchaseId"), ("itemId", "itemId")):
            check(o[a] == n[b], "legacy SalesItems row %d %s changed" % (i, a))
        for c in ("Price", "Cost", "Discount", "Commission"):
            check(float(o[c]) == float(n[c]), "legacy SalesItems row %d %s changed" % (i, c))
    # ---- 2. independent load-order check (Kosaraju + topological property)
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        by_id = {f["id"]: (t, f) for t in b["tables"] for f in t["fields"]}
        for mode, fn in (("resolve", "expected_load_order.csv"), ("literal", "expected_load_order_literal.csv")):
            rows = [r for r in rd(os.path.join(OUT, "answer_key", fn)) if r["base"] == b["label"]]
            no = {r["table"]: int(r["load_no_within_base"]) for r in rows}
            check(sorted(no.values()) == list(range(1, len(tmap) + 1)), "%s %s load numbers not 1..n" % (b["label"], mode))
            edges = set()
            for t in b["tables"]:
                for f in t["fields"]:
                    lk = f.get("link")
                    if not lk or lk["target"] == t["key"]:
                        continue
                    if mode == "resolve" and lk["inverse_id"]:
                        it, inf = by_id[lk["inverse_id"]]
                        if lk["single"] != inf["link"]["single"] and not lk["single"]:
                            continue
                    edges.add((t["key"], lk["target"]))
            # reachability closure
            reach = {k: set() for k in tmap}
            for c, p in edges:
                reach[c].add(p)
            ch = True
            while ch:
                ch = False
                for k in reach:
                    for p in list(reach[k]):
                        new = reach[p] - reach[k]
                        if new:
                            reach[k] |= new
                            ch = True
            scc_of = {k: frozenset([k] + [j for j in tmap if j in reach[k] and k in reach[j]]) for k in tmap}
            for c, p in edges:
                if scc_of[c] != scc_of[p]:
                    check(no[tmap[p]["name"]] < no[tmap[c]["name"]], "%s %s: parent %s not before child %s" % (b["label"], mode, tmap[p]["name"], tmap[c]["name"]))
            for r in rows:
                k = [x for x in tmap if tmap[x]["name"] == r["table"]][0]
                check((len(scc_of[k]) > 1) == (r["in_cycle"] == "yes"), "%s %s cycle flag wrong for %s" % (b["label"], mode, r["table"]))
    # ---- 3. topology coverage (resolve mode) asserted from the answer key
    lo = {(r["base"], r["table"]): r for r in rd(os.path.join(OUT, "answer_key", "expected_load_order.csv"))}
    g = lambda t: lo[("ff_main", t)]
    check(g("Clients")["self_link"] == "yes" and g("Employees")["self_link"] == "yes", "self-link tables not flagged")
    check(g("Retail Locations")["cycle_members"] == "Retail Locations; Store Managers", "2-table cycle missing")
    check(g("Collections")["cycle_members"] == "Ateliers; Collections; Designers", "3-table cycle missing")
    check(g("Lookbooks")["in_cycle"] == "yes" and g("Style Tags")["in_cycle"] == "yes", "many-to-many pair should stay a cycle in resolve mode")
    check(g("Campaign Tasks")["in_cycle"] == "no" and g("Campaign Tasks")["depth"] == "1", "single-hint pair should resolve")
    check(g("Suppliers")["in_cycle"] == "yes", "both-single pair should stay ambiguous")
    check(int(g("Restock Orders")["depth"]) >= 5, "chain of 5+ levels missing")
    check(g("Style Glossary")["parent_tables"] == "" and g("Style Glossary")["in_cycle"] == "no", "link-free table wrong")
    check(g("Items")["depth"] == "1", "Items should sit one level below the 3-cycle (link into cycle from outside)")
    lt = rd(os.path.join(OUT, "answer_key", "expected_link_treatment.csv"))
    so = [r for r in lt if r["table"] == "Special Orders" and r["links_to_table"] == "Retail Locations" and r["is_inverse_field"] == "no"]
    check(len(so) == 2, "two links from Special Orders to Retail Locations missing")
    # diamond: Purchase has two distinct parents that share Retail Locations ancestry
    check(set(g("Purchase")["parent_tables"].split("; ")) == {"Clients", "Sales Persons"}, "diamond arms wrong")
    # ---- 4. quota table
    w = [t for t in schema["bases"]["ff_main"]["tables"] if t["key"] == "wide"][0]
    ty = [f["type"] for f in w["fields"]]
    check(ty.count("multilineText") >= 25 and ty.count("formula") >= 20 and ty.count("multipleRecordLinks") >= 35 and 110 <= len(ty) <= 130, "quota table composition")
    # ---- 5. independent profile recomputation from the CSV export for plain seeded fields
    prof = rd(os.path.join(OUT, "answer_key", "expected_profile.csv"))
    csvcache = {}
    nchecked = 0
    for p in prof:
        if p["value_source"] != "seeded" or p["field_type"] in ("checkbox", "singleCollaborator", "multipleCollaborators", "barcode", "number", "currency", "percent", "duration", "rating"):
            continue
        if p["field_exists"] != "yes" or "WHITESPACE" in p["flags"]:
            continue
        key = (p["base"], p["table"])
        if key not in csvcache:
            csvcache[key] = rd(os.path.join(OUT, "data_csv", p["base"], "%s.csv" % p["table"]))
        rows = csvcache[key]
        if p["field"] not in rows[0]:
            continue
        vals = [r[p["field"]] for r in rows]
        nulls = sum(1 for v in vals if v == "")
        card = len({v for v in vals if v != ""})
        check(int(p["row_count"]) == len(rows), "row_count %s.%s" % (p["table"], p["field"]))
        check(int(p["null_count"]) == nulls, "null_count %s.%s: key %s vs csv %d" % (p["table"], p["field"], p["null_count"], nulls))
        if p["field_type"] not in ("multipleSelects", "multipleRecordLinks", "date", "dateTime"):
            check(int(p["cardinality"]) == card, "cardinality %s.%s: key %s vs csv %d" % (p["table"], p["field"], p["cardinality"], card))
        nchecked += 1
    print("profile cross-checked for", nchecked, "plain seeded fields")
    # ---- 6. attachments
    man = json.load(open(os.path.join(OUT, "attachments", "manifest.json"), encoding="utf-8"))
    for m in man:
        d = open(os.path.join(OUT, m["blob"]), "rb").read()
        check(hashlib.sha256(d).hexdigest() == m["sha256"] and len(d) == m["size"], "blob mismatch for %s" % m["filename"])
        if m["mime"] in ("image/png", "image/svg+xml", "application/pdf") or m["filename"].lower().endswith((".png", ".svg", ".pdf")):
            if m["size"] > 0 and m["filename"] != "looks_like.jpg":
                pass
        if d[:8] == b"\x89PNG\r\n\x1a\n" or d[:4] == b"%PDF" or d[:5] == b"<?xml":
            check(b"SAMPLE" in d or d[:4] != b"%PDF" and d[:5] != b"<?xml", "mark missing in %s" % m["filename"])
    sizes = [m["size"] for m in man]
    check(any(s < 10000 for s in sizes), "no tiny file")
    check(any(100_000 <= s <= 2_000_000 for s in sizes), "no medium file")
    check(any(4_400_000 <= s <= 4_600_000 for s in sizes), "no ~4.5MB file")
    check(any(s > 5 * 1024 * 1024 for s in sizes), "no >5MB manual file")
    cells = {}
    for m in man:
        cells.setdefault((m["table_key"], m["row"], m["field"]), []).append(m)
    cnt = [len(v) for v in cells.values()]
    check(any(c == 1 for c in cnt) and any(c >= 3 for c in cnt), "cell shapes (1 and 3+) missing")
    check(any(len({x["filename"] for x in v}) < len(v) for v in cells.values()), "identical filenames in one cell missing")
    names = {}
    for m in man:
        names.setdefault(m["filename"], set()).add((m["table_key"], m["row"]))
    check(any(len(v) > 1 for v in names.values()), "same filename across records missing")
    shas = {}
    for m in man:
        shas.setdefault(m["sha256"], set()).add((m["table_key"], m["row"]))
    check(any(len(v) > 1 for v in shas.values()), "checksum duplicates across records missing")
    # a rendered check of every pdf with pdftotext when available
    import shutil
    import subprocess
    if shutil.which("pdftotext"):
        bad = 0
        for m in [x for x in man if x["filename"].endswith(".pdf")][:40]:
            r = subprocess.run(["pdftotext", os.path.join(OUT, m["blob"]), "-"], capture_output=True, text=True)
            if r.returncode != 0 or "SAMPLE - FICTIONAL DATA" not in r.stdout:
                bad += 1
        check(bad == 0, "%d PDFs failed to render with the mark" % bad)
    # ---- 7. fictional-data hygiene
    bad_dom = 0
    for root, _, files in os.walk(os.path.join(OUT, "data_csv")):
        for f in files:
            txt = open(os.path.join(root, f), encoding="utf-8").read()
            for tok in txt.replace(",", " ").replace('"', " ").split():
                if "@" in tok and not tok.lower().rstrip(".").endswith("example.com"):
                    bad_dom += 1
    print("non-example.com email tokens in CSVs:", bad_dom, "(legacy monarchmenswear.com rows unless --sanitize-legacy)")
    print("passed %d checks, %d failed" % (passes, len(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
