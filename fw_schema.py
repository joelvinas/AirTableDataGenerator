"""Schema definition for the Fictional Fashionwear proxy bases.

build_schema() returns {"bases": {label: {"label","name","tables":[table,...]}}}
Every table/field is a plain dict.  Placeholder Airtable ids are deterministic, 17 chars.
"""
from fw_common import make_id, STYLES

ERR = {"error": "#ERROR!"}          # what a formula divide-by-zero looks like in API output (verify live)
COLORS = ["blueLight2", "cyanLight2", "tealLight2", "greenLight2", "yellowLight2", "orangeLight2",
          "redLight2", "pinkLight2", "purpleLight2", "grayLight2"]
BASES = {"ff_main": "TRIAL Fictional Fashionwear Main", "ff_ops": "TRIAL Fictional Fashionwear Ops"}


def F(name, type_, opts=None, **kw):
    d = {"name": name, "type": type_, "options": dict(opts or {})}
    d.update(kw)
    return d


def LINK(name, target, single=False, inverse=None, inverse_single=False, **kw):
    return F(name, "multipleRecordLinks", {},
             link={"target": target, "single": single, "inverse": inverse,
                   "inverse_single": inverse_single, "is_inverse": False}, **kw)


def SEL(name, choices, **kw):
    return F(name, "singleSelect", {"choices": list(choices)}, **kw)


def MSEL(name, choices, **kw):
    return F(name, "multipleSelects", {"choices": list(choices)}, **kw)


def NUM(name, p=0, **kw): return F(name, "number", {"precision": p}, **kw)
def CUR(name, p=2, **kw): return F(name, "currency", {"precision": p, "symbol": "$"}, **kw)
def PCT(name, p=1, **kw): return F(name, "percent", {"precision": p}, **kw)
def TXT(name, **kw): return F(name, "singleLineText", **kw)
def LONG(name, **kw): return F(name, "multilineText", **kw)
def DATE(name, **kw): return F(name, "date", {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}}, **kw)
def DT(name, **kw):
    return F(name, "dateTime", {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"},
                                "timeFormat": {"name": "24hour", "format": "HH:mm"},
                                "timeZone": "America/Chicago"}, **kw)
def CHK(name, **kw): return F(name, "checkbox", {"icon": "check", "color": "greenBright"}, **kw)
def ATTACH(name, **kw): return F(name, "multipleAttachments", {"isReversed": False}, **kw)
def RATING(name, **kw): return F(name, "rating", {"icon": "star", "max": 5, "color": "yellowBright"}, **kw)
def DUR(name, **kw): return F(name, "duration", {"durationFormat": "h:mm:ss"}, **kw)


def T(key, name, base, fields, rows):
    return {"key": key, "name": name, "base": base, "fields": fields, "rows": rows}


# ---------------------------------------------------------------- formulas used by several tables
def _n(v):
    return 0 if v is None else v


def margin(r):
    p = r.get("Price")
    if not p:
        return ERR
    return round((p - _n(r.get("Cost"))) / p, 3)


def margin_safe(r):
    p = r.get("Price")
    if not p:
        return None
    return round((p - _n(r.get("Cost"))) / p, 3)


def wide_formula(i):
    """Return (expr, fn, result_type) for Quota Stress Wide formula i (1-based)."""
    k = i % 6
    if k == 1:
        return ("{Number A} + {Number B} + %d" % i, lambda r: round(_n(r.get("Number A")) + _n(r.get("Number B")) + i, 8), "number")
    if k == 2:
        return ('CONCATENATE({Text A}, "-", {Text B}, "-%d")' % i,
                lambda r: "%s-%s-%d" % (r.get("Text A") or "", r.get("Text B") or "", i), "string")
    if k == 3:
        return ('IF({Flag}, "yes-%d", "no-%d")' % (i, i), lambda r: ("yes-%d" % i) if r.get("Flag") else ("no-%d" % i), "string")
    if k == 4:
        return ("ROUND({Number C} * 1.5 + %d, 2)" % i, lambda r: round(_n(r.get("Number C")) * 1.5 + i, 2), "number")
    if k == 5:
        return ("LEN({Long Text 01}) + %d" % i, lambda r: len(r.get("Long Text 01") or "") + i, "number")
    return ('UPPER({Text C}) & "-%d"' % i, lambda r: (r.get("Text C") or "").upper() + "-%d" % i, "string")


