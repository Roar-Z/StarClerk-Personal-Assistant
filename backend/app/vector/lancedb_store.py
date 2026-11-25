"""LanceDB 本地向量库：documents（资料分块，带工作区）+ memories（长期记忆）。

嵌入式模式，不用起服务，数据在 data/lancedb。
工作区是多知识库功能（Pro），免费版统一用 default。
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
DEFAULT_WS = "default"


def _db():
    return lancedb.connect(str(settings.lancedb_path))


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("doc_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("workspace", pa.string()),
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


def _docs_table():
    """打开分块表；早期版本没有 workspace 字段，顺手重建掉。"""
    db = _db()
    if _docs in db.table_names():
        t = db.open_table(_docs)
        if "workspace" not in t.schema.names:
            log.warning("向量表结构太旧，重建 documents（资料要重新导入）")
            db.drop_table(_docs)
        else:
            return t
    return db.create_table(_docs, schema=_schema())


def reset() -> None:
    db = _db()
    for n in (_docs, _mems):
        if n in db.table_names():
            db.drop_table(n)


def _quote(text: str) -> str:
    return text.replace("'", "''")


# ---------------------------------------------------------------- 文档分块
def add_document(
    doc_id: str, source: str, chunks: list[str], workspace: str = DEFAULT_WS
) -> int:
    """增量写入：同一 doc_id 已有的分块跳过，只给新内容做向量化。

    重新导入一份改过的文档时，前面没变的段落不会重复花钱算 embedding。
    """
    if not chunks:
        return 0
    table = _docs_table()
    have: set[str] = set()
    next_index = 0
    try:
        old = table.to_arrow().select(["doc_id", "chunk", "text"]).to_pylist()
        for r in old:
            if r["doc_id"] != doc_id:
                continue
            have.add(str(r["text"]))
            next_index = max(next_index, int(r["chunk"]) + 1)
    except Exception as e:  # noqa: BLE001  空表/字段缺失都不影响新建
        log.debug("读旧分块失败：%s", e)

    fresh = [c for c in chunks if c not in have]
    if not fresh:
        return 0
    vectors = embed(fresh)
    rows = [
        {
            "id": f"{doc_id}-{next_index + i}",
            "doc_id": doc_id,
            "source": source,
            "workspace": workspace or DEFAULT_WS,
            "chunk": next_index + i,
            "text": text,
            "vector": vectors[i],
        }
        for i, text in enumerate(fresh)
    ]
    table.add(rows)
    return len(rows)


def search_documents(
    query: str, top_k: int = 5, doc_scope: str = "", workspace: str = ""
) -> list[dict[str, Any]]:
    table = _docs_table()
    if table.count_rows() == 0:
        return []
    qv = embed([query])[0]
    q = table.search(qv).limit(top_k)
    where = []
    if doc_scope:
        where.append(f"doc_id IN ({','.join(repr(x) for x in doc_scope.split(','))})")
    if workspace:
        where.append(f"workspace = '{_quote(workspace)}'")
    if where:
        q = q.where(" AND ".join(where))
    return [
        {
            "text": r["text"],
            "source": r["source"],
            "doc_id": r["doc_id"],
            "workspace": r.get("workspace", DEFAULT_WS),
            "score": float(r.get("_distance", 0)),
        }
        for r in q.to_list()
    ]


def document_text(doc_id: str, limit_chars: int = 20000) -> str:
    """按分块顺序拼回正文，思维导图模块要用。"""
    table = _docs_table()
    rows = [r for r in table.to_arrow().select(["doc_id", "chunk", "text"]).to_pylist() if r["doc_id"] == doc_id]
    rows.sort(key=lambda r: int(r["chunk"]))
    text = "\n\n".join(str(r["text"]) for r in rows)
    return text[:limit_chars]


def delete_document(doc_id: str) -> None:
    table = _docs_table()
    table.delete(f"doc_id = '{_quote(doc_id)}'")


def move_document(doc_id: str, workspace: str) -> int:
    """把一份资料挪到别的工作区，分块不用重算向量。"""
    table = _docs_table()
    n = table.update(where=f"doc_id = '{_quote(doc_id)}'", values={"workspace": workspace or DEFAULT_WS})
    return int(n or 0)


def list_documents(workspace: str = "") -> list[dict[str, Any]]:
    """按文档聚合分块数；传 workspace 就只看那个工作区。"""
    table = _docs_table()
    if table.count_rows() == 0:
        return []
    rows = table.to_arrow().select(["doc_id", "source", "workspace"]).to_pylist()
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        ws = r.get("workspace") or DEFAULT_WS
        if workspace and ws != workspace:
            continue
        item = agg.setdefault(
            r["doc_id"], {"doc_id": r["doc_id"], "source": r["source"], "workspace": ws, "chunks": 0}
        )
        item["chunks"] += 1
    return sorted(agg.values(), key=lambda x: str(x["source"]))


def list_workspaces() -> list[dict[str, Any]]:
    """按工作区统计文档数和分块数，下拉框直接用。"""
    docs = list_documents()
    agg: dict[str, dict[str, Any]] = {}
    for d in docs:
        item = agg.setdefault(d["workspace"], {"name": d["workspace"], "docs": 0, "chunks": 0})
        item["docs"] += 1
        item["chunks"] += int(d["chunks"])
    if DEFAULT_WS not in agg:
        agg[DEFAULT_WS] = {"name": DEFAULT_WS, "docs": 0, "chunks": 0}
    return sorted(agg.values(), key=lambda x: (-x["docs"], x["name"]))


def count_documents(workspace: str = "") -> int:
    return len(list_documents(workspace))


# ---------------------------------------------------------------- 记忆向量
def add_memory(mem_id: str, text: str, kind: str = "fact") -> None:
    _table(_mems, _mem_schema()).add([{"id": mem_id, "text": text, "kind": kind, "vector": embed([text])[0]}])


def search_memories(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    db = _db()
    if _mems not in db.table_names():
        return []
    if db.open_table(_mems).count_rows() == 0:
        return []
    qv = embed([query])[0]
    return [
        {"id": r["id"], "text": r["text"], "kind": r["kind"]}
        for r in db.open_table(_mems).search(qv).limit(top_k).to_list()
    ]


def delete_memory(mem_id: str) -> None:
    db = _db()
    if _mems in db.table_names():
        db.open_table(_mems).delete(f"id = '{_quote(mem_id)}'")


def stats() -> dict[str, int]:
    db = _db()
    names = db.table_names()
    return {
        "chunks": db.open_table(_docs).count_rows() if _docs in names else 0,
        "memories": db.open_table(_mems).count_rows() if _mems in names else 0,
        "dim": settings.embed_dim,
    }
