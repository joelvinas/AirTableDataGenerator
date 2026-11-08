"""Deterministic record generation for both proxy bases.

generate(schema, cfg) -> dict(rows={table_key: [row,...]}, att=[attachment plan...])
Rows are RAW (they may contain '' / [] / duplicate links / unknown select values on purpose).
Link cells are lists of target primary-field values.  Collaborators are placeholder emails
collabK@example.com (mapped to real users at seed time).
"""
import csv
import json
import os
from datetime import datetime, timedelta

import fw_files as ff
from fw_common import CITIES, FIRST, LAST, STYLES, rng_for, slug

LEGACY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legacy")   # <root>/legacy
EPOCH = datetime(2024, 1, 1)


def read_legacy(name):
    with open(os.path.join(LEGACY, "csv_output_%s.csv" % name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def person(i):
    return FIRST[i % len(FIRST)], LAST[(7 * i + i // len(FIRST)) % len(LAST)]


def pname(i):
    a, b = person(i)
    return "%s %s" % (a, b)


def email(i, domain="example.com"):
    a, b = person(i)
    return "%s.%s%d@%s" % (slug(a), slug(b), i, domain)


def phone(r):
    return "%s-555-01%02d" % (r.choice(["212", "310", "312", "415", "617", "702", "206", "303", "305", "404"]), r.randrange(100))


def d_iso(r, y0=1995, y1=2026):
    return (datetime(y0, 1, 1) + timedelta(days=r.randrange((y1 - y0) * 365))).strftime("%Y-%m-%d")


def dt_iso(r):
    t = EPOCH + timedelta(seconds=r.randrange(0, 2 * 365 * 86400))
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def collab(r, n, p_empty=0.2):
    if n <= 0 or r.random() < p_empty:
        return None
    return "collab%d@example.com" % (1 + r.randrange(n))


def key(prefix, i, w=3):
    return "%s_%0*d" % (prefix, w, i)


class Plan:
    def __init__(self):
        self.items = []

    def add(self, table, row_key, field, filename, data, method="api", note="", dup=""):
        self.items.append({"table": table, "row": row_key, "field": field, "filename": filename, "data": data,
                           "mime": ff.mime_for(filename), "method": method, "note": note, "dup": dup})


# --------------------------------------------------------------------------- base 1 core tables
def gen_loc(cfg, rows, plan):
    r = rng_for(cfg["seed"], "loc")
    out = []
    mgr_of = {}
    legacy = read_legacy("Retail_Locations")
    for i in range(1, 61):
        if i <= 20:
            lg = legacy[i - 1]
            city, cross, fmt = lg["City"], lg["Cross Street"], lg["Freestanding/Mall"]
            k = lg["id"]
        else:
            city, cross = CITIES[i - 21]
            fmt = "Mall" if any(w in cross for w in ("Mall", "Center", "Plaza", "Fashion", "Village", "Shops", "Grove", "Place")) else "Freestanding"
            k = key("loc", i)
        label = [fmt, fmt.lower(), fmt.upper(), fmt][i % 4]
        row = {"id": k, "City": city, "Cross Street": cross, "Freestanding/Mall": fmt, "Format Label": label,
               "Opened": d_iso(r, 1995, 2025), "Square Footage": r.randrange(1500, 12000),
               "Phone": phone(r), "Store Email": "store.%s%d@example.com" % (slug(city), i)}
        if r.random() < 0.8:
            row["Store Hours"] = "Mon-Sat 10:00-19:00\nSun 12:00-17:00"
        mgr_of[i] = key("mgr", i)
        out.append(row)
    mgr_of[58], mgr_of[59] = key("mgr", 59), key("mgr", 58)
    del mgr_of[60]
    for i, row in enumerate(out, 1):
        if i in mgr_of:
            row["Store Manager"] = [mgr_of[i]]
    if cfg["sanitize_legacy"]:
        pass
    rows["loc"] = out


def gen_mgr(cfg, rows, plan):
    r = rng_for(cfg["seed"], "mgr")
    out = []
    home = {i: key("loc", i) if i > 20 else "loc_%03d" % i for i in range(1, 61)}
    home[58], home[59] = key("loc", 59), key("loc", 58)   # mutual with the swap done in gen_loc
    for i in range(1, 61):
        row = {"Manager ID": key("mgr", i), "Name": pname(i + 300), "Email": email(i + 300), "Phone": phone(r),
               "Hired": d_iso(r, 2005, 2025), "Salary Band": r.choice(["L1", "L2", "L3", "L4"])}
        if i != 60:
            row["Home Store"] = [home[i]]
        c = collab(r, cfg["collab_count"])
        if c:
            row["Regional Lead"] = c
        out.append(row)
    rows["mgr"] = out


def gen_rep(cfg, rows, plan):
    r = rng_for(cfg["seed"], "rep")
    legacy = read_legacy("Sales_Persons")
    out = []
    for i in range(1, 81):
        if i <= 20:
            lg = legacy[i - 1]
            em = lg["Email"]
            if cfg["sanitize_legacy"]:
                em = em.replace("monarchmenswear.com", "example.com")
            row = {"id": lg["id"], "Name": lg["Name"], "Email": em, "Homebase Location": [lg["Homebase Location"]],
                   "Commission Rate": float(lg["Commission Rate"])}
        else:
            row = {"id": key("rep", i), "Name": pname(i + 40), "Email": email(i + 40),
                   "Homebase Location": [key("loc", r.randrange(1, 61))],
                   "Commission Rate": round(r.uniform(0.05, 0.12), 3)}
        row["Phone"] = phone(r)
        row["Start Date"] = d_iso(r, 2008, 2026)
        if r.random() < 0.85:
            row["Active"] = True
        row["Rating"] = r.choice([1, 2, 3, 4, 5, None])
        if r.random() < 0.5:
            row["Bio"] = "Joined the %s floor team.\nSpecialty: %s." % (r.choice(["Madison", "Oak", "Pine"]), r.choice(STYLES))
        out.append(row)
        if i <= 30:
            col = (30 + i * 5 % 120, 50 + i * 3 % 100, 90 + i * 7 % 120)
            plan.add("rep", row["id"], "ID Photo", "%s_id.png" % row["id"], ff.png_gradient(200, 200, col))
    rows["rep"] = out


def gen_cli(cfg, rows, plan):
    r = rng_for(cfg["seed"], "cli")
    legacy = read_legacy("Clients")
    out = []
    for i in range(1, 151):
        if i <= 20:
            lg = legacy[i - 1]
            row = {"id": lg["id"], "Name": lg["Name"], "Home Store": [lg["Home Store"]],
                   "Style Interests": json.loads(lg["Style Interests"])}
        else:
            n = r.choice([0, 1, 1, 2, 2, 3, 4])
            row = {"id": key("cli", i), "Name": pname(i + 90), "Home Store": [key("loc", r.randrange(1, 61))],
                   "Style Interests": r.sample(STYLES, n)}
        if i == 100:
            row["Style Interests"] = list(STYLES)          # all 10 choices
        if i == 101:
            row["Style Interests"] = []                    # explicit empty array
        if i == 150:
            del row["Home Store"]                          # empty link
        row["Email"] = email(i + 90)
        row["Phone"] = phone(r)
        row["ZIP"] = r.choice(["02134", "10001", "90210", "60601", "00501", "75201", "01001", "07030"])
        if i == 21:
            row["Referred By"] = [row["id"]]               # record links to itself
        elif i == 22:
            row["Referred By"] = [key("cli", 23)]          # mutual pair
        elif i == 23:
            row["Referred By"] = [key("cli", 22)]
        elif i > 23 and r.random() < 0.3:
            row["Referred By"] = [key("cli", r.randrange(1, i))]
        row["Birthday"] = "1992-02-29" if i == 24 else d_iso(r, 1950, 2002)
        row["VIP Tier"] = r.choice(["Bronze", "Silver", "Gold", "Platinum", None])
        if r.random() < 0.4:
            row["Notes"] = r.choice(["Prefers evening fittings.\nAllergic to wool? No - to moths.", "Gift buyer \U0001F381, ships to office.",
                                     "Collects pocket squares ✂️", "Asked about monogramming, \"initials only\"."])
        if r.random() < 0.5:
            row["Newsletter"] = True
        out.append(row)
        if i <= 40:
            nm = row["id"]
            if i % 2:
                plan.add("cli", nm, "Logo", "%s_logo.svg" % nm, ff.svg(row["Name"]))
            else:
                plan.add("cli", nm, "Logo", "%s_logo.png" % nm, ff.png_gradient(240, 90, (80, 40 + i * 4 % 100, 70)))
    rows["cli"] = out


FABRICS = ["Merino", "Cashmere", "Silk", "Linen", "Alpaca", "Mohair", "Cotton Twill", "Flannel", "Tweed", "Velvet", "Herringbone", "Seersucker"]
GARMENTS = ["Overcoat", "Blazer", "Waistcoat", "Trousers", "Dress Shirt", "Cardigan", "Scarf", "Tie", "Loafers", "Belt", "Dinner Jacket", "Polo"]
ADJ = ["Heritage", "Atelier", "Signature", "Classic"]


def gen_itm(cfg, rows, plan):
    r = rng_for(cfg["seed"], "itm")
    legacy = read_legacy("Items")
    out = []
    for i in range(1, 101):
        if i <= 20:
            lg = legacy[i - 1]
            nm = lg["Name"]
            if cfg["sanitize_legacy"]:
                nm = nm.replace("Loro Piana", "Lorenzo Pianelli")
            row = {"id": lg["id"], "Name": nm, "Style Interest Tags": json.loads(lg["Style Interest Tags"]),
                   "Cost": float(lg["Cost"]), "Price": float(lg["Price"])}
        else:
            cost = float(r.randrange(15, 1600))
            row = {"id": key("itm", i), "Name": "%s %s %s" % (ADJ[i % 4], FABRICS[i % 12], GARMENTS[(i * 5) % 12]),
                   "Style Interest Tags": r.sample(STYLES, r.choice([1, 2, 3])),
                   "Cost": cost, "Price": round(cost * r.uniform(2.5, 3.6) / 5) * 5.0}
        if i == 99:
            row["Cost"], row["Price"] = 25.0, 0.0          # divide-by-zero case
        if i == 100:
            row["Cost"], row["Price"] = 0.0, 0.0           # 0/0
        if i <= 94:
            row["Collection"] = [COLL[r.randrange(12)]]
        if r.random() < 0.6:
            row["Description"] = "**Fabric:** %s\n\n- Hand finished\n- Fully canvassed" % FABRICS[i % 12]
        if i <= 90:
            row["SKU"] = {"text": "FW-%06d" % i}
        if r.random() < 0.7:
            row["In Stock"] = True
        out.append(row)
        if i <= 70:
            plan.add("itm", row["id"], "Product Photo", "%s_photo.png" % row["id"],
                     ff.png_gradient(400, 120, (50 + i * 3 % 120, 60 + i * 5 % 100, 100 + i * 2 % 100)))
            if i % 10 == 5:
                plan.add("itm", row["id"], "Product Photo", "%s_hires.png" % row["id"],
                         ff.png_noise(300, 330, "hires%d" % i))
    rows["itm"] = out


def gen_purchases(cfg, rows, plan):
    r = rng_for(cfg["seed"], "pur")
    lp = read_legacy("Purchases")
    ls = read_legacy("Sales_Items")
    reps = {x["id"]: x["Commission Rate"] for x in rows["rep"]}
    items = {x["id"]: x for x in rows["itm"]}
    purchases = []
    lines = {}                                              # purchase id -> list of line dicts
    for lg in lp:
        purchases.append({"id": lg["id"], "clientId": [lg["clientId"]], "salesPersonId": json.loads(lg["salesPersonId"])})
    for lg in ls:
        lines.setdefault(lg["purchaseId"], []).append({
            "itemId": lg["itemId"], "Price": float(lg["Price"]), "Cost": float(lg["Cost"]),
            "Discount": float(lg["Discount"]), "Commission": float(lg["Commission"])})
    gen_ids = [key("pur", i) for i in range(21, 200)]
    for pid in gen_ids:
        i = int(pid[4:])
        row = {"id": pid, "clientId": [key("cli", r.randrange(1, 151))],
               "salesPersonId": [key("rep", r.randrange(1, 81)) for _ in range(r.choice([1, 1, 2]))]}
        row["salesPersonId"] = list(dict.fromkeys(row["salesPersonId"]))
        if i == 150:
            row["salesPersonId"] = [key("rep", 5), key("rep", 5)]      # raw duplicate inside one cell
        if i == 196:
            del row["salesPersonId"]                                    # empty link
        if i == 199:
            del row["clientId"]
        purchases.append(row)
    bulk = {"id": key("pur", 200), "clientId": [key("cli", 7)], "salesPersonId": [key("rep", 3), key("rep", 9)]}
    purchases.append(bulk)
    total_target = cfg["large_rows"]
    legacy_n = sum(len(v) for v in lines.values())
    bulk_n = 110 if total_target >= 600 else max(0, min(110, total_target - legacy_n - 100))
    need = max(0, total_target - legacy_n - bulk_n)
    cand = [p for p in gen_ids if p not in (key("pur", 198), key("pur", 199))]
    counts = {p: 0 for p in gen_ids}
    base = min(len(cand), need)
    for p in cand[:base]:
        counts[p] = 1
    rest = need - base
    while rest > 0:
        p = cand[r.randrange(len(cand))]
        if counts[p] < 20:
            counts[p] += 1
            rest -= 1
    counts[key("pur", 200)] = bulk_n
    for p in purchases:
        if p["id"] in lines:
            continue
        n = counts.get(p["id"], 0)
        reps_l = list(dict.fromkeys(p.get("salesPersonId", [])))
        rate = sum(float(reps[x]) for x in reps_l) / len(reps_l) if reps_l else 0.0
        ls_ = []
        for _ in range(n):
            it = items[key("itm", r.randrange(1, 101))]
            disc = r.choices([0.0, 0.05, 0.1, 0.15], [60, 20, 15, 5])[0]
            price = round(float(it["Price"]) * (1 - disc), 2)
            ls_.append({"itemId": it["id"], "Price": price, "Cost": float(it["Cost"]), "Discount": disc,
                        "Commission": round(price * rate, 2)})
        lines[p["id"]] = ls_
    # edge numeric lines
    if lines.get(key("pur", 150)):
        l0 = lines[key("pur", 150)][0]
        l0.update({"Price": 0.0, "Discount": 1.0, "Commission": 0.0})
    if lines.get(key("pur", 151)):
        l0 = lines[key("pur", 151)][0]
        l0.update({"itemId": key("itm", 9), "Price": -295.0, "Cost": 90.0, "Discount": 0.0, "Commission": -19.18})
    # order = purchase order
    si = []
    for p in purchases:
        for n, ln in enumerate(lines.get(p["id"], []), 1):
            si.append({"Line ID": "%s-%03d" % (p["id"], n), "purchaseId": [p["id"]], "itemId": [ln["itemId"]],
                       "Price": ln["Price"], "Cost": ln["Cost"], "Discount": ln["Discount"], "Commission": ln["Commission"]})
    rows["si"] = si
    # purchase scalar fields + attachments
    for idx, p in enumerate(purchases, 1):
        p["Purchased At"] = dt_iso(r)
        p["Channel"] = r.choice(["In-Store", "Online", "Phone", "Trunk Show", None])
        if r.random() < 0.3:
            p["Notes"] = r.choice(["Gift wrap requested.", "Alterations: hem 2cm\nPickup Friday", "Paid with split tender (cash, card)."])
        if idx <= 70 or p["id"] == bulk["id"]:
            ln = ["Receipt for %s" % p["id"], "Client: %s" % p.get("clientId", ["(none)"])[0], "Sales: %s" % ", ".join(p.get("salesPersonId", [])), ""]
            pl = lines.get(p["id"], [])
            for n, l in enumerate(pl[:25], 1):
                ln.append("%02d  %-8s  $%10.2f  disc %3d%%" % (n, l["itemId"], l["Price"], round(l["Discount"] * 100)))
            if len(pl) > 25:
                ln.append("... %d more lines" % (len(pl) - 25))
            ln.append("TOTAL  $%.2f" % round(sum(l["Price"] for l in pl), 2))
            filler = 150000 if idx == 5 else (600000 if idx == 15 else 0)
            plan.add("pur", p["id"], "Receipt", "%s_receipt.pdf" % p["id"], ff.pdf(ln, filler))
            if 41 <= idx <= 70:
                plan.add("pur", p["id"], "Receipt", "%s_receipt_copy.pdf" % p["id"], ff.pdf(ln + ["COPY"], 0))
            if 61 <= idx <= 70:
                plan.add("pur", p["id"], "Receipt", "%s_signature.png" % p["id"], ff.png_gradient(300, 100, (90, 90, 120)))
                plan.add("pur", p["id"], "Receipt", "%s_warranty.txt" % p["id"], ff.txt("Warranty card for %s" % p["id"]))
    rows["pur"] = purchases


# --------------------------------------------------------------------------- base 1 topology tables
COLL = ["Aurora Heritage", "Midnight Atelier", "Harbor Wool", "Meridian Linen", "Sable Silk", "Hearthstone Tweed",
        "Northern Cashmere", "Vesper Evening", "Coastal Resort Edit", "Marble Court", "Ivory Season", "Lantern Tailoring"]
ATEL = [("Atelier Lyon", "Lyon"), ("Atelier Porto", "Porto"), ("Atelier Kyoto", "Kyoto"), ("Atelier Oaxaca", "Oaxaca"),
        ("Atelier Tallinn", "Tallinn"), ("Atelier Lisbon", "Lisbon"), ("Atelier Vienna", "Vienna"), ("Atelier Ghent", "Ghent")]
SEASONS = ["Spring/Summer", "Fall/Winter", "Resort", "Pre-Fall"]


def gen_cycle3(cfg, rows, plan):
    r = rng_for(cfg["seed"], "cycle3")
    dsg = [pname(i + 500) for i in range(12)]
    rows["dsg"] = [{"Designer": dsg[i], "Email": email(i + 500), "Home Atelier": [ATEL[i % 8][0]]} for i in range(12)]
    rows["col"] = [{"Collection": COLL[i], "Season": SEASONS[i % 4], "Lead Designer": [dsg[i]], "Launch": d_iso(r, 2023, 2027)} for i in range(12)]
    rows["atl"] = [{"Atelier": ATEL[j][0], "City": ATEL[j][1], "Signature Collection": [COLL[j]]} for j in range(8)]


TADJ = ["Slim", "Relaxed", "Tailored", "Plush", "Crisp", "Draped", "Boxy", "Fluid", "Structured", "Lightweight", "Heavyweight", "Textured"]
TNOUN = ["Wool", "Linen", "Silk", "Denim", "Velvet", "Leather", "Knit", "Twill", "Satin", "Suede"]


def gen_m2m(cfg, rows, plan):
    r = rng_for(cfg["seed"], "m2m")
    tags = ["%s %s" % (TADJ[i % 12], TNOUN[(i // 12) % 10]) for i in range(120)]
    rows["tag"] = [{"Tag": t} for t in tags]
    out = []
    for i in range(1, 51):
        row = {"Lookbook": "Lookbook %s-%02d" % (["SS27", "FW27"][i % 2], i), "Season": SEASONS[i % 4]}
        if i == 1:
            row["Style Tags"] = tags[:110]                                  # 110 links in one cell
        elif i == 2:
            row["Style Tags"] = [tags[5], tags[5], tags[6]]                 # raw duplicate links
        elif i == 3:
            pass                                                            # empty
        else:
            row["Style Tags"] = r.sample(tags, r.randrange(1, 9))
        out.append(row)
    rows["lb"] = out


def gen_campaigns(cfg, rows, plan):
    r = rng_for(cfg["seed"], "cmp")
    names = ["Spring Launch", "Holiday Gifting", "Trunk Show Tour", "Summer Linen Edit", "Black Tie Season", "Heritage Wool Week",
             "Resort Preview", "VIP Evening", "Tailoring Month", "Outerwear Debut", "Winter Sale", "Anniversary Edit",
             "Groomsmen Program", "Corporate Wardrobe", "Student Discount"]
    rows["cmp"] = [{"Campaign": n, "Start": d_iso(r, 2025, 2027), "Budget": 0.0 if i == 14 else float(r.randrange(5, 200) * 500)} for i, n in enumerate(names)]
    out = []
    for i in range(1, 81):
        row = {"Task": key("ct", i), "Estimate": r.choice([0, 1800, 7200, 90000, 3600]), "Due": d_iso(r, 2026, 2027)}
        if i != 80:
            row["Campaign"] = [names[r.randrange(15)]]
        if r.random() < 0.4:
            row["Done"] = True
        c = collab(r, cfg["collab_count"])
        if c:
            row["Owner"] = c
        out.append(row)
    rows["ct"] = out


def gen_supply(cfg, rows, plan):
    r = rng_for(cfg["seed"], "sup")
    names = ["Harrow Finch Textiles", "Brightwater Mills", "Kettleridge Leather", "Orsini Silk House", "Pennant Buttons",
             "Vantage Linings", "Alder Lane Wool", "Cobalt Dye Works", "Fenwick Zippers", "Marlow Packaging"]
    rows["suc"] = [{"Contract": "Contract 2026-%02d" % i, "Signed": d_iso(r, 2024, 2026)} for i in range(1, 11)]
    out = []
    for i, n in enumerate(names, 1):
        row = {"Supplier": n, "Contact Email": "orders.%s@example.com" % slug(n)}
        if i <= 9:
            row["Contract"] = ["Contract 2026-%02d" % i]
        out.append(row)
    rows["sup"] = out


def gen_special(cfg, rows, plan):
    r = rng_for(cfg["seed"], "so")
    out = []
    for i in range(1, 61):
        row = {"Order Ref": "SO-%03d" % i, "Client": [key("cli", r.randrange(1, 151))],
               "Billing Store": [key("loc", r.randrange(1, 61))], "Shipping Store": [key("loc", r.randrange(1, 61))],
               "Due Date": d_iso(r, 2026, 2027)}
        if i == 7:
            row["Shipping Store"] = list(row["Billing Store"])
        if i == 60:
            del row["Billing Store"]
        if r.random() < 0.2:
            row["Rush"] = True
        out.append(row)
    rows["so"] = out


def gen_returns(cfg, rows, plan):
    r = rng_for(cfg["seed"], "ret")
    line_ids = [x["Line ID"] for x in rows["si"]]
    price = {x["Line ID"]: x["Price"] for x in rows["si"]}
    chosen = r.sample(line_ids, 50)
    rets = []
    for i, ln in enumerate(chosen, 1):
        rets.append({"Return Ref": key("ret", i), "Line": [ln], "Reason": r.choice(["Fit", "Defect", "Changed Mind", "Gift", None]),
                     "Returned On": d_iso(r, 2025, 2026), "Refund Amount": 0.0 if i % 9 == 0 else round(max(price[ln], 0), 2)})
    rows["ret"] = rets
    ins = []
    for i in range(1, 51):
        row = {"Inspection": key("ins", i), "Return": [key("ret", (i if i <= 40 else r.randrange(1, 41)))],
               "Condition": r.choice(["Resellable", "Damaged", "Needs Cleaning"])}
        if r.random() < 0.3:
            row["Notes"] = "Seam check\nLining intact"
        ins.append(row)
    rows["ins"] = ins
    rows["rst"] = [{"Restock Ref": key("rst", i), "Inspection": [key("ins", r.randrange(1, 51))], "Qty": r.choice([0, 1, 1, 2, 5]),
                    "Status": r.choice(["Queued", "Shipped", "Received"])} for i in range(1, 51)]


TITLES = ["Chief Executive", "VP", "Director", "Manager", "Lead", "Associate"]


def gen_emp(cfg, rows, plan):
    r = rng_for(cfg["seed"], "emp")
    levels = [(1, 1), (2, 5), (6, 20), (21, 45), (46, 75), (76, 100)]
    out = []
    for i in range(1, 101):
        lv = [n for n, (a, b) in enumerate(levels, 1) if a <= i <= b][0]
        row = {"Employee ID": key("emp", i), "Name": pname(i + 700), "Title": TITLES[lv - 1], "Email": email(i + 700),
               "Phone": phone(r), "Hire Date": d_iso(r, 2000, 2026), "Org Level": lv}
        if lv == 1:
            row["Reports To"] = [row["Employee ID"]]                      # CEO reports to self
        else:
            a, b = levels[lv - 2]
            row["Reports To"] = [key("emp", r.randrange(a, b + 1))]
        if i != 100:
            row["Works At"] = [key("loc", r.randrange(1, 61))]
        out.append(row)
    out[49]["Reports To"] = [key("emp", 51)]                              # A manages B ...
    out[50]["Reports To"] = [key("emp", 50)]                              # ... and B manages A
    rows["emp"] = out


def gen_glossary(cfg, rows, plan):
    r = rng_for(cfg["seed"], "glo")
    pre = ["Notch", "Peak", "Shawl", "Patch", "Welt", "Flap", "Besom", "Gorge", "Throat", "Barchetta"]
    suf = ["Lapel", "Pocket", "Seam", "Vent", "Cuff"]
    out = []
    for i in range(50):
        row = {"Term": "%s %s" % (pre[i % 10], suf[i // 10]), "Definition": "Fictional glossary entry #%d. Café-style detail, 100%% invented." % i}
        row["Language"] = r.choice(["English", "Italian", "French", None])
        out.append(row)
    rows["glo"] = out


# --------------------------------------------------------------------------- lab tables
def gen_showcase(cfg, rows, plan):
    r = rng_for(cfg["seed"], "shw")
    n = cfg["collab_count"]
    out = []
    for i in range(1, 61):
        row = {"Showcase ID": key("shw", i), "Single Line Text": "Row %d" % i,
               "Long Text": "Line one\nLine two \U0001F9F5\n\"quoted\", with commas",
               "Rich Text": "**bold** and _italic_\n\n- bullet %d" % i,
               "Number": round(r.uniform(-50, 500), 2), "Currency": round(r.uniform(0, 900), 2),
               "Percent": round(r.uniform(0, 1), 3), "Rating": r.choice([1, 2, 3, 4, 5]),
               "Duration": r.choice([0, 60, 3600, 7325]), "Date": d_iso(r, 2020, 2027),
               "Date Time": dt_iso(r), "Single Select": r.choice(["Red", "Green", "Blue", "Black"]),
               "Multi Select": r.sample(["Wool", "Silk", "Linen", "Cotton"], r.choice([0, 1, 2, 4])),
               "Email": "show.%d@example.com" % i, "URL": "https://example.com/item/%d" % i, "Phone": phone(r),
               "Barcode": {"text": "SHW%06d" % i}}
        if r.random() < 0.5:
            row["Checkbox"] = True
        c = collab(r, n, 0.3)
        if c:
            row["Collaborator"] = c
        if n:
            row["Collaborators"] = ["collab%d@example.com" % (1 + k) for k in range(n)][: r.choice([0, 1, n])]
        if i % 6:
            row["Featured Item"] = [key("itm", r.randrange(1, 101))]
        if i <= 12:
            plan.add("shw", row["Showcase ID"], "Attachments", "%s_a.txt" % row["Showcase ID"], ff.txt("showcase %d" % i))
            if i % 4 == 0:
                plan.add("shw", row["Showcase ID"], "Attachments", "%s_b.png" % row["Showcase ID"], ff.png_gradient(240, 80, (100, 60, 60)))
                plan.add("shw", row["Showcase ID"], "Attachments", "%s_c.svg" % row["Showcase ID"], ff.svg("showcase %d" % i))
        out.append(row)
    rows["shw"] = out


def gen_dql(cfg, rows, plan):
    r = rng_for(cfg["seed"], "dql")
    n = cfg["collab_count"]
    floats = [0.0, -1.0, -273.15, 0.00000001, 0.1 + 0.2, 1 / 3, 999999999999999.0, -999999999999999.0, 12345.12345678, 2.5, 0.30000000000000004, 1e-9]
    ints = [0, -1, 1, 2147483647, -2147483648, 999999999999999, 42]
    curs = [0.0, -0.01, 0.01, 1234567.89, 999999999999.99, 19.999]
    pcts = [0.0, 1.0, 1.5, -0.05, 0.0001, 0.12345]
    durs = [0, 1, 59, 3600, 86399, 31536000]
    dates = ["1900-01-01", "1970-01-01", "1999-12-31", "2000-01-01", "2000-02-29", "2024-02-29", "2028-02-29", "2038-01-19", "2099-12-31"]
    dts = ["2026-03-08T07:59:59.000Z", "2026-03-08T08:00:00.000Z", "2026-11-01T06:59:59.000Z", "2026-11-01T07:00:00.000Z",
           "2026-12-31T23:59:59.000Z", "2027-01-01T00:00:00.000Z", "1970-01-01T00:00:00.000Z", "2038-01-19T03:14:07.000Z",
           "2024-02-29T23:59:59.000Z", "2000-02-29T00:00:00.000Z"]
    long10k = ("Fictional long text paragraph with unicode café and emoji \U0001F457.\n" * 200)[:10000]
    texts = ["Line one\nLine two\nLine three", "Emoji \U0001F9E5\U0001F454✨ mix", "مرحبا بالعالم - نص تجريبي",
             "שלום עולם", 'She said "hello", then left', '"a","b",\n"c"', "  leading and trailing  ", "tab\there",
             "combining é vs é", "plain"]
    zips = ["02134", "00501", "01001", "02134-0001", "90210", "10001"]
    labels = ["Mall", "mall", "MALL", "Mall ", "Mall", "mall "]
    nears = ["Midnight Navy", "midnight navy", "Midnight  Navy", "Midnight Navy.", "Midnight Navy ", "Midnight-Navy", "MIDNIGHT NAVY", "Midnight Navy"]
    emails = ["a+tag@example.com", "First.Last@Example.COM", "x@sub.domain.example.com", "plain@example.com", "UPPER@EXAMPLE.COM"]
    urls = ["https://example.com/a?b=1&c=2#frag", "http://example.com", "https://example.com/ünï", "https://example.com/path%20with%20space"]
    out = []
    for i in range(1, 121):
        row = {"Row ID": key("dql", i), "Always Filled": "filled-%d" % i, "Constant Value": "CONSTANT",
               "Unique Value": "uniq-%05d-%s" % (i, format(i * 2654435761 % 99991, "05d")),
               "Near Duplicate": nears[r.randrange(len(nears))]}
        if i == 57:
            row["Filled Once"] = "only-one-value"
        row["Empty Representations"] = [None, "", "   ", "\t", "value-%d" % (i % 7), "x"][i % 6]
        if row["Empty Representations"] is None:
            del row["Empty Representations"]
        m = i % 10
        row["Multi Select Mix"] = [] if m == 0 else ([STYLES[i % 10]] if m == 1 else (list(STYLES) if m == 2 else r.sample(STYLES, r.randrange(2, 6))))
        if i % 3 == 0:
            row["Checkbox Mix"] = True
        elif i % 3 == 1:
            row["Checkbox Mix"] = False
        row["Float Edge"] = floats[(i - 1) % len(floats)] if i <= 36 else round(r.uniform(-1000, 1000), 4)
        row["Integer Edge"] = ints[(i - 1) % len(ints)] if i <= 21 else r.randrange(-1000, 1000)
        row["Currency Edge"] = curs[(i - 1) % len(curs)] if i <= 30 else round(r.uniform(-50, 5000), 2)
        row["Percent Edge"] = pcts[(i - 1) % len(pcts)] if i <= 30 else round(r.random(), 3)
        row["Rating Edge"] = r.choice([0, 1, 2, 3, 4, 5, None])
        if row["Rating Edge"] is None:
            del row["Rating Edge"]
        row["Duration Edge"] = durs[(i - 1) % len(durs)] if i <= 18 else r.randrange(0, 100000)
        row["Text Edge"] = long10k if i == 33 else texts[i % len(texts)]
        row["ZIP"] = zips[i % len(zips)]
        row["Format Label"] = labels[i % len(labels)]
        row["Typecast Select"] = "Zeta-New" if i == 118 else r.choice(["Alpha", "Beta", "Gamma", None])
        if row["Typecast Select"] is None:
            del row["Typecast Select"]
        row["Date Edge"] = dates[(i - 1) % len(dates)] if i <= 27 else d_iso(r, 1990, 2030)
        row["DateTime Edge"] = dts[(i - 1) % len(dts)] if i <= 30 else dt_iso(r)
        row["Email Edge"] = emails[i % len(emails)]
        row["URL Edge"] = urls[i % len(urls)]
        row["Phone Edge"] = phone(r)
        if i % 4:
            row["Barcode"] = {"text": "DQL%07d" % i}
        row["Rich Text Edge"] = "**row %d**\n- item" % i
        c = collab(r, n, 0.5)
        if c:
            row["Collaborator Mix"] = c
        if n:
            row["Collaborators Mix"] = ["collab%d@example.com" % (1 + k) for k in range(n)][: [0, 1, n][i % 3]]
        out.append(row)
    rows["dql"] = out


def gen_naming(cfg, rows, plan, schema_table):
    r = rng_for(cfg["seed"], "nec")
    names = [f["name"] for f in schema_table["fields"]]
    out = []
    for i in range(1, 21):
        row = {names[0]: key("nec", i, 2)}
        for j, nm in enumerate(names[1:], 1):
            if (i + j) % 3:
                row[nm] = "v%d-%d" % (i, j)
        out.append(row)
    rows["nec"] = out


def gen_attlab(cfg, rows, plan):
    r = rng_for(cfg["seed"], "att")
    out = []
    scen = {}

    def S(i, label, files, method="api", note="", dup=""):
        scen[i] = (label, files, method, note, dup)
    same_png = ff.png_gradient(240, 90, (70, 70, 70))
    S(1, "zero files", [])
    S(2, "one tiny txt", [("one.txt", ff.txt("single file"))])
    S(3, "three files png+svg+csv", [("p.png", ff.png_gradient(200, 80, (10, 80, 90))), ("v.svg", ff.svg("three")), ("t.csv", ff.csv_bytes([["a", "b"], [1, 2]]))])
    S(4, "five files mixed", [("f%d.%s" % (k, e), (ff.txt("f%d" % k) if e == "txt" else ff.svg("f%d" % k))) for k, e in enumerate(["txt", "svg", "txt", "svg", "txt"])])
    S(5, "identical filenames same cell, different content", [("receipt.pdf", ff.pdf(["receipt A"])), ("receipt.pdf", ff.pdf(["receipt B"]))])
    S(6, "identical filename AND content same cell", [("same.txt", ff.txt("dup content")), ("same.txt", ff.txt("dup content"))], dup="in-cell")
    S(7, "same filename as row 5 (cross-record)", [("receipt.pdf", ff.pdf(["receipt C"]))])
    S(8, "spaces in name", [("my receipt final (v2).pdf", ff.pdf(["spaces"]))])
    S(9, "unicode name", [("résumé_図面_\U0001F4CE.txt", ff.txt("unicode name"))])
    S(10, "special chars", [("a&b=c;d,e#f%g+h'i.txt", ff.txt("special"))], note="Airtable may rewrite the filename")
    S(11, "no extension", [("README_noext", ff.txt("no extension"))])
    S(12, "very long name", [(("long_" + "n" * 240 + ".txt"), ff.txt("long name"))], method="try", note="255-char filename; Airtable limit unverified")
    S(13, "checksum duplicate A", [("copy_a.png", same_png)], dup="x-record")
    S(14, "checksum duplicate B", [("copy_b.png", same_png)], dup="x-record")
    S(15, "medium ~300KB", [("medium_300k.png", ff.png_noise(300, 330, "m300"))])
    S(16, "medium ~1.5MB", [("medium_1500k.png", ff.png_noise(700, 710, "m1500"))])
    S(17, "large ~4.5MB (API ok)", [("large_4_5mb.png", ff.png_noise(1200, 1250, "l45", exact_size=4_500_000))])
    S(18, "over 5MB (MANUAL upload)", [("over_5mb.png", ff.png_noise(1300, 1500, "o5"))], method="manual", note="exceeds the 5 MB direct-upload limit; upload through the Airtable UI or a public URL")
    S(19, "csv with commas/quotes", [("quoted.csv", ff.csv_bytes([["a,b", 'he said "hi"'], ["x", "y\nz"]]))])
    S(20, "svg", [("shape.svg", ff.svg("lab svg"))])
    S(21, "txt unicode contents", [("uni.txt", ff.txt("café ☕ مرحبا"))])
    S(22, "pdf", [("doc.pdf", ff.pdf(["lab pdf", "line 2"]))])
    S(23, "dotfile", [(".hidden", ff.txt("dotfile"))], method="try")
    S(24, "uppercase extension", [("PHOTO.PNG", ff.png_gradient(200, 80, (120, 40, 40)))])
    S(25, "double extension gz", [("archive.tar.gz", ff.gz(ff.txt("archive")))])
    S(26, "extension/MIME mismatch (png bytes named .jpg)", [("looks_like.jpg", ff.png_gradient(200, 80, (40, 120, 40)))], note="contentType sent as image/jpeg")
    S(27, "zero-byte file", [("empty.txt", b"")], method="rejected", note="Airtable rejects empty files (BAD_REQUEST, confirmed live 2026-11-08); the cell stays empty")
    jp = ff.jpeg(28, "lab jpeg")
    S(28, "real JPEG (Pillow only)", [("photo.jpg", jp)] if jp else [], note="skipped when Pillow is not installed")
    S(29, "12 files in one cell", [("many_%02d.txt" % k, ff.txt("many %d" % k)) for k in range(12)])
    S(30, "same png attached to this and row 13/14", [("copy_c.png", same_png)], dup="x-record")
    for i in range(1, 31):
        label, files, method, note, dup = scen[i]
        k = key("att", i, 2)
        out.append({"Lab ID": k, "Scenario": label})
        for fn, data in files:
            plan.add("att", k, "Files", fn, data, method=method, note=note, dup=dup)
    rows["att"] = out


def gen_wide(cfg, rows, plan):
    r = rng_for(cfg["seed"], "wide")
    for k in range(1, 7):
        rows["qp%d" % k] = [{"Parent ID": "qp%d_%02d" % (k, i)} for i in range(1, 9)]
    out = []
    for i in range(1, 61):
        row = {"Row ID": key("wide", i)}
        for n in range(1, 27):
            if r.random() < 0.3:
                row["Long Text %02d" % n] = "Long text %d/%d\n%s" % (i, n, "lorem fictional " * r.randrange(1, 12))
        for nm in ["A", "B", "C"] + ["%02d" % x for x in range(4, 16)]:
            if r.random() < 0.8:
                row["Number " + nm] = round(r.uniform(-100, 1000), 2)
        for nm in ["A", "B", "C"] + ["%02d" % x for x in range(4, 13)]:
            if r.random() < 0.8:
                row["Text " + nm] = "t%s-%d" % (nm, r.randrange(30))
        if r.random() < 0.5:
            row["Flag"] = True
        for n in range(1, 37):
            pk = (n - 1) % 6 + 1
            m = r.choice([0, 0, 1, 1, 2])
            if m:
                row["Link %02d" % n] = ["qp%d_%02d" % (pk, x) for x in r.sample(range(1, 9), m)]
        row["Launch Date"] = d_iso(r, 2025, 2027)
        row["Reviewed At"] = dt_iso(r)
        row["Status"] = r.choice(["Draft", "Review", "Live"])
        row["Tags"] = r.sample(["A", "B", "C", "D"], r.choice([0, 1, 2]))
        row["Score"] = r.choice([1, 2, 3, 4, 5])
        row["Budget"] = round(r.uniform(0, 9999), 2)
        row["Progress"] = round(r.random(), 2)
        row["Contact"] = "wide%d@example.com" % i
        row["Link URL"] = "https://example.com/w/%d" % i
        row["Hotline"] = phone(r)
        out.append(row)
    rows["wide"] = out


# --------------------------------------------------------------------------- base 2
def gen_ops(cfg, rows, plan):
    r = rng_for(cfg["seed"], "ops")
    rows["rl2"] = [{"id": key("rl2", i), "City": CITIES[(i * 3) % len(CITIES)][0], "Region": r.choice(["North", "South", "East", "West"]),
                    "Freestanding/Mall": r.choice(["Freestanding", "Mall", "Outlet"])} for i in range(1, 16)]
    itm = []
    for i in range(1, 51):
        cost = float(r.randrange(10, 900))
        row = {"id": key("itm2", i), "Name": "%s %s" % (FABRICS[i % 12], GARMENTS[(i * 7) % 12]), "Price": "${:,.2f}".format(cost * 3),
               "Cost": cost}
        if r.random() < 0.2:
            row["Discontinued"] = True
        itm.append(row)
        if i <= 15:
            if i % 2:
                plan.add("itm2", row["id"], "Spec Sheet", "%s_spec.pdf" % row["id"], ff.pdf(["Spec sheet %s" % row["id"], row["Name"]]))
            else:
                plan.add("itm2", row["id"], "Spec Sheet", "%s_spec.txt" % row["id"], ff.txt("Spec %s" % row["id"]))
    rows["itm2"] = itm
    rows["glo2"] = [{"Term": "%s %s" % (["Notch", "Peak", "Shawl"][i % 3], ["Lapel", "Pocket", "Seam", "Vent"][i % 4]),
                     "Definition": "Ops glossary entry %d" % i} for i in range(10)]
    vn = ["Harrow Finch Textiles", "Brightwater Mills", "Kettleridge Leather", "Orsini Silk House", "Pennant Buttons", "Vantage Linings",
          "Alder Lane Wool", "Cobalt Dye Works", "Fenwick Zippers", "Marlow Packaging", "Sable Trims", "Ironside Buckles"]
    ven = []
    for i, n in enumerate(vn):
        row = {"Vendor": n, "Contact Email": "vendor.%s@example.com" % slug(n)}
        if i not in (4, 9):
            row["Preferred Items"] = [x["id"] for x in r.sample(itm, r.randrange(1, 7))]
        ven.append(row)
    rows["ven"] = ven
    shp = []
    for i in range(1, 81):
        row = {"Shipment No": "SHP-%04d" % i, "Destination": [key("rl2", r.randrange(1, 16))],
               "Carrier": r.choice(["Fictional Freight", "Example Express", "Sample Couriers"]), "Shipped": d_iso(r, 2025, 2026)}
        if i == 80:
            del row["Destination"]
        if r.random() < 0.6:
            row["Delivered"] = True
        shp.append(row)
        if i <= 30:
            plan.add("shp", row["Shipment No"], "Manifest", "%s_manifest.csv" % row["Shipment No"],
                     ff.csv_bytes([["line", "qty"], ["SLN-%04d" % i, r.randrange(1, 40)]]))
    rows["shp"] = shp
    rows["sln"] = [{"Line": "SLN-%04d" % i, "Shipment": ["SHP-%04d" % r.randrange(1, 81)], "Item": [key("itm2", r.randrange(1, 51))],
                    "Qty": r.choice([0, 1, 2, 5, 10, 24])} for i in range(1, 151)]


# --------------------------------------------------------------------------- driver
def generate(schema, cfg):
    rows = {}
    plan = Plan()
    gen_loc(cfg, rows, plan)
    gen_mgr(cfg, rows, plan)
    gen_rep(cfg, rows, plan)
    gen_cli(cfg, rows, plan)
    gen_itm(cfg, rows, plan)
    gen_purchases(cfg, rows, plan)
    gen_cycle3(cfg, rows, plan)
    gen_m2m(cfg, rows, plan)
    gen_campaigns(cfg, rows, plan)
    gen_supply(cfg, rows, plan)
    gen_special(cfg, rows, plan)
    gen_returns(cfg, rows, plan)
    gen_emp(cfg, rows, plan)
    gen_glossary(cfg, rows, plan)
    gen_showcase(cfg, rows, plan)
    gen_dql(cfg, rows, plan)
    nec = [t for t in schema["bases"]["ff_main"]["tables"] if t["key"] == "nec"][0]
    gen_naming(cfg, rows, plan, nec)
    gen_attlab(cfg, rows, plan)
    gen_wide(cfg, rows, plan)
    gen_ops(cfg, rows, plan)
    return rows, plan.items
