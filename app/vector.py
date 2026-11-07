from app.observability import trace
import logging
import os
import time
from functools import lru_cache

from pinecone import Pinecone, DenseVectorQuery
from app.config import settings


log = logging.getLogger(__name__)

# Name of the dense_vector field in the index schema (Pinecone console -> SCHEMA tab).
VECTOR_FIELD = os.getenv("PINECONE_VECTOR_FIELD", "embedding")
_RESERVED = {"_id", "_score", VECTOR_FIELD}
# Fields written at ingest (add any other metadata keys your rag.py reads)
META_FIELDS = ["text", "title", "document_id", "page", "allowed_groups", "owner_sub"]


def _http_status(exc):
    """Best-effort HTTP status from a Pinecone exception (works across SDK versions)."""
    for attr in ("status", "status_code", "code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    return {"NotFoundError": 404, "ConflictError": 409}.get(type(exc).__name__)


@lru_cache(maxsize=1)
def index():
    """Return an initialized Pinecone document index. Safe for repeated requests in one process."""
    s = settings()
    if not s.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is missing from .env")
    if not s.pinecone_index_name:
        raise RuntimeError("PINECONE_INDEX_NAME is missing from .env")
    pc = Pinecone(api_key=s.pinecone_api_key)
    name = s.pinecone_index_name

    try:
        pc.describe_index(name)
    except Exception as exc:
        # Only create on an actual 404; never hide auth/network failures.
        if _http_status(exc) != 404:
            raise
        log.info("Creating Pinecone document index %s (field=%s, dimension=%d, metric=cosine)",
                 name, VECTOR_FIELD, s.embed_dim)
        try:
            pc.indexes.create(
                name=name,
                schema={"fields": {VECTOR_FIELD: {
                    "type": "dense_vector", "dimension": s.embed_dim, "metric": "cosine"}}},
                deployment={"deployment_type": "managed",
                            "cloud": s.pinecone_cloud, "region": s.pinecone_region},
            )
        except Exception as create_exc:
            # Another process may have created the index concurrently.
            if _http_status(create_exc) != 409:
                raise

    deadline = time.monotonic() + s.pinecone_ready_timeout
    while not _is_ready(pc.describe_index(name)):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Pinecone index {name} was not ready within {s.pinecone_ready_timeout}s")
        time.sleep(3)
    log.info("Pinecone index %s ready (vector field=%s)", name, VECTOR_FIELD)
    return pc.Index(name)


def _is_ready(info):
    status = getattr(info, "status", None)
    if isinstance(status, dict):
        return bool(status.get("ready"))
    return bool(getattr(status, "ready", False))


def namespace(tenant):
    return "tenant-" + tenant


def _to_document(r):
    """Legacy {'id','values','metadata'} record -> flat document."""
    meta = {k: v for k, v in (r.get("metadata") or {}).items()
            if v is not None and k not in _RESERVED}
    return {"_id": r["id"], VECTOR_FIELD: r["values"], **meta}

def _fields(doc):
    """Pull stored fields off a v10 Document (fields are key-accessed, not attributes)."""
    out = {}
    try:
        data = doc.to_dict() or {}
    except Exception:
        data = {}
    # Flatten any nested container the SDK may use
    for key in ("fields", "_fields", "document", "data"):
        if isinstance(data.get(key), dict):
            data.update(data.pop(key))
    out.update({k: v for k, v in data.items()
                if k not in _RESERVED and k not in {"id", "score"}})
    for k in META_FIELDS:
        if k not in out:
            v = doc.get(k)
            if v is not None:
                out[k] = v
    return out

@trace("upsert")
def upsert(tenant, records):
    docs = [_to_document(r) for r in records]
    if not docs:
        return None
    return index().documents.upsert(namespace=namespace(tenant), documents=docs)



@trace("search")
def search(tenant, vector, groups, owner, limit=5):
    acl = {"$or": [{"allowed_groups": {"$in": list(groups)}},
                   {"owner_sub": {"$eq": owner}}]}
    result = index().documents.search(
        namespace=namespace(tenant),
        top_k=limit,
        score_by=[DenseVectorQuery(field=VECTOR_FIELD, values=vector)],
        filter=acl,
        include_fields=META_FIELDS,   # skip returning the embedding (cuts egress)
    )
    return [{"id": m.id, "score": m.score, "metadata": _fields(m)} for m in result.matches]

def delete_document(tenant, ids):
    ids = list(ids or [])
    for i in range(0, len(ids), 1000):
        index().documents.delete(namespace=namespace(tenant), ids=ids[i:i + 1000])