# ---------------------------------------------------------------- base 1
def base_main():
    t = []
    t.append(T("loc", "Retail Locations", "ff_main", [
        TXT("id"), TXT("City"), TXT("Cross Street"),
        SEL("Freestanding/Mall", ["Freestanding", "Mall"]),
        TXT("Format Label", note="near-duplicate case variants of Mall/Freestanding"),
        DATE("Opened"), NUM("Square Footage"), F("Phone", "phoneNumber"), F("Store Email", "email"),
        LONG("Store Hours"),
        LINK("Store Manager", "mgr", single=True, inverse=None, cover="2-cycle Stores<->Store Managers (one-way both sides)"),
    ], 60))
    t.append(T("mgr", "Store Managers", "ff_main", [
        TXT("Manager ID"), TXT("Name"), F("Email", "email"), F("Phone", "phoneNumber"),
        LINK("Home Store", "loc", single=True, inverse=None),
        F("Regional Lead", "singleCollaborator"), DATE("Hired"),
        SEL("Salary Band", ["L1", "L2", "L3", "L4"]),
    ], 60))
    t.append(T("rep", "Sales Persons", "ff_main", [
        TXT("id"), TXT("Name"), F("Email", "email"),
        LINK("Homebase Location", "loc", single=True, inverse="Sales Team"),
        PCT("Commission Rate", 1), F("Phone", "phoneNumber"), DATE("Start Date"), CHK("Active"),
        ATTACH("ID Photo"), RATING("Rating"), LONG("Bio"),
    ], 80))
    t.append(T("cli", "Clients", "ff_main", [
        TXT("id"), TXT("Name"),
        LINK("Home Store", "loc", single=True, inverse="Clients"),
        MSEL("Style Interests", STYLES),
        F("Email", "email"), F("Phone", "phoneNumber"), TXT("ZIP"),
        LINK("Referred By", "cli", single=True, inverse=None, cover="self-link"),
        ATTACH("Logo"), DATE("Birthday"), SEL("VIP Tier", ["Bronze", "Silver", "Gold", "Platinum"]),
        F("Joined", "createdTime", {}, calc={"kind": "created"}),
        LONG("Notes"), CHK("Newsletter"),
    ], 150))
    t.append(T("itm", "Items", "ff_main", [
        TXT("id"), TXT("Name"), MSEL("Style Interest Tags", STYLES),
        CUR("Cost"), CUR("Price"),
        F("Margin", "formula", {"formula": "ROUND(({Price}-{Cost})/{Price},3)"},
          calc={"kind": "formula", "fn": margin, "result": "number"}, note="divide-by-zero when Price is 0/blank"),
        F("Margin Safe", "formula", {"formula": "IF({Price}=0,BLANK(),ROUND(({Price}-{Cost})/{Price},3))"},
          calc={"kind": "formula", "fn": margin_safe, "result": "number"}),
        LINK("Collection", "col", single=True, inverse=None, cover="link into a 3-cycle from outside"),
        ATTACH("Product Photo"), F("Description", "richText"), F("SKU", "barcode"), CHK("In Stock"),
    ], 100))
    t.append(T("pur", "Purchase", "ff_main", [
        TXT("id"),
        LINK("clientId", "cli", single=True, inverse="Purchases"),
        LINK("salesPersonId", "rep", single=False, inverse=None, cover="multi-value one-way link"),
        F("Total", "rollup", {}, calc={"kind": "rollup", "link": "Line Items", "field": "Price", "agg": "SUM"}),
        ATTACH("Receipt"), DT("Purchased At"),
        SEL("Channel", ["In-Store", "Online", "Phone", "Trunk Show"]), LONG("Notes"),
        F("Order Number", "autoNumber", {}, calc={"kind": "autonumber"}),
        F("Created", "createdTime", {}, calc={"kind": "created"}),
        F("Last Modified", "lastModifiedTime", {}, calc={"kind": "modified"}),
        F("Created By", "createdBy", {}, calc={"kind": "createdby"}),
        F("Line Count", "count", {}, calc={"kind": "count", "link": "Line Items"}),
        F("Line Prices", "multipleLookupValues", {}, calc={"kind": "lookup", "link": "Line Items", "field": "Price"}),
    ], 200))
    t.append(T("si", "SalesItems", "ff_main", [
        TXT("Line ID", note="NEW primary field: defect fix, original had none"),
        LINK("purchaseId", "pur", single=True, inverse="Line Items"),
        LINK("itemId", "itm", single=True, inverse="Sales Lines"),
        CUR("Price"), CUR("Cost"), PCT("Discount", 1), CUR("Commission"),
    ], 1250))
    t.append(T("col", "Collections", "ff_main", [
        TXT("Collection"), SEL("Season", ["Spring/Summer", "Fall/Winter", "Resort", "Pre-Fall"]),
        LINK("Lead Designer", "dsg", single=True, inverse=None, cover="3-cycle Collections->Designers->Ateliers->Collections"),
        DATE("Launch"),
    ], 12))
    t.append(T("dsg", "Designers", "ff_main", [
        TXT("Designer"), F("Email", "email"),
        LINK("Home Atelier", "atl", single=True, inverse=None),
    ], 12))
    t.append(T("atl", "Ateliers", "ff_main", [
        TXT("Atelier"), TXT("City"),
        LINK("Signature Collection", "col", single=True, inverse=None),
    ], 8))
    t.append(T("lb", "Lookbooks", "ff_main", [
        TXT("Lookbook"), SEL("Season", ["Spring/Summer", "Fall/Winter", "Resort", "Pre-Fall"]),
        LINK("Style Tags", "tag", single=False, inverse="Lookbooks", inverse_single=False,
             cover="many-to-many pair, inverse both sides, no single preference"),
    ], 50))
    t.append(T("tag", "Style Tags", "ff_main", [TXT("Tag")], 120))
    t.append(T("cmp", "Campaigns", "ff_main", [TXT("Campaign"), DATE("Start"), CUR("Budget")], 15))
    t.append(T("ct", "Campaign Tasks", "ff_main", [
        TXT("Task"),
        LINK("Campaign", "cmp", single=True, inverse="Tasks", cover="pair where exactly one side prefers single"),
        CHK("Done"), DATE("Due"), DUR("Estimate"), F("Owner", "singleCollaborator"),
    ], 80))
    t.append(T("sup", "Suppliers", "ff_main", [
        TXT("Supplier"), F("Contact Email", "email"),
        LINK("Contract", "suc", single=True, inverse="Supplier", inverse_single=True,
             cover="pair where BOTH sides prefer single (ambiguous)"),
    ], 10))
    t.append(T("suc", "Supplier Contracts", "ff_main", [TXT("Contract"), DATE("Signed")], 10))
    t.append(T("so", "Special Orders", "ff_main", [
        TXT("Order Ref"),
        LINK("Client", "cli", single=True, inverse="Special Orders"),
        LINK("Billing Store", "loc", single=True, inverse="Billed Special Orders",
             cover="two link fields to the same parent (Billing/Shipping Store)"),
        LINK("Shipping Store", "loc", single=True, inverse=None),
        CHK("Rush"), DATE("Due Date"),
    ], 60))
    t.append(T("ret", "Returns", "ff_main", [
        TXT("Return Ref"), LINK("Line", "si", single=True, inverse="Returns", cover="chain level 4"),
        SEL("Reason", ["Fit", "Defect", "Changed Mind", "Gift"]), DATE("Returned On"), CUR("Refund Amount"),
    ], 50))
    t.append(T("ins", "Return Inspections", "ff_main", [
        TXT("Inspection"), LINK("Return", "ret", single=True, inverse="Inspections", cover="chain level 5"),
        SEL("Condition", ["Resellable", "Damaged", "Needs Cleaning"]), LONG("Notes"),
    ], 50))
    t.append(T("rst", "Restock Orders", "ff_main", [
        TXT("Restock Ref"), LINK("Inspection", "ins", single=True, inverse="Restock Orders", cover="chain level 6"),
        NUM("Qty"), SEL("Status", ["Queued", "Shipped", "Received"]),
    ], 50))
    t.append(T("emp", "Employees", "ff_main", [
        TXT("Employee ID"), TXT("Name"), TXT("Title"), F("Email", "email"), F("Phone", "phoneNumber"), DATE("Hire Date"),
        NUM("Org Level"),
        LINK("Reports To", "emp", single=True, inverse=None, cover="self-link, 6-level org chart"),
        LINK("Works At", "loc", single=True, inverse="Staff"),
    ], 100))
    t.append(T("glo", "Style Glossary", "ff_main", [
        TXT("Term"), LONG("Definition"), SEL("Language", ["English", "Italian", "French"]),
    ], 50))
    t.append(showcase())
    t.append(dq_lab())
    t.append(naming_edge())
    t.append(T("att", "Attachment Lab", "ff_main", [TXT("Lab ID"), TXT("Scenario"), ATTACH("Files")], 30))
    t.extend(wide_tables())
    return t


