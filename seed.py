#!/usr/bin/env python3
"""Seed the TRIAL Airtable bases through the Web API (standard library only).

    python seed.py --phase preflight          # token + base-name safety check, no writes
    python seed.py --phase schema             # tables, fields, link fields (+ renames inverse fields), computed fields
    ... do the manual UI steps in out/reports/manual_steps.md, then `python verify_live_schema.py` ...
    python seed.py --phase records            # idempotent upserts keyed on each table's primary field
    python seed.py --phase links              # second pass: link cells via the local-key -> record-id map
    python seed.py --phase attachments        # uploadAttachment, one request per file
    python seed.py --phase all                # everything above in order
    python seed.py --dry-run --phase all      # offline: counts of requests, no network

Safety: reads the WRITE token only from seed_config.json (gitignored). The token is never printed or logged.
It refuses to touch any base whose name does not start with the trial prefix (default "TRIAL").
Verified against Airtable docs on 2026-11-08: 10 records per create/update request, 5 requests/s per base,
429 => wait 30 s, upload attachment = POST content.airtable.com/v0/{base}/{record}/{field}/uploadAttachment
(base64, file bytes <= 5 MB), create base = POST /v0/meta/bases.
"""
import argparse
import base64
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fw_schema import build_schema  # noqa: E402

OUT = os.path.join(HERE, "out")
API = "https://api.airtable.com"
CONTENT = "https://content.airtable.com"
LOG_PATH = os.path.join(HERE, "seed_log.json")
CALLS_PATH = os.path.join(HERE, "seed_calls.log")
BATCH = 10


class Fatal(Exception):
    pass


def load_config():
    p = os.path.join(HERE, "seed_config.json")
    if not os.path.exists(p):
        raise Fatal("seed_config.json not found. Copy seed_config.example.json and fill it in (the file is gitignored).")
    cfg = json.load(open(p, encoding="utf-8"))
    for k in ("token", "bases"):
        if not cfg.get(k):
            raise Fatal("seed_config.json is missing %r" % k)
    cfg.setdefault("trial_prefix", "TRIAL")
    cfg.setdefault("requests_per_second", 4.5)
    cfg.setdefault("collaborator_emails", [])
    return cfg


