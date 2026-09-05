"""Persistent, incrementally maintained BM25 retrieval without model dependencies."""

from __future__ import annotations

import re
import sqlite3
from typing import Iterable

QUERY_STOP_WORDS = frozenset("a an the is are was were be been what how why when where who which of to in on for and or do does explain describe please".split())

def tokens(text: str) -> list[str]:
    # Encode CJK bigrams as ASCII tokens so SQLite's unicode61 needs no extension.
    result = re.findall(r"[a-z0-9_]+", text.lower())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        parts = [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
        result.extend("z" + part.encode("utf-8").hex() for part in parts)
    return result


def ensure_index(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='kgts_fts'").fetchone():
        return
    # DDL and initial queue creation commit together, including concurrent starts.
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kgts_fts USING fts5(node_id UNINDEXED, label, body)")
    conn.execute("CREATE TABLE IF NOT EXISTS kgts_fts_dirty (node_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS kgts_fts_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT UNIQUE)")
    for operation, ref in (("INSERT", "new"), ("UPDATE", "new"), ("DELETE", "old")):
        previous = "INSERT OR REPLACE INTO kgts_fts_dirty VALUES (old.id);" if operation == "UPDATE" else ""
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS kgts_fts_{operation.lower()}
            AFTER {operation} ON nodes BEGIN
            INSERT OR REPLACE INTO kgts_fts_dirty VALUES ({ref}.id);
            {previous}
            END""")
    conn.execute("INSERT OR IGNORE INTO kgts_fts_dirty SELECT id FROM nodes")
    conn.commit()


def synchronize(conn: sqlite3.Connection) -> None:
    ensure_index(conn)
    if not conn.execute("SELECT 1 FROM kgts_fts_dirty LIMIT 1").fetchone():
        return
    # The write lock prevents an edit from being lost between indexing and dequeue.
    conn.execute("BEGIN IMMEDIATE")
    try:
        while True:
            batch = conn.execute("SELECT node_id FROM kgts_fts_dirty LIMIT 128").fetchall()
            if not batch:
                break
            for (node_id,) in batch:
                conn.execute("INSERT OR IGNORE INTO kgts_fts_keys(node_id) VALUES (?)", (node_id,))
                key = conn.execute("SELECT id FROM kgts_fts_keys WHERE node_id=?", (node_id,)).fetchone()[0]
                conn.execute("DELETE FROM kgts_fts WHERE rowid=?", (key,))
                row = conn.execute("SELECT label, content FROM nodes WHERE id=?", (node_id,)).fetchone()
                if row:
                    conn.execute("INSERT INTO kgts_fts(rowid,node_id,label,body) VALUES (?,?,?,?)",
                                 (key, node_id, " ".join(tokens(row[0] or "")), " ".join(tokens(row[1] or ""))))
                else:
                    conn.execute("DELETE FROM kgts_fts_keys WHERE id=?", (key,))
                conn.execute("DELETE FROM kgts_fts_dirty WHERE node_id=?", (node_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def search(conn: sqlite3.Connection, query: str, *, limit: int,
           node_type: str | None = None, allowed_ids: Iterable[str] | None = None) -> list[sqlite3.Row]:
    terms = [term for term in dict.fromkeys(tokens(query[:2000])) if term not in QUERY_STOP_WORDS][:64]
    if not terms or limit <= 0:
        return []
    synchronize(conn)
    clauses = ["kgts_fts MATCH ?"]
    params: list = [" OR ".join('"' + term + '"' for term in terms)]
    if node_type:
        clauses.append("n.type=?")
        params.append(node_type)
    if allowed_ids is not None:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS retrieval_scope (id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM retrieval_scope")
        conn.executemany("INSERT OR IGNORE INTO retrieval_scope VALUES (?)", ((v,) for v in allowed_ids))
        clauses.append("n.id IN (SELECT id FROM retrieval_scope)")
    params.append(limit)
    return conn.execute(f"""SELECT n.*, bm25(kgts_fts, 0.0, 4.0, 1.0) AS bm25_rank
        FROM kgts_fts JOIN nodes n ON n.id=kgts_fts.node_id
        WHERE {' AND '.join(clauses)} ORDER BY bm25_rank, n.id LIMIT ?""", params).fetchall()