def showcase():
    fs = [
        TXT("Showcase ID"), TXT("Single Line Text"), LONG("Long Text"), F("Rich Text", "richText"),
        NUM("Number", 2), CUR("Currency"), PCT("Percent", 1), RATING("Rating"), DUR("Duration"),
        DATE("Date"), DT("Date Time"), CHK("Checkbox"),
        SEL("Single Select", ["Red", "Green", "Blue", "Black"]),
        MSEL("Multi Select", ["Wool", "Silk", "Linen", "Cotton"]),
        F("Email", "email"), F("URL", "url"), F("Phone", "phoneNumber"), ATTACH("Attachments"),
        F("Collaborator", "singleCollaborator"), F("Collaborators", "multipleCollaborators"),
        F("Barcode", "barcode"),
        LINK("Featured Item", "itm", single=True, inverse="Showcase Rows"),
        F("Formula", "formula", {"formula": "{Number} * {Currency}"},
          calc={"kind": "formula", "fn": lambda r: round(_n(r.get("Number")) * _n(r.get("Currency")), 8), "result": "number"}),
        F("Rollup", "rollup", {}, calc={"kind": "rollup", "link": "Featured Item", "field": "Price", "agg": "SUM"}),
        F("Lookup", "multipleLookupValues", {}, calc={"kind": "lookup", "link": "Featured Item", "field": "Name"}),
        F("Count", "count", {}, calc={"kind": "count", "link": "Featured Item"}),
        F("Auto Number", "autoNumber", {}, calc={"kind": "autonumber"}),
        F("Created Time", "createdTime", {}, calc={"kind": "created"}),
        F("Last Modified Time", "lastModifiedTime", {}, calc={"kind": "modified"}),
        F("Created By", "createdBy", {}, calc={"kind": "createdby"}),
        F("Last Modified By", "lastModifiedBy", {}, calc={"kind": "modifiedby"}),
        F("Button", "button", {"label": "Open", "url": "https://example.com"}, calc={"kind": "button"}, api="manual",
          note="button fields cannot be created via API and hold no data"),
    ]
    return T("shw", "Field Type Showcase", "ff_main", fs, 60)


