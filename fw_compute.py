"""Normalisation (what Airtable will actually store), inverse links, computed fields and the expected profile."""
import json

from fw_schema import ERR

TEXTY = ("singleLineText", "multilineText", "richText", "email", "url", "phoneNumber")
OBSERVED = ("created", "modified", "createdby", "modifiedby", "button")


def is_ws(v):
    return isinstance(v, str) and v != "" and v.strip() == ""


def norm_value(f, v):
    t = f["type"]
    if v is None:
        return None
    if t in TEXTY or t in ("singleSelect", "singleCollaborator", "date", "dateTime"):
        return None if v == "" else v
    if t in ("number", "currency"):
        p = f["options"].get("precision", 0)
        x = round(float(v), p)
        return int(x) if p == 0 else (0.0 if x == 0 else x)
    if t == "percent":
        x = round(float(v), f["options"].get("precision", 0) + 2)
        return 0.0 if x == 0 else x
    if t == "rating":
        return None if not v else int(v)
    if t == "duration":
        return int(v)
    if t == "checkbox":
        return True if v else None
    if t in ("multipleSelects", "multipleCollaborators", "multipleRecordLinks"):
        out = list(dict.fromkeys(x for x in v if x not in ("", None)))
        return out or None
    return v


def normalize(schema, rows):
    out = {}
    for b in schema["bases"].values():
        for t in b["tables"]:
            fm = t["by_name"]
            res = []
            for r in rows[t["key"]]:
                n = {}
                for k, v in r.items():
                    if k not in fm:
                        raise KeyError("generated field %r not in schema table %s" % (k, t["name"]))
                    nv = norm_value(fm[k], v)
                    if nv is not None:
                        n[k] = nv
                res.append(n)
            out[t["key"]] = res
    return out


def fill_inverse(schema, nrows):
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        for t in b["tables"]:
            for f in t["fields"]:
                lk = f.get("link")
                if not lk or lk["is_inverse"] or not lk["inverse"]:
                    continue
                pk = t["primary"]
                acc = {}
                for r in nrows[t["key"]]:
                    for tgt in r.get(f["name"], []):
                        acc.setdefault(tgt, []).append(r[pk])
                tt = tmap[lk["target"]]
                for r in nrows[tt["key"]]:
                    v = acc.get(r[tt["primary"]])
                    if v:
                        r[lk["inverse"]] = list(dict.fromkeys(v))


def fill_computed(schema, nrows):
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        for t in b["tables"]:
            idx = {}
            for f in t["fields"]:
                c = f.get("calc")
                if not c:
                    continue
                kind = c["kind"]
                for i, r in enumerate(nrows[t["key"]], 1):
                    if kind == "autonumber":
                        r[f["name"]] = i
                    elif kind == "formula":
                        v = c["fn"](r)
                        if v is not None:
                            r[f["name"]] = v
                    elif kind in ("rollup", "lookup", "count"):
                        lf = t["by_name"][c["link"]]
                        tgt = tmap[lf["link"]["target"]]
                        if tgt["key"] not in idx:
                            idx[tgt["key"]] = {x[tgt["primary"]]: x for x in nrows[tgt["key"]]}
                        linked = [idx[tgt["key"]][k] for k in r.get(c["link"], [])]
                        if kind == "count":
                            r[f["name"]] = len(linked)
                        else:
                            vals = [x.get(c["field"]) for x in linked if x.get(c["field"]) is not None]
                            if kind == "rollup":
                                r[f["name"]] = round(sum(vals), 8) if vals else 0
                            elif vals:
                                r[f["name"]] = vals


def is_null(f, v):
    if f["type"] == "checkbox":
        return False
    return v is None or v == "" or v == [] or v == {}


