"""Relate graph store: build the PLC-logic graph and read it back (read-only).

The graph is the single source of truth. Expressions are rebuilt from FEEDS edges
(ordered by ``pos``), never by re-parsing the stored rung source text.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import relate

from .model import (
    And,
    Const,
    Expr,
    Not,
    Or,
    Project,
    Ref,
    Rung,
    TagInfo,
    Unresolved,
)

MAX_HOPS = 60  # upper bound for every variable-length pattern / expression-depth walk

_SOURCE_LABELS = ("Tag", "Gate", "Const", "Unresolved")
_TARGET_LABELS = ("Gate", "Rung")


# --------------------------------------------------------------------------- build


class _Rows:
    """Flattened node / edge rows collected from a Project before bulk insertion."""

    def __init__(self) -> None:
        self.gates: list[dict] = []
        self.consts: list[dict] = []
        self.unresolved: list[dict] = []
        # (src_label, dst_label) -> rows {src, dst, pos}
        self.feeds: dict[tuple[str, str], list[dict]] = {
            (s, d): [] for s in _SOURCE_LABELS for d in _TARGET_LABELS
        }

    def add_expr(self, rung_id: str, expr: Expr, counter: list[int]) -> tuple[str, str]:
        """Register ``expr`` (pre-order ids ``<rung>#<n>``); return its (label, id)."""
        if isinstance(expr, Ref):
            return "Tag", expr.name
        n = counter[0]
        counter[0] += 1
        node_id = f"{rung_id}#{n}"
        if isinstance(expr, Const):
            self.consts.append({"id": node_id, "value": expr.value})
            return "Const", node_id
        if isinstance(expr, Unresolved):
            self.unresolved.append({"id": node_id, "text": expr.text})
            return "Unresolved", node_id
        if isinstance(expr, Not):
            op, children = "NOT", (expr.child,)
        elif isinstance(expr, And):
            op, children = "AND", expr.children
        elif isinstance(expr, Or):
            op, children = "OR", expr.children
        else:  # pragma: no cover - Expr is a closed union
            raise TypeError(f"unsupported expression node: {expr!r}")
        self.gates.append({"id": node_id, "op": op})
        for pos, child in enumerate(children):
            label, cid = self.add_expr(rung_id, child, counter)
            self.feeds[(label, "Gate")].append({"src": cid, "dst": node_id, "pos": pos})
        return "Gate", node_id


def _tag_rows(project: Project) -> list[dict]:
    """Tag rows for declared tags plus any tag only mentioned by rungs/snapshots."""
    tags = dict(project.tags)

    def ensure(name: str) -> None:
        if name not in tags:
            tags[name] = TagInfo(name=name, kind="undeclared")

    for rung in project.rungs:
        ensure(rung.target)
        _walk_refs(rung.expr, ensure)
    for snap in project.snapshots.values():
        for name in snap.values:
            ensure(name)
    return [
        {
            "name": t.name,
            "kind": t.kind,
            "address": t.address,
            "device": t.device,
            "desc_en": t.desc_en,
            "desc_de": t.desc_de,
            "declared": t.kind != "undeclared",
        }
        for t in tags.values()
    ]


def _walk_refs(expr: Expr, fn) -> None:
    if isinstance(expr, Ref):
        fn(expr.name)
    elif isinstance(expr, Not):
        _walk_refs(expr.child, fn)
    elif isinstance(expr, (And, Or)):
        for child in expr.children:
            _walk_refs(child, fn)


def build_store(project: Project, store_dir: Path) -> None:
    """Create a fresh store at ``store_dir`` (removing any existing one) and close it cleanly."""
    store_dir = Path(store_dir)
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store_dir.parent.mkdir(parents=True, exist_ok=True)

    rows = _Rows()
    rung_rows: list[dict] = []
    writes: list[dict] = []
    for rung in project.rungs:
        rung_rows.append(
            {
                "id": rung.id,
                "routine": rung.routine,
                "target": rung.target,
                "source": rung.source,
                "line": rung.line,
            }
        )
        writes.append({"src": rung.id, "dst": rung.target})
        label, root = rows.add_expr(rung.id, rung.expr, [0])
        rows.feeds[(label, "Rung")].append({"src": root, "dst": rung.id, "pos": 0})

    snap_rows = [{"id": s.id, "description": s.description} for s in project.snapshots.values()]
    observed = [
        {"src": s.id, "dst": name, "value": value}
        for s in project.snapshots.values()
        for name, value in s.values.items()
    ]

    conn = relate.connect(str(store_dir), read_only=False)
    try:
        conn.autocommit = False
        conn.execute("CREATE (:Project {name: $name, version: $version})",
                     {"name": project.name, "version": project.version})
        conn.execute(
            "UNWIND $rows AS row CREATE (:Tag {name: row.name, kind: row.kind, "
            "address: row.address, device: row.device, desc_en: row.desc_en, "
            "desc_de: row.desc_de, declared: row.declared})",
            {"rows": _tag_rows(project)},
        )
        _bulk(conn, "UNWIND $rows AS row CREATE (:Rung {id: row.id, routine: row.routine, "
              "target: row.target, source: row.source, line: row.line})", rung_rows)
        _bulk(conn, "UNWIND $rows AS row CREATE (:Gate {id: row.id, op: row.op})", rows.gates)
        _bulk(conn, "UNWIND $rows AS row CREATE (:Const {id: row.id, value: row.value})",
              rows.consts)
        _bulk(conn, "UNWIND $rows AS row CREATE (:Unresolved {id: row.id, text: row.text})",
              rows.unresolved)
        _bulk(conn, "UNWIND $rows AS row CREATE (:Snapshot {id: row.id, "
              "description: row.description})", snap_rows)

        for (src, dst), feed_rows in rows.feeds.items():
            skey = "name" if src == "Tag" else "id"
            _bulk(
                conn,
                f"UNWIND $rows AS row MATCH (a:{src} {{{skey}: row.src}}), "
                f"(b:{dst} {{id: row.dst}}) CREATE (a)-[:FEEDS {{pos: row.pos}}]->(b)",
                feed_rows,
            )
        _bulk(conn, "UNWIND $rows AS row MATCH (r:Rung {id: row.src}), (t:Tag {name: row.dst}) "
              "CREATE (r)-[:WRITES]->(t)", writes)
        _bulk(conn, "UNWIND $rows AS row MATCH (s:Snapshot {id: row.src}), "
              "(t:Tag {name: row.dst}) CREATE (s)-[:OBSERVED {value: row.value}]->(t)", observed)
        conn.commit()
        conn.execute(
            "CREATE FULLTEXT INDEX tag_text IF NOT EXISTS FOR (n:Tag) "
            "ON EACH [n.name, n.desc_en, n.desc_de]"
        )
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        finally:
            conn.close()
        raise
    # Always close the writer cleanly (relatedb/relate#576: empty newest WAL segment breaks reopen).
    conn.close()


def _bulk(conn: relate.Connection, cypher: str, rows: list[dict]) -> None:
    if rows:
        conn.execute(cypher, {"rows": rows})


# --------------------------------------------------------------------------- read


def open_store(store_dir: Path) -> relate.Connection:
    """Open an existing store read-only."""
    store_dir = Path(store_dir)
    if not store_dir.is_dir():
        raise FileNotFoundError(f"graph store not found: {store_dir}")
    return relate.connect(str(store_dir), read_only=True)


def _rows(conn: relate.Connection, cypher: str, params: dict | None = None) -> list[dict]:
    return [dict(r.data()) for r in conn.execute(cypher, params or {})]


def project_meta(conn: relate.Connection) -> tuple[str, str]:
    rows = _rows(conn, "MATCH (p:Project) RETURN p.name AS name, p.version AS version")
    if not rows:
        raise LookupError("store has no Project node")
    return rows[0]["name"], rows[0]["version"]


def _tag_from_row(row: dict) -> TagInfo:
    return TagInfo(
        name=row["name"],
        kind=row["kind"],
        address=row["address"] or "",
        device=row["device"] or "",
        desc_en=row["desc_en"] or "",
        desc_de=row["desc_de"] or "",
    )


_TAG_RETURN = (
    "RETURN t.name AS name, t.kind AS kind, t.address AS address, t.device AS device, "
    "t.desc_en AS desc_en, t.desc_de AS desc_de"
)


def tag_info(conn: relate.Connection, tag: str) -> TagInfo | None:
    rows = _rows(conn, f"MATCH (t:Tag {{name: $name}}) {_TAG_RETURN}", {"name": tag.upper()})
    return _tag_from_row(rows[0]) if rows else None


def all_tags(conn: relate.Connection) -> dict[str, TagInfo]:
    rows = _rows(conn, f"MATCH (t:Tag) {_TAG_RETURN} ORDER BY name")
    return {r["name"]: _tag_from_row(r) for r in rows}


def all_rungs(conn: relate.Connection) -> dict[str, str]:
    rows = _rows(conn, "MATCH (r:Rung) RETURN r.id AS id, r.source AS source ORDER BY id")
    return {r["id"]: r["source"] for r in rows}


def snapshot_ids(conn: relate.Connection) -> list[str]:
    return [r["id"] for r in _rows(conn, "MATCH (s:Snapshot) RETURN s.id AS id ORDER BY id")]


def snapshot_values(conn: relate.Connection, snapshot_id: str) -> dict[str, bool]:
    if not _rows(conn, "MATCH (s:Snapshot {id: $id}) RETURN s.id AS id", {"id": snapshot_id}):
        raise KeyError(snapshot_id)
    rows = _rows(
        conn,
        "MATCH (:Snapshot {id: $id})-[o:OBSERVED]->(t:Tag) "
        "RETURN t.name AS name, o.value AS value ORDER BY name",
        {"id": snapshot_id},
    )
    return {r["name"]: bool(r["value"]) for r in rows}


_FEEDERS = (
    "MATCH (n)-[f:FEEDS]->(d:{dst} {{id: $id}}) "
    "RETURN labels(n) AS labels, n.name AS name, n.id AS id, n.op AS op, "
    "n.value AS value, n.text AS text, f.pos AS pos ORDER BY pos"
)


def _build_expr(conn: relate.Connection, node: dict, depth: int) -> Expr:
    if depth > MAX_HOPS:
        raise ValueError(f"expression nesting exceeds MAX_HOPS={MAX_HOPS}")
    label = node["labels"][0]
    if label == "Tag":
        return Ref(node["name"])
    if label == "Const":
        return Const(bool(node["value"]))
    if label == "Unresolved":
        return Unresolved(node["text"])
    if label != "Gate":
        raise ValueError(f"unexpected node label in expression: {label}")
    kids = tuple(
        _build_expr(conn, k, depth + 1)
        for k in _rows(conn, _FEEDERS.format(dst="Gate"), {"id": node["id"]})
    )
    op = node["op"]
    if op == "NOT":
        if len(kids) != 1:
            raise ValueError(f"NOT gate {node['id']} has {len(kids)} operands")
        return Not(kids[0])
    return And(kids) if op == "AND" else Or(kids)


def writer_rung(conn: relate.Connection, tag: str) -> Rung | None:
    """The rung writing ``tag`` with its expression rebuilt from FEEDS edges, or None."""
    rows = _rows(
        conn,
        "MATCH (r:Rung)-[:WRITES]->(:Tag {name: $name}) "
        "RETURN r.id AS id, r.routine AS routine, r.target AS target, "
        "r.source AS source, r.line AS line ORDER BY id LIMIT 1",
        {"name": tag.upper()},
    )
    if not rows:
        return None
    r = rows[0]
    roots = _rows(conn, _FEEDERS.format(dst="Rung"), {"id": r["id"]})
    if len(roots) != 1:
        raise ValueError(f"rung {r['id']} has {len(roots)} root expressions (expected 1)")
    expr = _build_expr(conn, roots[0], 0)
    return Rung(
        routine=r["routine"], target=r["target"], expr=expr, source=r["source"], line=r["line"]
    )