def dq_lab():
    fs = [
        TXT("Row ID"), TXT("Always Empty"), TXT("Always Filled"), TXT("Filled Once"),
        TXT("Empty Representations"),
        MSEL("Multi Select Mix", STYLES),
        CHK("Checkbox Mix"),
        NUM("Float Edge", 8), NUM("Integer Edge", 0), CUR("Currency Edge"), PCT("Percent Edge", 2),
        RATING("Rating Edge"), DUR("Duration Edge"),
        LONG("Text Edge"), TXT("ZIP"), TXT("Format Label"),
        TXT("Constant Value"), TXT("Unique Value"), TXT("Near Duplicate"),
        SEL("Typecast Select", ["Alpha", "Beta", "Gamma"]),
        DATE("Date Edge"), DT("DateTime Edge"), F("Email Edge", "email"), F("URL Edge", "url"),
        F("Phone Edge", "phoneNumber"), F("Barcode", "barcode"), F("Rich Text Edge", "richText"),
        F("Collaborator Mix", "singleCollaborator"), F("Collaborators Mix", "multipleCollaborators"),
    ]
    return T("dql", "Data Quality Lab", "ff_main", fs, 120)


LONG_100 = ("Field " + "L" * 94)[:100]
LONG_255 = ("Long Field Name " + "X" * 239)[:255]


