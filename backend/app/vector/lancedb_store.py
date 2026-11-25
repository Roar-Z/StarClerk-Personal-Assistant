"""LanceDB 本地向量库：两张表 documents（知识库分块）+ memories（长期记忆向量）。

LanceDB 用嵌入式模式，无需服务进程；数据落在 data/lancedb。
"""
from __future__ import annotations

import logging
from typing import Any

import lancedb
import pyarrow as pa

from ..config import settings
from ..llm.client import embed

log = logging.getLogger("vector")

_docs = "documents"
_mems = "memories"


def _db():
    return lancedb.connect(str(settings.lancedb_path))


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("doc_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("chunk", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.embed_dim)),
        ]
    )


def _mem_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("kind", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), settings.embed_dim)),
        ]
    )


def _table(name: str, schema: pa.Schema):
    db = _db()
    if name in db.table_names():
        return db.open_table(name)
    return db.create_table(name, schema=schema)


def reset() -> None:
    """维度/模型切换后重建（MVP 阶段直接重建，不做迁移）。"""
    db = _db()
    for n in (_docs, _mems):
        if n in db.table_names():
            db.drop_table(n)


def add_document(doc_id: str, source: str, chunks: list[str]) -> int:
    if not chunks:
        return 0
    vectors = embed(chunks)
    rows = [
        {
            "id": f"{doc_id}-{i}",
            "doc_id": doc_id,
            "source": source,
            "chunk": i,
            "text": t,
            "vector": vectors[i],
        }
        for i, t in enumerate(chunks)
    ]
    _table(_docs, _schema()).add(rows)
    return len(rows)


def search_documents(query: str, top_k: int = 5, doc_scope: str = "") -> list[dict[str, Any]]:
    db = _db()
    if _docs not in db.table_names():
        return []
    qv = embed([query])[0]
    q = db.open_table(_docs).search(qv).limit(top_k)
    if doc_scope:
        q = q.where(f"doc_id IN ({','.join(repr(x) for x in doc_scope.split(','))})")
    out = []
    for r in q.to_list():
        out.append(
            {"text": r["text"], "source": r["source"], "doc_id": r["doc_id"], "score": float(r.get("_distance", 0))}
        )
    return out


def add_memory(mem_id: str, text: str, kind: str = "fact") -> None:
    _table(_mems, _mem_schema()).add([{"id": mem_id, "text": text, "kind": kind, "vector": embed([text])[0]}])


def search_memories(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    db = _db()
    if _mems not in db.table_names():
        return []
    qv = embed([query])[0]
    return [{"id": r["id"], "text": r["text"], "kind": r["kind"]} for r in db.open_table(_mems).search(qv).limit(top_k).to_list()]


def delete_document(doc_id: str) -> None:
    db = _db()
    if _docs in db.table_names():
        db.open_table(_docs).delete(f"doc_id = '{doc_id}'")


def delete_memory(mem_id: str) -> None:
    db = _db()
    if _mems in db.table_names():
        db.open_table(_mems).delete(f"id = '{mem_id}'")


def list_documents() -> list[dict[str, Any]]:
    """按文档聚合分块数，供 /api/rag/documents 展示。"""
    db = _db()
    if _docs not in db.table_names():
        return []
    rows = db.open_table(_docs).to_arrow().select(["doc_id", "source"]).to_pylist()
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        item = agg.setdefault(r["doc_id"], {"doc_id": r["doc_id"], "source": r["source"], "chunks": 0})
        item["chunks"] += 1
    return sorted(agg.values(), key=lambda x: str(x["source"]))


def stats() -> dict[str, int]:
    db = _db()
    names = db.table_names()
    return {
        "chunks": db.open_table(_docs).count_rows() if _docs in names else 0,
        "memories": db.open_table(_mems).count_rows() if _mems in names else 0,
        "dim": settings.embed_dim,
    }