def canon(v):
    if isinstance(v, bool):
        return "b:%s" % v
    if isinstance(v, (int, float)):
        return "n:%r" % float(v)
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def profile(schema, raw, norm, att):
    """Rows for expected_profile.csv."""
    att_cells = {}
    for a in att:
        if a["method"] != "rejected":              # files Airtable refuses to store never appear in a cell
            att_cells.setdefault((a["table"], a["row"], a["field"]), []).append(a)
    out = []
    for b in schema["bases"].values():
        for t in b["tables"]:
            n = len(norm[t["key"]])
            pk = t["primary"]
            for f in t["fields"]:
                name, ty = f["name"], f["type"]
                lk, calc = f.get("link"), f.get("calc")
                flags, notes = [], []
                alt_null = ""
                if ty == "multipleAttachments":
                    cells = [att_cells.get((t["key"], r[pk], name), []) for r in norm[t["key"]]]
                    nn = sum(1 for c in cells if c)
                    null, card, src = n - nn, nn, "attachment_upload"
                    flags.append("ATTACH_CARDINALITY_IS_NONNULL_CELLS")
                    notes.append("attachment ids are unique per cell, so cardinality should equal non-null cells; files in expected_attachments.csv")
                    if any(a["method"] == "manual" for c in cells for a in c):
                        flags.append("HAS_MANUAL_UPLOAD")
                    if any(a["method"] == "try" for c in cells for a in c):
                        flags.append("HAS_TRY_UPLOAD")
                    if any(a["method"] == "rejected" and (a["table"], a["field"]) == (t["key"], name) for a in att):
                        flags.append("HAS_REJECTED_UPLOAD")
                        notes.append("a file Airtable rejects (zero bytes) is listed in expected_attachments.csv as seed_method=rejected; its cell stays empty, which is counted in null_count")
                elif calc and calc["kind"] in OBSERVED:
                    null = 0 if calc["kind"] != "button" else ""
                    card = ""
                    src = "observed"
                    flags.append("OBSERVED_NOT_COMPUTED")
                    if calc["kind"] == "button":
                        flags.append("API_CREATE_MANUAL")
                        notes.append("button cells carry no seeded data; observe what the API returns")
                    else:
                        notes.append("value set by Airtable at seed time (token owner / timestamps); only row_count and null_count are predictable")
                else:
                    vals = [r.get(name) for r in norm[t["key"]]]
                    rawv = [r.get(name) for r in raw[t["key"]]]
                    null = sum(1 for v in vals if is_null(f, v))
                    if ty == "checkbox":
                        flags.append("CHECKBOX_MISSING_IS_FALSE")
                        notes.append("API omits unchecked boxes; tool must treat missing as false (not null)")
                        card = len({bool(v) for v in vals})
                    else:
                        card = len({canon(v) for v in vals if not is_null(f, v)})
                    src = "seeded"
                    if calc:
                        src = "computed_locally"
                        flags.append("COMPUTED_FIELD_EXPECTED_VALUE_IS_LOCAL_EMULATION")
                        if calc["kind"] == "rollup":
                            flags += ["ROLLUP_EMPTY_IS_ZERO", "FLOAT_NOISE_POSSIBLE"]
                            notes.append("SUM over no links is 0 (a real value, not null); compare floats with tolerance")
                        if calc["kind"] == "lookup":
                            flags.append("LOOKUP_EMPTY_ARRAY_OR_MISSING")
                            notes.append("lookup over no links may arrive as [] or be omitted; both are null under the tool's rules")
                        if calc["kind"] == "formula" and any(v == ERR for v in vals):
                            flags.append("FORMULA_ERROR_VALUE")
                            notes.append("division by zero yields an error value (shape unverified: {'error': '#ERROR!'}?); counted as non-null here; verify live")
                        if calc["kind"] == "autonumber":
                            notes.append("assumes records are created in table row order by a single uninterrupted seed run")
                    if lk and lk["is_inverse"]:
                        src = "derived_inverse"
                        flags.append("INVERSE_FIELD_AUTO_POPULATED")
                        notes.append("Airtable fills this from the forward side; never seeded directly")
                    if lk:
                        if any(len(v) > 1 for v in vals if v):
                            flags.append("LINK_ARRAY_ORDER_UNCERTAIN")
                        if any(len(v) != len(set(v)) for v in rawv if isinstance(v, list)):
                            flags.append("RAW_DUPLICATE_LINKS_COLLAPSED")
                        mx = max([len(v) for v in vals if v] or [0])
                        notes.append("max links in one cell: %d" % mx)
                    # normalisation differences
                    kinds = set()
                    for v, nv in zip(rawv, vals):
                        if v == "" and nv is None:
                            kinds.add("empty-string")
                        if v == [] and nv is None:
                            kinds.add("empty-array")
                        if ty == "rating" and v == 0:
                            kinds.add("rating-0")
                        if ty == "checkbox" and v is False:
                            kinds.add("false")
                    if kinds:
                        flags.append("EMPTY_REPR_NORMALIZED(%s)" % "+".join(sorted(kinds)))
                        notes.append("Airtable stores these as missing; raw and normalized null counts agree under the tool's rules")
                    ws = sum(1 for v in vals if is_ws(v))
                    if ws:
                        flags.append("WHITESPACE_ONLY_UNCERTAIN")
                        alt_null = null + ws
                        notes.append("%d whitespace-only value(s) are NOT null by the stated rule; Airtable may trim them (then null_count=%d)" % (ws, alt_null))
                    if ty in ("number", "currency", "percent"):
                        rk = {canon(v) for v in rawv if v is not None}
                        nk = {canon(v) for v in vals if v is not None}
                        if len(rk) != len(nk):
                            flags.append("PRECISION_ROUNDING_MERGES_VALUES")
                            notes.append("field precision rounds distinct raw values together (%d raw vs %d stored)" % (len(rk), len(nk)))
                    if ty == "singleSelect":
                        ch = {c["name"] for c in f["options"]["choices"]}
                        new = [v for v in vals if v and v not in ch]
                        if new:
                            flags.append("TYPECAST_ADDS_CHOICE")
                            notes.append("%d value(s) not in choices (%s): seed uses typecast, so live schema gains a choice" % (len(new), ", ".join(sorted(set(new)))))
                    if ty in ("singleCollaborator", "multipleCollaborators"):
                        flags.append("NEEDS_REAL_COLLABORATORS")
                        notes.append("counts assume seed_config.json supplies %s collaborator emails; cardinality is by placeholder identity" % "collab_count")
                    if ty in ("date", "dateTime") and ty == "dateTime":
                        flags.append("API_RETURNS_UTC_ISO")
                    if ty == "barcode":
                        flags.append("OBJECT_VALUE")
                api = f.get("api")
                if api == "try":
                    flags.append("API_CREATE_UNVERIFIED")
                if api == "manual" and not (lk and lk["is_inverse"]):
                    flags.append("API_CREATE_MANUAL")
                exists = "no" if f.get("confirmed_rejected") else ("maybe" if f.get("naming_try") else "yes")
                if f.get("confirmed_rejected"):
                    flags.append("NAME_REJECTED_BY_AIRTABLE")
                elif f.get("naming_try"):
                    flags.append("NAME_MAY_BE_REJECTED")
                if f.get("note"):
                    notes.append(f["note"])
                out.append({"base": b["label"], "table": t["name"], "field": name, "field_type": ty,
                            "local_table_id": t["id"], "local_field_id": f["id"], "row_count": n, "null_count": null,
                            "cardinality": card, "value_source": src, "alt_null_count_if_whitespace_trimmed": alt_null,
                            "field_exists": exists, "flags": ";".join(flags), "notes": " | ".join(notes)})
    return out