def naming_edge():
    fs = [
        TXT("Case ID"),
        TXT("Total"), TXT("total", naming_try=True, note="case-only duplicate: Airtable requires unique names ignoring case"),
        TXT("Trailing Space"), TXT("Trailing Space ", naming_try=True, note="trailing space: likely trimmed/rejected"),
        TXT("Zero​Width", naming_try=True), TXT("Non Breaking Space"), TXT("Non Breaking Space"),
        TXT("Café Note", naming_try=True, note="NFD form"), TXT("Café Note", note="NFC form"),
        TXT("Color"), TXT("Cоlor", note="Cyrillic o homoglyph"),
        TXT("Café Voucher ☕"), TXT("顧客 Notes"), TXT("Größe (Size)"),
        TXT("\U0001F457 Style Notes"), TXT("Price (€)"),
        TXT("Qty, Net"), TXT('Note "quoted"'), TXT("Fit: slim/regular"), TXT("A/B Test Group"),
        TXT("100% Cotton?"), TXT("Back\\Slash"), TXT("[Bracket] {Curly} <Angle>"), TXT("Semi;colon"),
        TXT("Name"), TXT("id"), TXT("Notes"),
        TXT(LONG_100), TXT(LONG_255, naming_try=True, note="255-char name; Airtable limit not verified"),
    ]
    return T("nec", "Naming Edge Cases", "ff_main", fs, 20)


N_QP = 6


def wide_tables():
    fs = [TXT("Row ID")]
    for i in range(1, 27):
        fs.append(LONG("Long Text %02d" % i))
    for n in "ABC":
        fs.append(NUM("Number " + n, 2))
    for i in range(4, 16):
        fs.append(NUM("Number %02d" % i, 2))
    for n in "ABC":
        fs.append(TXT("Text " + n))
    for i in range(4, 13):
        fs.append(TXT("Text %02d" % i))
    fs.append(CHK("Flag"))
    for i in range(1, 23):
        expr, fn, res = wide_formula(i)
        fs.append(F("Formula %02d" % i, "formula", {"formula": expr}, calc={"kind": "formula", "fn": fn, "result": res}))
    for i in range(1, 37):
        parent = "qp%d" % ((i - 1) % N_QP + 1)
        fs.append(LINK("Link %02d" % i, parent, single=False, inverse="From Link %02d" % i,
                       cover="35+ link fields (quota stress)" if i == 1 else None))
    fs += [DATE("Launch Date"), DT("Reviewed At"), SEL("Status", ["Draft", "Review", "Live"]),
           MSEL("Tags", ["A", "B", "C", "D"]), RATING("Score"), CUR("Budget"), PCT("Progress"),
           F("Contact", "email"), F("Link URL", "url"), F("Hotline", "phoneNumber"),
           F("Created", "createdTime", {}, calc={"kind": "created"})]
    out = [T("wide", "Quota Stress Wide", "ff_main", fs, 60)]
    for k in range(1, N_QP + 1):
        out.append(T("qp%d" % k, "Quota Parent %d" % k, "ff_main", [TXT("Parent ID")], 8))
    return out


# ---------------------------------------------------------------- base 2
def base_ops():
    t = []
    t.append(T("rl2", "Retail Locations", "ff_ops", [TXT("id"), TXT("City"), TXT("Region"),
                                                       SEL("Freestanding/Mall", ["Freestanding", "Mall", "Outlet"])], 15))
    t.append(T("itm2", "Items", "ff_ops", [
        TXT("id"), TXT("Name"), TXT("Price", note="text here, currency in ff_main (type collision across bases)"),
        CUR("Cost"), CHK("Discontinued"), ATTACH("Spec Sheet"),
    ], 50))
    t.append(T("glo2", "Style Glossary", "ff_ops", [TXT("Term"), LONG("Definition")], 10))
    t.append(T("ven", "Vendors", "ff_ops", [
        TXT("Vendor"), F("Contact Email", "email"),
        LINK("Preferred Items", "itm2", single=False, inverse="Vendors", cover="many-to-many in base 2"),
    ], 12))
    t.append(T("shp", "Shipments", "ff_ops", [
        TXT("Shipment No"),
        LINK("Destination", "rl2", single=True, inverse="Shipments"),
        SEL("Carrier", ["Fictional Freight", "Example Express", "Sample Couriers"]), DATE("Shipped"),
        ATTACH("Manifest"), CHK("Delivered"),
    ], 80))
    t.append(T("sln", "Shipment Lines", "ff_ops", [
        TXT("Line"), LINK("Shipment", "shp", single=True, inverse="Lines"),
        LINK("Item", "itm2", single=True, inverse=None), NUM("Qty"),
    ], 150))
    return t


