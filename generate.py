#!/usr/bin/env python3
"""Generate the whole proxy-base kit: schema JSON, CSVs, seed payloads, attachments and the answer key.

    python generate.py                       # defaults
    python generate.py --large-rows 1250 --collab-count 3 --out out
Deterministic: same arguments -> byte-identical output (except Pillow-encoded JPEG, optional).
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fw_compute as fc          # noqa: E402
import fw_data                   # noqa: E402
import fw_graph                  # noqa: E402
from fw_common import DEFAULT_SEED  # noqa: E402
from fw_schema import build_schema, manual_link_steps  # noqa: E402


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ------------------------------------------------------------------ Metadata-API shaped schema
def api_schema(base):
    tmap = {t["key"]: t for t in base["tables"]}
    tables = []
    for t in base["tables"]:
        fields = []
        for f in t["fields"]:
            o = json.loads(json.dumps(f["options"]))
            lk, c = f.get("link"), f.get("calc")
            if lk:
                o = {"linkedTableId": lk["target_id"], "isReversed": False, "prefersSingleRecordLink": bool(lk["single"])}
                if lk["inverse_id"]:
                    o["inverseLinkFieldId"] = lk["inverse_id"]
            elif c and c["kind"] == "formula":
                refs = [t["by_name"][n]["id"] for n in re.findall(r"\{([^}]+)\}", o["formula"]) if n in t["by_name"]]
                o.update({"isValid": True, "referencedFieldIds": refs, "result": {"type": "number" if c["result"] == "number" else "singleLineText"}})
            elif c and c["kind"] in ("rollup", "lookup", "count"):
                lf = t["by_name"][c["link"]]
                o["recordLinkFieldId"] = lf["id"]
                o["isValid"] = True
                if c["kind"] != "count":
                    tgt = tmap[lf["link"]["target"]]
                    o["fieldIdInLinkedTable"] = tgt["by_name"][c["field"]]["id"]
                    o["result"] = {"type": "number" if c["field"] == "Price" else "singleLineText"}
            elif c and c["kind"] in ("created", "modified"):
                o["result"] = {"type": "dateTime", "options": {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"},
                                                              "timeFormat": {"name": "24hour", "format": "HH:mm"}, "timeZone": "utc"}}
            d = {"id": f["id"], "name": f["name"], "type": f["type"]}
            if o:
                d["options"] = o
            fields.append(d)
        tables.append({"id": t["id"], "name": t["name"], "primaryFieldId": t["by_name"][t["primary"]]["id"], "fields": fields, "views": []})
    return {"tables": tables}


# ------------------------------------------------------------------ cell formatting for CSV import
def csv_cell(f, v):
    if v is None:
        return ""
    t = f["type"]
    if t == "checkbox":
        return "checked" if v else ""
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    if isinstance(v, dict):
        return v.get("text", "")
    if isinstance(v, float):
        return repr(v)
    return str(v)


def is_data_field(f):
    if f.get("calc"):
        return False
    if f["type"] == "multipleAttachments":
        return False
    lk = f.get("link")
    if lk and lk["is_inverse"]:
        return False
    return True


# ------------------------------------------------------------------ integrity
def check_integrity(schema, raw):
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        prim = {}
        for t in b["tables"]:
            pk = t["primary"]
            vals = [r.get(pk) for r in raw[t["key"]]]
            assert all(v not in (None, "") for v in vals), "empty primary in %s" % t["name"]
            assert len(set(vals)) == len(vals), "duplicate primary values in %s" % t["name"]
            assert not any("," in str(v) for v in vals), "comma in a primary value in %s" % t["name"]
            prim[t["key"]] = set(vals)
        for t in b["tables"]:
            for f in t["fields"]:
                lk = f.get("link")
                if lk and not lk["is_inverse"]:
                    for r in raw[t["key"]]:
                        for v in r.get(f["name"], []) or []:
                            assert v in prim[lk["target"]], "dangling link %s.%s -> %r" % (t["name"], f["name"], v)


def legacy_check(schema, raw, norm):
    """Compare preserved legacy values + recomputed computed fields with the original CSVs."""
    notes = []
    leg = {n: fw_data.read_legacy(n) for n in ("Retail_Locations", "Sales_Persons", "Items", "Clients", "Purchases", "Sales_Items")}
    pairs = [("loc", "Retail_Locations", {"City": "City", "Cross Street": "Cross Street", "Freestanding/Mall": "Freestanding/Mall"}),
             ("rep", "Sales_Persons", {"Name": "Name", "Email": "Email"}),
             ("itm", "Items", {"Name": "Name"}), ("cli", "Clients", {"Name": "Name"})]
    bad = 0
    for tk, fn, cols in pairs:
        for lg, r in zip(leg[fn], raw[tk]):
            assert r["id"] == lg["id"], (tk, r["id"], lg["id"])
            for a, b in cols.items():
                if r.get(a) != lg[b]:
                    bad += 1
                    notes.append("%s %s.%s differs: %r vs %r" % (tk, lg["id"], a, r.get(a), lg[b]))
    for lg, r in zip(leg["Items"], norm["itm"]):
        if abs(r["Margin"] - float(lg["Margin"])) > 1e-9:
            notes.append("Items %s Margin recomputed %s != legacy %s" % (lg["id"], r["Margin"], lg["Margin"]))
    for lg, r in zip(leg["Purchases"], norm["pur"]):
        if abs(r["Total"] - float(lg["Total"])) > 1e-6:
            notes.append("Purchase %s Total recomputed %s != legacy %s" % (lg["id"], r["Total"], lg["Total"]))
    sp = {x["id"]: float(x["Commission Rate"]) for x in leg["Sales_Persons"]}
    for lg in leg["Sales_Items"]:
        pass
    return notes


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--large-rows", type=int, default=1250, help="row count of the SalesItems table (1,200+ recommended)")
    ap.add_argument("--collab-count", type=int, default=3, help="number of distinct real collaborators you can supply at seed time")
    ap.add_argument("--sanitize-legacy", action="store_true", help="rewrite the two legacy real-looking values (monarchmenswear.com emails, 'Loro Piana')")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    cfg = {"seed": a.seed, "large_rows": a.large_rows, "collab_count": a.collab_count, "sanitize_legacy": a.sanitize_legacy}
    out = a.out
    if os.path.isdir(out):
        shutil.rmtree(out)
    schema = build_schema()
    raw, att = fw_data.generate(schema, cfg)
    for b in schema["bases"].values():
        for t in b["tables"]:
            t["rows"] = len(raw[t["key"]])
    check_integrity(schema, raw)
    norm = fc.normalize(schema, raw)
    fc.fill_inverse(schema, norm)
    fc.fill_computed(schema, norm)
    keyof = {t["key"]: t for b in schema["bases"].values() for t in b["tables"]}
    baseof = {t["key"]: b["label"] for b in schema["bases"].values() for t in b["tables"]}

    # ---- schema + csv + seed payload
    for b in schema["bases"].values():
        write_json(os.path.join(out, "schema", "%s.schema.json" % b["label"]), api_schema(b))
        for t in b["tables"]:
            dfields = [f for f in t["fields"] if is_data_field(f)]
            rows = [[csv_cell(f, r.get(f["name"])) for f in dfields] for r in raw[t["key"]]]
            write_csv(os.path.join(out, "data_csv", b["label"], "%s.csv" % t["name"]), [f["name"] for f in dfields], rows)
            lines = []
            for r in norm[t["key"]]:
                flds, links = {}, {}
                for f in t["fields"]:
                    if f["name"] not in r or f.get("calc") or f["type"] == "multipleAttachments":
                        continue
                    lk = f.get("link")
                    if lk:
                        if not lk["is_inverse"]:
                            links[f["name"]] = r[f["name"]]
                    else:
                        flds[f["name"]] = r[f["name"]]
                lines.append({"key": r[t["primary"]], "fields": flds, "links": links})
            p = os.path.join(out, "seed_payload", b["label"], "%s.jsonl" % t["key"])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                for ln in lines:
                    fh.write(json.dumps(ln, ensure_ascii=False) + "\n")
        write_json(os.path.join(out, "seed_payload", b["label"], "_tables.json"),
                   [{"key": t["key"], "name": t["name"], "rows": t["rows"]} for t in b["tables"]])

    # ---- attachments
    blobs = os.path.join(out, "attachments", "blobs")
    os.makedirs(blobs, exist_ok=True)
    manual_dir = os.path.join(out, "attachments", "manual_upload")
    manifest, per_cell = [], {}
    for it in att:
        data = it["data"]
        sha = hashlib.sha256(data).hexdigest()
        md5 = hashlib.md5(data).hexdigest()
        with open(os.path.join(blobs, sha + ".dat"), "wb") as fh:
            fh.write(data)
        if it["method"] == "manual":
            os.makedirs(manual_dir, exist_ok=True)
            with open(os.path.join(manual_dir, it["filename"]), "wb") as fh:
                fh.write(data)
        ck = (it["table"], it["row"], it["field"])
        per_cell[ck] = per_cell.get(ck, 0) + 1
        manifest.append({"base": baseof[it["table"]], "table": keyof[it["table"]]["name"], "table_key": it["table"],
                         "row": it["row"], "field": it["field"], "order": per_cell[ck], "filename": it["filename"],
                         "size": len(data), "mime": it["mime"], "sha256": sha, "md5": md5, "method": it["method"],
                         "dup_group": it["dup"], "note": it["note"], "blob": "attachments/blobs/%s.dat" % sha})
    # checksum-duplicate detection across the whole set
    by_sha = {}
    for m in manifest:
        by_sha.setdefault(m["sha256"], []).append(m)
    for sha, ms in by_sha.items():
        rec = {(m["table_key"], m["row"]) for m in ms}
        if len(ms) > 1 and len(ms) != len(rec) and not any(m["dup_group"] for m in ms):
            for m in ms:
                m["dup_group"] = "same-bytes"
    write_json(os.path.join(out, "attachments", "manifest.json"), manifest)
    ak = os.path.join(out, "answer_key")
    write_csv(os.path.join(ak, "expected_attachments.csv"),
              ["base", "table", "record", "field", "order_in_cell", "filename", "size_bytes", "mime_type", "sha256", "md5", "seed_method", "checksum_group_size", "dup_group", "note"],
              [[m["base"], m["table"], m["row"], m["field"], m["order"], m["filename"], m["size"], m["mime"], m["sha256"], m["md5"],
                m["method"], len(by_sha[m["sha256"]]), m["dup_group"], m["note"]] for m in manifest])

    # ---- profile
    prof = fc.profile(schema, raw, norm, att)
    cols = ["base", "table", "field", "field_type", "local_table_id", "local_field_id", "row_count", "null_count", "cardinality",
            "value_source", "alt_null_count_if_whitespace_trimmed", "field_exists", "flags", "notes"]
    write_csv(os.path.join(ak, "expected_profile.csv"), cols, [[r[c] for c in cols] for r in prof])

    # ---- load order + link treatment
    lo_cols = ["base", "table", "local_table_id", "load_no_within_base", "depth", "parent_tables", "in_cycle", "self_link", "cycle_members"]
    for mode, fn in (("resolve", "expected_load_order.csv"), ("literal", "expected_load_order_literal.csv")):
        rows = []
        for b in schema["bases"].values():
            lo, _ = fw_graph.load_order(b, mode)
            rows += [[r["base"], r["table"], r["local_table_id"], r["load_no"], r["depth"], r["parents"],
                      "yes" if r["in_cycle"] else "no", "yes" if r["self_link"] else "no", r["cycle_members"]] for r in lo]
        write_csv(os.path.join(ak, fn), lo_cols, rows)
    manual = {(bl, tn, fnm): st for bl, tn, fnm, st in manual_link_steps(schema)}
    lt = []
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        _, tr_res = fw_graph.load_order(b, "resolve")
        _, tr_lit = fw_graph.load_order(b, "literal")
        for t in b["tables"]:
            mx = {}
            for f in t["fields"]:
                lk = f.get("link")
                if not lk:
                    continue
                cells = [len(r.get(f["name"], [])) for r in norm[t["key"]]]
                a1, a2 = tr_res[(t["key"], f["name"])], tr_lit[(t["key"], f["name"])]
                inv = lk["inverse"]
                lt.append([b["label"], t["name"], f["name"], tmap[lk["target"]]["name"], "yes" if lk["is_inverse"] else "no",
                           "yes" if lk["single"] else "no", inv or "", max(cells or [0]), sum(1 for c in cells if c),
                           a1[0], a1[1], a1[2], a2[0], a2[1], a2[2], "; ".join(manual.get((b["label"], t["name"], f["name"]), []))])
    write_csv(os.path.join(ak, "expected_link_treatment.csv"),
              ["base", "table", "field", "links_to_table", "is_inverse_field", "prefers_single_record", "inverse_field", "max_links_in_a_cell",
               "non_empty_cells", "second_pass_resolve_mode", "reason_resolve_mode", "explanation_resolve_mode",
               "second_pass_literal_mode", "reason_literal_mode", "explanation_literal_mode", "manual_ui_steps_needed_after_api_seed"], lt)

    # ---- reports
    notes = legacy_check(schema, raw, norm)
    os.makedirs(os.path.join(out, "reports"), exist_ok=True)
    with open(os.path.join(out, "reports", "legacy_check.txt"), "w", encoding="utf-8") as fh:
        fh.write("Legacy preservation / recomputation check\n" + ("\n".join(notes) if notes else "all legacy values preserved; Margin and Purchase.Total recompute to the original values\n") + "\n")
    with open(os.path.join(out, "reports", "manual_steps.md"), "w", encoding="utf-8") as fh:
        fh.write("# Manual UI steps after the API seed\n\nGenerated. API-created link fields always get an inverse and allow multiple links, so:\n\n")
        for (bl, tn, fnm), st in manual.items():
            fh.write("- **%s / %s.%s**: %s\n" % (bl, tn, fnm, "; ".join(st)))
        fh.write("\n## Other manual items\n\n- Field Type Showcase.Button cannot be created via API; add a Button field by hand if you want that type present.\n")
        fh.write("- Attachment Lab row Lab ID att_18 (over 5 MB): upload `out/attachments/manual_upload/over_5mb.png` through the Airtable UI.\n")
        fh.write("- Delete the default empty table(s) Airtable puts in each new base (no delete-table endpoint is used).\n")
    summ = ["# Generation summary", "", "args: %s" % json.dumps(cfg), ""]
    for b in schema["bases"].values():
        summ.append("## %s (%s): %d tables, %d fields, %d rows" % (b["label"], b["name"], len(b["tables"]),
                    sum(len(t["fields"]) for t in b["tables"]), sum(t["rows"] for t in b["tables"])))
        for t in b["tables"]:
            summ.append("- %s: %d rows, %d fields" % (t["name"], t["rows"], len(t["fields"])))
    summ.append("")
    summ.append("attachments: %d files, %d bytes total" % (len(manifest), sum(m["size"] for m in manifest)))
    with open(os.path.join(out, "reports", "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(summ) + "\n")
    print("\n".join(summ[:3]))
    for b in schema["bases"].values():
        print(b["label"], len(b["tables"]), "tables", sum(len(t["fields"]) for t in b["tables"]), "fields", sum(t["rows"] for t in b["tables"]), "rows")
    print("attachments:", len(manifest), "files")
    print("legacy check:", "OK" if not notes else "%d notes (see out/reports/legacy_check.txt)" % len(notes))


if __name__ == "__main__":
    main()