class Api:
    def __init__(self, cfg, dry=False):
        self._token = cfg["token"]                 # never printed, logged or put in exceptions
        self.min_gap = 1.0 / float(cfg["requests_per_second"])
        self.last = {}
        self.dry = dry
        self.counts = {}

    def call(self, method, url, bucket, body=None, tries=7):
        if self.dry:
            self.counts[bucket] = self.counts.get(bucket, 0) + 1
            return 200, {}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(tries):
            wait = self.min_gap - (time.time() - self.last.get(bucket, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[bucket] = time.time()
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", "Bearer " + self._token)
            if data is not None:
                req.add_header("Content-Type", "application/json")
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    status, raw = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, raw = e.code, e.read()
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                status, raw = 599, str(type(e).__name__).encode()
            self._log(method, url, status, time.time() - t0)
            if status == 429:
                print("  429 from Airtable: waiting 30 s (documented penalty)")
                time.sleep(30)
                continue
            if status >= 500:
                time.sleep(min(60, 2 ** attempt) + random.random())
                continue
            try:
                js = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                js = {"raw": raw[:200].decode("utf-8", "replace")}
            return status, js
        return 599, {"error": "gave up after %d tries" % tries}

    @staticmethod
    def _log(method, url, status, secs):
        path = re.sub(r"\?.*", "", url.split("//", 1)[1].split("/", 1)[1])
        with open(CALLS_PATH, "a", encoding="utf-8") as fh:
            fh.write("%s %s /%s %d %.2fs\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), method, path, status, secs))


def err_text(js):
    e = js.get("error") if isinstance(js, dict) else None
    if isinstance(e, dict):
        return "%s: %s" % (e.get("type", ""), (e.get("message") or "")[:200])
    return str(e or js)[:200]


# ------------------------------------------------------------------ seed log (resumable state)
def load_log():
    if os.path.exists(LOG_PATH):
        return json.load(open(LOG_PATH, encoding="utf-8"))
    return {"records": {}, "links_done": {}, "attachments_done": {}, "failed_fields": [], "failed_records": [], "failed_attachments": [], "tables": {}}


DRY = False


def save_log(log):
    if DRY:
        return
    tmp = LOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1)
    os.replace(tmp, LOG_PATH)


# ------------------------------------------------------------------ field option mapping for creation
def create_options(f):
    t, o = f["type"], f["options"]
    if t in ("singleSelect", "multipleSelects"):
        return {"choices": [{"name": c["name"], "color": c["color"]} for c in o["choices"]]}
    if t == "date":
        return {"dateFormat": {"name": "iso"}}
    if t == "dateTime":
        return {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}, "timeZone": o["timeZone"]}
    if t in ("number", "percent", "currency", "rating", "duration", "checkbox"):
        return dict(o)
    return None


def field_payload(f):
    d = {"name": f["name"], "type": f["type"]}
    o = create_options(f)
    if o:
        d["options"] = o
    return d


def _fail(log, entry):
    log["failed_fields"] = [e for e in log["failed_fields"] if (e["base"], e["table"], e["field"]) != (entry["base"], entry["table"], entry["field"])]
    log["failed_fields"].append(entry)


# ------------------------------------------------------------------ preflight
def preflight(api, cfg, schema):
    if api.dry:
        print("dry-run: skipping live checks")
        return {}
    st, js = api.call("GET", API + "/v0/meta/bases", "meta")
    if st != 200:
        raise Fatal("cannot list bases (status %d: %s). The token needs scope schema.bases:read." % (st, err_text(js)))
    names = {b["id"]: b["name"] for b in js.get("bases", [])}
    for label, bid in cfg["bases"].items():
        if label not in schema["bases"]:
            raise Fatal("unknown base label %r in seed_config.json (expected ff_main / ff_ops)" % label)
        if bid not in names:
            raise Fatal("base %s (%s) is not visible to this token" % (label, bid))
        if not names[bid].startswith(cfg["trial_prefix"]):
            raise Fatal("REFUSING: base %s is named %r, which does not start with %r. Rename the trial base or fix the config."
                        % (label, names[bid], cfg["trial_prefix"]))
        print("ok  %s -> base named %r" % (label, names[bid]))
    return names


def live_tables(api, bid):
    st, js = api.call("GET", "%s/v0/meta/bases/%s/tables" % (API, bid), bid)
    if st != 200:
        raise Fatal("cannot read schema of %s: %d %s" % (bid, st, err_text(js)))
    return {t["name"]: t for t in js["tables"]}


# ------------------------------------------------------------------ phase: schema
def phase_schema(api, cfg, schema, log):
    for label, bid in cfg["bases"].items():
        base = schema["bases"][label]
        print("== schema %s" % label)
        live = {} if api.dry else live_tables(api, bid)
        # 1. tables with plain fields
        for t in base["tables"]:
            if t["name"] in live:
                continue
            fields = [field_payload(t["by_name"][t["primary"]])]
            for f in t["fields"][1:]:
                if f.get("link") or f.get("calc") or f["api"] != "ok" or f.get("naming_try"):
                    continue
                if f["type"] == "multipleAttachments":
                    fields.append({"name": f["name"], "type": "multipleAttachments"})
                else:
                    fields.append(field_payload(f))
            st, js = api.call("POST", "%s/v0/meta/bases/%s/tables" % (API, bid), bid, {"name": t["name"], "fields": fields})
            if st != 200:
                raise Fatal("create table %s failed: %d %s" % (t["name"], st, err_text(js)))
            live[t["name"]] = js
            print("  table %-28s %d fields" % (t["name"], len(fields)))
        if api.dry:
            n_links = sum(1 for t in base["tables"] for f in t["fields"] if f.get("link") and not f["link"]["is_inverse"])
            n_try = sum(1 for t in base["tables"] for f in t["fields"] if not f.get("link") and (f.get("calc") or f["api"] == "try" or f.get("naming_try")))
            print("  dry-run: %d tables, %d link fields (+inverse renames), %d extra field calls" % (len(base["tables"]), n_links, n_try))
            api.counts[bid] = api.counts.get(bid, 0) + n_links * 2 + n_try
            continue
        # refresh ids
        live = live_tables(api, bid)
        for t in base["tables"]:
            log["tables"].setdefault(label, {})[t["key"]] = live[t["name"]]["id"]
        # 2. optional-type plain fields
        for t in base["tables"]:
            lt = live[t["name"]]
            have = {f["name"] for f in lt["fields"]}
            for f in t["fields"]:
                if f.get("link") or f.get("calc") or f["name"] in have:
                    continue
                if f["api"] in ("ok", "try") or f.get("naming_try"):   # also re-creates plain fields deleted later
                    st, js = api.call("POST", "%s/v0/meta/bases/%s/tables/%s/fields" % (API, bid, lt["id"]), bid, field_payload(f))
                    if st != 200:
                        _fail(log, {"base": label, "table": t["name"], "field": f["name"], "type": f["type"], "why": err_text(js)})
                        print("  could not create %s.%s (%s): %s" % (t["name"], f["name"], f["type"], err_text(js)))
        save_log(log)
        # 3. link fields
        live = live_tables(api, bid)
        for t in base["tables"]:
            lt = live[t["name"]]
            for f in t["fields"]:
                lk = f.get("link")
                if not lk or lk["is_inverse"]:
                    continue
                tgt = [x for x in base["tables"] if x["key"] == lk["target"]][0]
                cur = {x["name"]: x for x in lt["fields"]}
                if f["name"] not in cur:
                    st, js = api.call("POST", "%s/v0/meta/bases/%s/tables/%s/fields" % (API, bid, lt["id"]), bid,
                                      {"name": f["name"], "type": "multipleRecordLinks", "options": {"linkedTableId": live[tgt["name"]]["id"]}})
                    if st != 200:
                        _fail(log, {"base": label, "table": t["name"], "field": f["name"], "type": "multipleRecordLinks", "why": err_text(js)})
                        print("  link %s.%s failed: %s" % (t["name"], f["name"], err_text(js)))
                        continue
                    fld = js
                else:
                    fld = cur[f["name"]]
                inv_id = (fld.get("options") or {}).get("inverseLinkFieldId")
                if inv_id:
                    want = lk["inverse"] or ("__delete_me__ %s.%s" % (t["name"], f["name"]))
                    tt = lt if tgt["key"] == t["key"] else live[tgt["name"]]
                    cur_inv = [x for x in tt["fields"] if x["id"] == inv_id]
                    if not cur_inv or cur_inv[0]["name"] != want:
                        st, js = api.call("PATCH", "%s/v0/meta/bases/%s/tables/%s/fields/%s" % (API, bid, tt["id"], inv_id), bid, {"name": want})
                        if st != 200:
                            _fail(log, {"base": label, "table": tgt["name"], "field": want, "type": "inverse rename", "why": err_text(js)})
            print("  links done for %s" % t["name"])
        save_log(log)
        # 4. computed fields (all 'try')
        live = live_tables(api, bid)
        for t in base["tables"]:
            lt = live[t["name"]]
            cur = {x["name"]: x["id"] for x in lt["fields"]}
            for f in t["fields"]:
                c = f.get("calc")
                if not c or f["name"] in cur:
                    continue
                k = c["kind"]
                body = {"name": f["name"], "type": f["type"]}
                if k == "formula":
                    body["options"] = {"formula": re.sub(r"\{([^}]+)\}", lambda m: "{%s}" % cur.get(m.group(1), m.group(1)), f["options"]["formula"])}
                elif k in ("rollup", "lookup", "count"):
                    lf = cur.get(c["link"])
                    opt = {"recordLinkFieldId": lf}
                    if k != "count":
                        tgt = [x for x in base["tables"] if x["key"] == t["by_name"][c["link"]]["link"]["target"]][0]
                        opt["fieldIdInLinkedTable"] = {x["name"]: x["id"] for x in live[tgt["name"]]["fields"]}.get(c["field"])
                    if k == "rollup":
                        opt["formula"] = "SUM(values)"      # API validation: options.formula is required for rollups
                    body["options"] = opt
                elif k == "modified":
                    body["options"] = {"referencedFieldIds": []}   # API validation rejects 'result' here; [] = all fields
                elif k == "created":
                    pass                                        # API validation: createdTime takes no options
                elif k == "button":
                    continue
                st, js = api.call("POST", "%s/v0/meta/bases/%s/tables/%s/fields" % (API, bid, lt["id"]), bid, body)
                if st != 200:
                    _fail(log, {"base": label, "table": t["name"], "field": f["name"], "type": f["type"], "why": err_text(js)})
                    print("  computed %s.%s (%s) not created: %s" % (t["name"], f["name"], f["type"], err_text(js)))
        save_log(log)
        now = live_tables(api, bid)
        log["failed_fields"] = [e for e in log["failed_fields"]
                                if not (e["base"] == label and e["field"] in {f["name"] for f in now.get(e["table"], {}).get("fields", [])})]
        save_log(log)
    if not api.dry:
        print("\nschema phase finished. Failed/unsupported fields so far: %d (see seed_log.json 'failed_fields')." % len(log["failed_fields"]))
        print("NEXT: do the manual UI steps in out/reports/manual_steps.md, then run verify_live_schema.py")


# ------------------------------------------------------------------ helpers shared by later phases
def live_map(api, cfg, schema, log):
    out = {}
    for label, bid in cfg["bases"].items():
        live = {} if api.dry else live_tables(api, bid)
        for t in schema["bases"][label]["tables"]:
            lt = live.get(t["name"])
            if not lt and not api.dry:
                raise Fatal("table %r missing in %s: run --phase schema first" % (t["name"], label))
            fm = {}
            if lt:
                for f in lt["fields"]:
                    fm[f["name"]] = f
            out[(label, t["key"])] = (lt["id"] if lt else "tbl_dry", fm)
    return out


def read_jsonl(label, key):
    p = os.path.join(OUT, "seed_payload", label, "%s.jsonl" % key)
    return [json.loads(x) for x in open(p, encoding="utf-8")]


def live_name(fm, name):
    if name in fm:
        return name
    for k in fm:
        if k.strip() == name.strip():
            return k
    return None


def collab_value(placeholder, cfg):
    m = re.match(r"collab(\d+)@example\.com$", placeholder)
    if not m:
        return None
    i = int(m.group(1)) - 1
    em = cfg["collaborator_emails"]
    return {"email": em[i]} if i < len(em) else None


# ------------------------------------------------------------------ phase: records (idempotent upsert on primary field)
def phase_records(api, cfg, schema, log):
    lm = live_map(api, cfg, schema, log)
    for label, bid in cfg["bases"].items():
        base = schema["bases"][label]
        for t in base["tables"]:
            tid, fm = lm[(label, t["key"])]
            rows = read_jsonl(label, t["key"])
            done = log["records"].setdefault("%s/%s" % (label, t["key"]), {})
            log["failed_records"] = [e for e in log["failed_records"]
                                     if not (e.get("phase") is None and e["base"] == label and e["table"] == t["name"] and e.get("key") in done)]
            todo = [r for r in rows if r["key"] not in done]
            print("records %-28s %4d to do (%d already logged)" % (t["name"], len(todo), len(rows) - len(todo)))
            pname = live_name(fm, t["primary"]) or t["primary"]
            ftype = {f["name"]: f["type"] for f in t["fields"]}
            for i in range(0, len(todo), BATCH):
                chunk = todo[i:i + BATCH]
                recs = []
                for r in chunk:
                    fields = {}
                    for k, v in r["fields"].items():
                        ln = live_name(fm, k) if not api.dry else k
                        if not ln:
                            continue
                        if ftype[k] == "singleCollaborator":
                            v = collab_value(v, cfg)
                            if v is None:
                                continue
                        elif ftype[k] == "multipleCollaborators":
                            v = [x for x in (collab_value(p, cfg) for p in v) if x]
                            if not v:
                                continue
                        fields[ln] = v
                    fields[pname] = r["key"]
                    recs.append({"fields": fields})
                body = {"performUpsert": {"fieldsToMergeOn": [pname]}, "typecast": True, "records": recs}
                st, js = api.call("PATCH", "%s/v0/%s/%s" % (API, bid, tid), bid, body)
                if st == 200 and not api.dry:
                    for r, rec in zip(chunk, js["records"]):
                        done[r["key"]] = rec["id"]
                elif st != 200:
                    for r, one in zip(chunk, recs):          # isolate the bad record(s)
                        st1, js1 = api.call("PATCH", "%s/v0/%s/%s" % (API, bid, tid), bid,
                                            {"performUpsert": {"fieldsToMergeOn": [pname]}, "typecast": True, "records": [one]})
                        if st1 == 200:
                            done[r["key"]] = js1["records"][0]["id"]
                        else:
                            log["failed_records"].append({"base": label, "table": t["name"], "key": r["key"], "why": err_text(js1)})
                            print("  record %s/%s failed: %s" % (t["name"], r["key"], err_text(js1)))
                if (i // BATCH) % 10 == 9:
                    save_log(log)
            save_log(log)


# ------------------------------------------------------------------ phase: links (second pass)
def phase_links(api, cfg, schema, log):
    lm = live_map(api, cfg, schema, log)
    for label, bid in cfg["bases"].items():
        base = schema["bases"][label]
        tmap = {t["key"]: t for t in base["tables"]}
        for t in base["tables"]:
            tid, fm = lm[(label, t["key"])]
            rows = [r for r in read_jsonl(label, t["key"]) if r["links"]]
            if not rows:
                continue
            ids = log["records"].get("%s/%s" % (label, t["key"]), {})
            done = log["links_done"].setdefault("%s/%s" % (label, t["key"]), [])
            doneset = set(done)
            log["failed_records"] = [e for e in log["failed_records"]
                                     if not (e.get("phase") == "links" and e["base"] == label and e["table"] == t["name"]
                                             and set(e["keys"]) <= doneset)]
            todo = [r for r in rows if r["key"] not in doneset and r["key"] in ids]
            print("links   %-28s %4d records with links to set" % (t["name"], len(todo)))
            for i in range(0, len(todo), BATCH):
                chunk = todo[i:i + BATCH]
                recs = []
                for r in chunk:
                    fields = {}
                    for fname, keys in r["links"].items():
                        tgt = tmap[t["by_name"][fname]["link"]["target"]]
                        tids = log["records"].get("%s/%s" % (label, tgt["key"]), {})
                        arr = [tids[k] for k in keys if k in tids]
                        if arr:
                            fields[live_name(fm, fname) or fname] = arr
                    if fields:
                        recs.append({"id": ids[r["key"]], "fields": fields})
                if not recs:
                    continue
                st, js = api.call("PATCH", "%s/v0/%s/%s" % (API, bid, tid), bid, {"records": recs})
                if st == 200:
                    done.extend(r["key"] for r in chunk)
                    gone = {r["key"] for r in chunk}
                    log["failed_records"] = [e for e in log["failed_records"]
                                             if not (e.get("phase") == "links" and e["base"] == label and e["table"] == t["name"]
                                                     and set(e["keys"]) <= (doneset | gone))]
                else:
                    log["failed_records"].append({"base": label, "table": t["name"], "phase": "links", "keys": [r["key"] for r in chunk], "why": err_text(js)})
                    print("  link batch failed in %s: %s" % (t["name"], err_text(js)))
                if (i // BATCH) % 10 == 9:
                    save_log(log)
            save_log(log)


# ------------------------------------------------------------------ phase: attachments
def phase_attachments(api, cfg, schema, log):
    lm = live_map(api, cfg, schema, log)
    man = json.load(open(os.path.join(OUT, "attachments", "manifest.json"), encoding="utf-8"))
    n_done = 0
    for m in man:
        if m["base"] not in cfg["bases"]:
            continue
        if m["method"] == "manual":
            continue
        k = "%s|%s|%s|%d" % (m["table_key"], m["row"], m["field"], m["order"])
        if k in log["attachments_done"]:
            continue
        bid = cfg["bases"][m["base"]]
        tid, fm = lm[(m["base"], m["table_key"])]
        rid = log["records"].get("%s/%s" % (m["base"], m["table_key"]), {}).get(m["row"])
        if not rid and not api.dry:
            continue
        fld = fm.get(m["field"]) if not api.dry else {"id": "fld_dry"}
        if not fld:
            continue
        data = open(os.path.join(OUT, m["blob"]), "rb").read()
        if len(data) > 5 * 1024 * 1024:
            continue
        body = {"contentType": m["mime"], "filename": m["filename"], "file": base64.b64encode(data).decode("ascii")}
        st, js = api.call("POST", "%s/v0/%s/%s/%s/uploadAttachment" % (CONTENT, bid, rid or "rec_dry", fld["id"]), bid, body)
        if st == 200:
            log["attachments_done"][k] = True
            n_done += 1
        else:
            log["failed_attachments"].append({"file": m["filename"][:60], "table": m["table"], "row": m["row"], "method": m["method"], "why": err_text(js)})
            print("  upload failed %s (%s): %s" % (m["filename"][:40], m["method"], err_text(js)))
        if n_done % 25 == 24:
            save_log(log)
    save_log(log)
    print("attachments uploaded this run: %d" % n_done)


# ------------------------------------------------------------------ phase: adopt (table loaded by hand, e.g. CSV import)
def phase_adopt(api, cfg, schema, log, names, with_links):
    lm = live_map(api, cfg, schema, log)
    for label, bid in cfg["bases"].items():
        for t in schema["bases"][label]["tables"]:
            if t["name"] not in names:
                continue
            tid, fm = lm[(label, t["key"])]
            rows = read_jsonl(label, t["key"])
            pname = live_name(fm, t["primary"]) or t["primary"]
            tmap = {x["key"]: x for x in schema["bases"][label]["tables"]}
            link_fields = sorted({f for r in rows for f in r["links"]}) if with_links else []
            got, live_links, offset = {}, {}, None
            while not api.dry:
                q = "?pageSize=100&fields%5B%5D=" + urllib.parse.quote(pname)
                q += "".join("&fields%5B%5D=" + urllib.parse.quote(live_name(fm, f) or f) for f in link_fields)
                q += ("&offset=" + offset if offset else "")
                st, js = api.call("GET", "%s/v0/%s/%s%s" % (API, bid, tid, q), bid)
                if st != 200:
                    raise Fatal("cannot read %s: %s" % (t["name"], err_text(js)))
                for r in js["records"]:
                    k = r["fields"].get(pname, "")
                    got[k] = r["id"]
                    live_links[k] = {f: r["fields"].get(live_name(fm, f) or f, []) for f in link_fields}
                offset = js.get("offset")
                if not offset:
                    break
            want = {r["key"] for r in rows}
            missing, extra = sorted(want - set(got)), sorted(set(got) - want)
            print("adopt %-24s live %d, expected %d, missing %d, unexpected %d" % (t["name"], len(got), len(want), len(missing), len(extra)))
            if missing[:5]:
                print("   missing e.g.", missing[:5])
            if extra[:5]:
                print("   unexpected e.g.", extra[:5])
            log["records"]["%s/%s" % (label, t["key"])] = {k: v for k, v in got.items() if k in want}
            if with_links:
                good, bad = [], []
                for r in rows:
                    if r["key"] not in got:
                        continue
                    ok = True
                    for f in link_fields:
                        tgt = tmap[t["by_name"][f]["link"]["target"]]
                        rev = {v: k for k, v in log["records"].get("%s/%s" % (label, tgt["key"]), {}).items()}
                        have = {rev.get(i, "?" + i) for i in live_links[r["key"]].get(f, [])}
                        if have != set(r["links"].get(f, [])):
                            ok = False
                            if len(bad) < 8:
                                print("   link mismatch %s.%s: expected %s, live %s" % (r["key"], f, sorted(r["links"].get(f, [])), sorted(have)))
                    (good if ok else bad).append(r["key"])
                print("   links: %d rows match, %d mismatch" % (len(good), len(bad)))
                if bad and any(not log["records"].get("%s/%s" % (label, tmap[t["by_name"][f]["link"]["target"]]["key"])) for f in link_fields):
                    print("   NOTE: a linked table has no logged record IDs yet; adopt or seed it first so link IDs can be translated")
                log["links_done"]["%s/%s" % (label, t["key"])] = good
            save_log(log)
            if missing:
                print("   NOTE: missing rows are not marked done; --phase records will upsert just those")


# ------------------------------------------------------------------ check attachments already present (manual uploads, earlier runs)
def phase_check_attachments(api, cfg, schema, log, accept_existing=False):
    lm = live_map(api, cfg, schema, log)
    man = json.load(open(os.path.join(OUT, "attachments", "manifest.json"), encoding="utf-8"))
    tot = {"expected": 0, "present": 0, "missing": 0, "extra": 0, "accepted_as_yours": 0}
    live_rows = []
    for label, bid in cfg["bases"].items():
        groups = {}
        for m in man:
            if m["base"] == label:
                groups.setdefault((m["table_key"], m["table"]), []).append(m)
        for (tkey, tname), items in groups.items():
            tid, fm = lm[(label, tkey)]
            t = [x for x in schema["bases"][label]["tables"] if x["key"] == tkey][0]
            pname = live_name(fm, t["primary"]) or t["primary"]
            fields = sorted({m["field"] for m in items})
            live = {}
            offset = None
            while not api.dry:
                q = "?pageSize=100&fields%5B%5D=" + urllib.parse.quote(pname)
                q += "".join("&fields%5B%5D=" + urllib.parse.quote(live_name(fm, f) or f) for f in fields)
                q += ("&offset=" + offset if offset else "")
                st, js = api.call("GET", "%s/v0/%s/%s%s" % (API, bid, tid, q), bid)
                if st != 200:
                    raise Fatal("cannot read %s: %s" % (tname, err_text(js)))
                for r in js["records"]:
                    live[r["fields"].get(pname, "")] = r["fields"]
                offset = js.get("offset")
                if not offset:
                    break
            present = missing = extra = 0
            notes = []
            cells = {}
            for m in items:
                cells.setdefault((m["row"], m["field"]), []).append(m)
            for (row, field), exp in sorted(cells.items()):
                atts = live.get(row, {}).get(live_name(fm, field) or field, [])
                have = [(a.get("filename"), a.get("size")) for a in atts]
                matched_names = set()
                user_cell = bool(accept_existing and atts)
                for m in sorted(exp, key=lambda x: x["order"]):
                    k = "%s|%s|%s|%d" % (m["table_key"], m["row"], m["field"], m["order"])
                    if (m["filename"], m["size"]) in have:
                        have.remove((m["filename"], m["size"]))
                        matched_names.add((m["filename"], m["size"]))
                        log["attachments_done"][k] = True
                        present += 1
                    elif user_cell:
                        log["attachments_done"][k] = True      # cell already holds files you supplied: do not add ours
                        tot["accepted_as_yours"] += 1
                    else:
                        log["attachments_done"].pop(k, None)
                        missing += 1
                        if len(notes) < 6:
                            notes.append("missing %s %s: %s (%s bytes, method %s)" % (row, field, m["filename"][:40], m["size"], m["method"]))
                for pos, a in enumerate(atts, 1):
                    live_rows.append({"base": label, "table": tname, "record": row, "field": field, "position_in_cell": pos, "filename": a.get("filename"),
                                      "size": a.get("size"), "type": a.get("type"), "attachment_id": a.get("id"),
                                      "matches_generated_file": "yes" if (a.get("filename"), a.get("size")) in matched_names else "no"})
                if have and not user_cell:
                    extra += len(have)
                    if len(notes) < 6:
                        notes.append("extra   %s %s: %s" % (row, field, ", ".join("%s (%s)" % (f[0][:30], f[1]) for f in have[:3])))
            print("attach %-24s expected %4d, present %4d, missing %4d, extra %3d" % (tname, len(items), present, missing, extra))
            for n in notes:
                print("   " + n)
            tot["expected"] += len(items); tot["present"] += present; tot["missing"] += missing; tot["extra"] += extra
            save_log(log)
    if live_rows:
        import csv as _csv
        p = os.path.join(OUT, "live_attachments.csv")
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(live_rows[0]))
            w.writeheader(); w.writerows(live_rows)
        print("wrote %s (%d live attachments; source of truth for cells you supplied yourself)" % (p, len(live_rows)))
    print("attachment check totals:", tot)
    print("Present files are logged as done, so --phase attachments uploads only the missing ones (methods 'manual' are never uploaded).")
    print("'extra' means more files in a cell than expected (e.g. duplicates): remove them in the app.")


# ------------------------------------------------------------------ optional: create the two trial bases by API
def phase_create_bases(api, cfg, schema):
    ws = cfg.get("workspace_id")
    if not ws:
        raise Fatal("add workspace_id to seed_config.json (token needs schema.bases:write; you need workspace creator rights)")
    for label, b in schema["bases"].items():
        st, js = api.call("POST", API + "/v0/meta/bases", "createbase",
                          {"name": b["name"], "workspaceId": ws, "tables": [{"name": "Seed Placeholder", "fields": [{"name": "Name", "type": "singleLineText"}]}]})
        if st != 200:
            print("create %s failed: %s" % (label, err_text(js)))
        else:
            print("created %s -> %s   (paste into seed_config.json bases; then delete the 'Seed Placeholder' table in the UI)" % (label, js.get("id")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="adopt", choices=["preflight", "create-bases", "schema", "records", "links", "attachments", "all"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--adopt", nargs="+", metavar="TABLE", help="tables you loaded by hand (e.g. CSV import); records the IDs and skips them")
    ap.add_argument("--adopt-links", action="store_true", help="the imported CSV also filled the link columns, so skip the link pass for adopted tables")
    ap.add_argument("--check-attachments", action="store_true", help="compare live attachment cells with the manifest and log what is already there")
    ap.add_argument("--accept-existing", action="store_true", help="with --check-attachments: a cell that already holds any file is treated as supplied by you; none of ours is added to it")
    ap.add_argument("--only-base", choices=["ff_main", "ff_ops"])
    a = ap.parse_args()
    try:
        if a.dry_run and not os.path.exists(os.path.join(HERE, "seed_config.json")):
            cfg = {"token": "dry", "bases": {"ff_main": "app_dry_main", "ff_ops": "app_dry_ops"}, "trial_prefix": "TRIAL",
                   "requests_per_second": 4.5, "collaborator_emails": []}
        else:
            cfg = load_config()
        if a.only_base:
            cfg["bases"] = {a.only_base: cfg["bases"][a.only_base]}
        global DRY
        DRY = a.dry_run
        api = Api(cfg, dry=a.dry_run)
        schema = build_schema()
        log = load_log()
        if a.check_attachments:
            preflight(api, cfg, schema)
            return phase_check_attachments(api, cfg, schema, log, a.accept_existing)
        if a.phase == "create-bases":
            return phase_create_bases(api, cfg, schema)
        preflight(api, cfg, schema)
        if a.phase == "preflight":
            return
        if a.phase == "adopt" and not a.adopt:
            raise Fatal("--phase adopt needs --adopt TABLE [TABLE...]")
        if a.adopt:
            phase_adopt(api, cfg, schema, log, set(a.adopt), a.adopt_links)
            if a.phase == "adopt":
                return
        if a.phase in ("schema", "all"):
            phase_schema(api, cfg, schema, log)
        if a.phase in ("records", "all"):
            phase_records(api, cfg, schema, log)
        if a.phase in ("links", "all"):
            phase_links(api, cfg, schema, log)
        if a.phase in ("attachments", "all"):
            phase_attachments(api, cfg, schema, log)
        if a.dry_run:
            print("dry-run request counts (no network used):", api.counts)
    except Fatal as e:
        print("STOP:", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