# ---------------------------------------------------------------- assembly
def build_schema():
    bases = {}
    for label, tables in (("ff_main", base_main()), ("ff_ops", base_ops())):
        bases[label] = {"label": label, "name": BASES[label], "tables": tables}
    for b in bases.values():
        _finish(b)
    return {"bases": bases}


def _finish(base):
    tmap = {t["key"]: t for t in base["tables"]}
    # inverse fields
    for t in list(base["tables"]):
        for f in list(t["fields"]):
            lk = f.get("link")
            if lk and lk["inverse"] and not lk["is_inverse"]:
                tgt = tmap[lk["target"]]
                inv = F(lk["inverse"], "multipleRecordLinks", {},
                        link={"target": t["key"], "single": lk["inverse_single"], "inverse": f["name"],
                              "inverse_single": lk["single"], "is_inverse": True,
                              "forward": [t["key"], f["name"]]})
                tgt["fields"].append(inv)
    # ids, primary, options
    for t in base["tables"]:
        t["id"] = make_id("tbl", base["label"] + "|" + t["key"])
        t["primary"] = t["fields"][0]["name"]
        seen = {}
        for f in t["fields"]:
            f["id"] = make_id("fld", base["label"] + "|" + t["key"] + "|" + f["name"])
            f["table"] = t["key"]
            if f["type"] in ("singleSelect", "multipleSelects"):
                for i, ch in enumerate(f["options"]["choices"]):
                    if isinstance(ch, str):
                        f["options"]["choices"][i] = {"id": make_id("sel", t["key"] + "|" + f["name"] + "|" + ch),
                                                       "name": ch, "color": COLORS[i % len(COLORS)]}
            f.setdefault("api", None)
            seen[f["name"]] = f
        t["by_name"] = seen
    for t in base["tables"]:
        for f in t["fields"]:
            lk = f.get("link")
            if lk:
                tgt = tmap[lk["target"]]
                lk["target_id"] = tgt["id"]
                inv = tgt["by_name"].get(lk["inverse"]) if lk["inverse"] else None
                lk["inverse_id"] = inv["id"] if inv else None
            if f["api"] is None:
                f["api"] = api_class(f)


def api_class(f):
    ty = f["type"]
    lk = f.get("link")
    if lk:
        if lk["is_inverse"]:
            return "auto"                       # created by Airtable when the forward side is created
        return "manual" if (lk["single"] or lk["inverse"] is None or lk["inverse_single"]) else "ok"
    if f.get("naming_try"):
        return "try"
    if ty in ("formula", "rollup", "multipleLookupValues", "count", "autoNumber", "createdTime",
              "lastModifiedTime", "createdBy", "lastModifiedBy"):
        return "try"
    if ty in ("richText", "barcode", "rating", "duration", "singleCollaborator", "multipleCollaborators"):
        return "try"
    return "ok"


def manual_link_steps(schema):
    """Yield (base, table, field, [steps]) for every link needing UI work."""
    for b in schema["bases"].values():
        tmap = {t["key"]: t for t in b["tables"]}
        for t in b["tables"]:
            for f in t["fields"]:
                lk = f.get("link")
                if not lk or lk["is_inverse"]:
                    continue
                steps = []
                if lk["single"]:
                    steps.append("turn OFF 'Allow linking to multiple records' on %s.%s" % (t["name"], f["name"]))
                if lk["inverse"] is None:
                    tgt = tmap[lk["target"]]
                    steps.append("delete the auto-created inverse field in '%s' (renamed __delete_me__ by seed.py)" % tgt["name"])
                if lk["inverse"] and lk["inverse_single"]:
                    steps.append("turn OFF 'Allow linking to multiple records' on inverse %s.%s" % (tmap[lk["target"]]["name"], lk["inverse"]))
                if steps:
                    yield (b["label"], t["name"], f["name"], steps)


if __name__ == "__main__":
    s = build_schema()
    for b in s["bases"].values():
        nf = sum(len(t["fields"]) for t in b["tables"])
        print(b["label"], len(b["tables"]), "tables", nf, "fields", sum(t["rows"] for t in b["tables"]), "rows")
    w = [t for t in s["bases"]["ff_main"]["tables"] if t["key"] == "wide"][0]
    from collections import Counter
    c = Counter(f["type"] for f in w["fields"])
    print("wide:", len(w["fields"]), dict(c))
    print("manual link fields:", sum(1 for _ in manual_link_steps(s)))
