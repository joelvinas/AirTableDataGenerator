"""Reference implementation of the migrator's load-order rules (used only to build the answer key).

Rules reproduced from the two sample reports:
  * every link field A->B (A != B) makes A the child and B the parent ("literal" mode); self-links ignored
  * strongly connected components (Tarjan) are a single step; members are listed by (name, table id)
  * steps are emitted parent-first by Kahn's algorithm; ties broken by smallest (table name, table id) in the step
  * depth = longest chain of parent steps above the step (0 when no parents)
  * "resolve" mode: for a two-way pair where exactly ONE side prefers a single record, that side's table is the
    child and only the child->parent dependency is kept.  Both-single and neither-single pairs stay mutual (cycle).
"""
import heapq


def _fields(base):
    for t in base["tables"]:
        for f in t["fields"]:
            if f["type"] == "multipleRecordLinks":
                yield t, f


def build_edges(base, mode):
    """Return (edges, treatment) where edges = {(child_key, parent_key): [field refs]} and
    treatment[(table_key, field_name)] = dict(kind=..., kept=bool)."""
    tmap = {t["key"]: t for t in base["tables"]}
    by_id = {f["id"]: (t, f) for t, f in _fields(base)}
    edges = {}
    kept = {}
    for t, f in _fields(base):
        lk = f["link"]
        tgt = lk["target"]
        if tgt == t["key"]:
            kept[(t["key"], f["name"])] = "self"
            continue
        keep = True
        if mode == "resolve" and lk["inverse_id"] and lk["inverse_id"] in by_id:
            it, inf = by_id[lk["inverse_id"]]
            s1, s2 = lk["single"], inf["link"]["single"]
            if s1 != s2:
                keep = bool(s1)            # only the single-preferring side (child) keeps its dependency
                if not keep:
                    kept[(t["key"], f["name"])] = "derived"
        if keep:
            edges.setdefault((t["key"], tgt), []).append((t["key"], f["name"]))
            kept[(t["key"], f["name"])] = "edge"
    return edges, kept


def sccs(nodes, adj):
    index = {}
    low = {}
    on = set()
    stack = []
    out = []
    counter = [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for n in nodes:
        if n not in index:
            visit(n)
    return out


def load_order(base, mode):
    tmap = {t["key"]: t for t in base["tables"]}
    edges, kept = build_edges(base, mode)
    skey = lambda k: (tmap[k]["name"], tmap[k]["id"])
    nodes = sorted(tmap, key=skey)
    adj = {}
    for (c, p) in edges:
        adj.setdefault(c, []).append(p)
    comps = sccs(nodes, adj)
    comp_of = {}
    for i, comp in enumerate(comps):
        for k in comp:
            comp_of[k] = i
    members = {i: sorted(c, key=skey) for i, c in enumerate(comps)}
    cparents = {i: set() for i in members}
    for (c, p) in edges:
        if comp_of[c] != comp_of[p]:
            cparents[comp_of[c]].add(comp_of[p])
    ckey = {i: skey(members[i][0]) for i in members}
    # Kahn with priority queue
    indeg = {i: len(cparents[i]) for i in members}
    children = {i: [] for i in members}
    for i, ps in cparents.items():
        for p in ps:
            children[p].append(i)
    heap = [(ckey[i], i) for i in members if indeg[i] == 0]
    heapq.heapify(heap)
    order = []
    depth = {}
    while heap:
        _, i = heapq.heappop(heap)
        order.append(i)
        depth[i] = 1 + max((depth[p] for p in cparents[i]), default=-1)
        for ch in children[i]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                heapq.heappush(heap, (ckey[ch], ch))
    rows = []
    n = 0
    self_tables = {tk for (tk, fn), v in kept.items() if v == "self"}
    parents_of = {k: set() for k in tmap}
    for (c, p) in edges:
        parents_of[c].add(p)
    for i in order:
        for k in members[i]:
            n += 1
            rows.append({
                "base": base["label"], "table": tmap[k]["name"], "table_key": k, "local_table_id": tmap[k]["id"],
                "load_no": n, "depth": depth[i],
                "parents": "; ".join(sorted((tmap[p]["name"] for p in parents_of[k]), key=lambda s: s)),
                "in_cycle": len(members[i]) > 1, "self_link": k in self_tables,
                "cycle_members": "; ".join(tmap[m]["name"] for m in members[i]) if len(members[i]) > 1 else "",
            })
    treat = {}
    for t, f in _fields(base):
        k = (t["key"], f["name"])
        kind = kept[k]
        tgt = f["link"]["target"]
        if kind == "self":
            treat[k] = ("Yes", "SELF_LINK", "links to its own table; set after the table's records exist")
        elif kind == "derived":
            treat[k] = ("No", "INVERSE_DERIVED",
                        "parent-side field of a resolved two-way pair; value mirrors the child's field (assumed handled with the child)")
        elif comp_of[t["key"]] == comp_of[tgt]:
            treat[k] = ("Yes", "CYCLE", "member of a dependency cycle; set after both tables' records exist")
        else:
            treat[k] = ("No", "ORDERS_LOAD", "parent table loads first; link can be set while loading")
    return rows, treat
