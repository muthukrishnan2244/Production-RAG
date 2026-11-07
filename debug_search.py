# debug_search.py
from app.vector import index, search, namespace

ns = namespace("demo-workspace")
idx = index()

# 1. Reuse a stored chunk's embedding as the query vector
any_id = next(iter(idx.documents.list(namespace=ns, limit=1))).id
doc = idx.documents.fetch(namespace=ns, ids=[any_id]).documents[any_id]
print("FETCHED TYPE:", type(doc), "\nATTRS:", [a for a in dir(doc) if not a.startswith("_")])
vec = getattr(doc, "embedding", None) or doc["embedding"]

# 2. Raw SDK search, no ACL filter
raw = idx.documents.search(namespace=ns, top_k=3,
                           score_by=[{"type": "dense_vector", "fields": ["embedding"], "values": vec}])
m = raw.matches[0]
print("\nRAW MATCH TYPE:", type(m), "\nATTRS:", [a for a in dir(m) if not a.startswith("_")])
print("RAW MATCH:", repr(m)[:800])

# 3. Your app's search() with the ACL filter
res = search("demo-workspace", vec, {"workspace"}, "demo-operator")
print("\nAPP SEARCH COUNT:", len(res))
for r in res:
    print(r["id"], r["score"], sorted(r["metadata"].keys()))