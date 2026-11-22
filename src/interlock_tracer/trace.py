"""`why`: deterministic verdict, explanation tree and causal paths for one output + snapshot.

Semantics (spec "Verdict semantics"):

* A tag's value is the Kleene (3-valued) evaluation of its writer rung, recursively.
* Leaves are tags without a writer, or a tag already on the evaluation stack (seal-in / cycle);
  a leaf takes its snapshot value. A missing snapshot value or an ``Unresolved`` atom is unknown.
* Explanation per De Morgan: a gate's contributing operands are those whose value equals the
  gate's value (for NOT: the operand, whose value is the negation). ``all_of`` for (AND, false)
  and (OR, true) -- every listed operand must change; ``any_of`` for (OR, false) and (AND, true)
  -- changing any one listed operand flips the gate. Single-operand nodes collapse.
* Paths run leaf tag -> rung id -> tag -> ... -> output rung id -> output; gates never appear.

Memoisation: a tag's value can only depend on the evaluation stack through stack members that sit
in the same strongly connected component (they are ancestors *and* reachable). Results are cached
under ``(tag, stack ∩ scc(tag))``, which is exact; for acyclic logic that is just the tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import relate

from .graph_store import MAX_HOPS, snapshot_values, writer_rung
from .model import And, Const, Expr, Not, Or, Ref, Rung, Unresolved, refs

Status = Literal["RUNNING", "BLOCKED", "INCOMPLETE", "NOT_FOUND"]
Kind = Literal["leaf", "all_of", "any_of"]


@dataclass
class Explanation:
    kind: Kind
    label: str
    value: bool | None
    children: list[Explanation] = field(default_factory=list)


@dataclass
class Verdict:
    output: str
    snapshot: str
    status: Status
    value: bool | None
    explanation: Explanation | None
    paths: list[list[str]]
    root_causes: dict[str, bool]
    missing: list[str]
    unresolved: list[str]


@dataclass(frozen=True)
class _Res:
    """Evaluation result of a sub-expression, aggregated over its *contributing* leaves only."""

    value: bool | None
    expl: Explanation
    gate: bool  # expl is a gate node (label AND/OR) rather than a tag or leaf node
    paths: frozenset[tuple[str, ...]]  # leaf -> ... -> (enclosing tag excluded)
    causes: tuple[tuple[str, bool], ...]
    missing: frozenset[str]
    unresolved: frozenset[str]


_NONE: frozenset = frozenset()


def _kind(op: str, value: bool | None) -> Kind:
    if value is False:
        return "all_of" if op == "AND" else "any_of"
    if value is True:
        return "all_of" if op == "OR" else "any_of"
    # unknown: every unknown operand of an AND must resolve True; any one of an OR suffices
    return "all_of" if op == "AND" else "any_of"


def _kleene(op: str, values: list[bool | None]) -> bool | None:
    dominant = op == "OR"  # OR: any True wins; AND: any False wins
    if dominant in values:
        return dominant
    if None in values:
        return None
    return not dominant


def _merge(results: list[_Res]) -> tuple[frozenset, tuple, frozenset, frozenset]:
    paths: set = set()
    causes: dict[str, bool] = {}
    missing: set = set()
    unres: set = set()
    for r in results:
        paths |= r.paths
        causes.update(r.causes)
        missing |= r.missing
        unres |= r.unresolved
    return frozenset(paths), tuple(sorted(causes.items())), frozenset(missing), frozenset(unres)


def _load_cone(conn: relate.Connection, output: str) -> dict[str, Rung]:
    """Writer rungs of every written tag in the upstream cone of ``output`` (one query per tag)."""
    rungs: dict[str, Rung] = {}
    seen: set[str] = set()
    todo = [output]
    while todo:
        tag = todo.pop()
        if tag in seen:
            continue
        seen.add(tag)
        rung = writer_rung(conn, tag)
        if rung is not None:
            rungs[tag] = rung
            todo.extend(sorted(refs(rung.expr) - seen))
    return rungs


def _sccs(rungs: dict[str, Rung]) -> dict[str, frozenset[str]]:
    """Strongly connected components (Tarjan, iterative) of the written-tag dependency graph."""
    graph = {t: sorted(n for n in refs(r.expr) if n in rungs) for t, r in rungs.items()}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: dict[str, frozenset[str]] = {}
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(graph[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph[nxt])))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = set()
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    comp.add(member)
                    if member == node:
                        break
                frozen = frozenset(comp)
                for member in comp:
                    out[member] = frozen
    return out


class _Evaluator:
    def __init__(self, rungs: dict[str, Rung], values: dict[str, bool]) -> None:
        self.rungs = rungs
        self.values = values
        self.scc = _sccs(rungs)
        self.memo: dict[tuple[str, frozenset[str]], _Res] = {}

    # -- tags ---------------------------------------------------------------------------------

    def leaf(self, tag: str) -> _Res:
        value = self.values.get(tag)
        expl = Explanation("leaf", tag, value, [])
        if value is None:
            return _Res(None, expl, False, _NONE, (), frozenset({tag}), _NONE)
        return _Res(value, expl, False, frozenset({(tag,)}), ((tag, value),), _NONE, _NONE)

    def tag(self, tag: str, stack: tuple[str, ...]) -> _Res:
        if tag in stack or tag not in self.rungs:
            return self.leaf(tag)
        if len(stack) >= MAX_HOPS:
            raise ValueError(f"tag dependency chain exceeds MAX_HOPS={MAX_HOPS} at {tag}")
        key = (tag, frozenset(stack) & self.scc[tag])
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        rung = self.rungs[tag]
        body = self.expr(rung.expr, stack + (tag,))
        if body.gate:
            kind, children = body.expl.kind, body.expl.children
        else:
            kind, children = "all_of", [body.expl]
        res = _Res(
            body.value,
            Explanation(kind, tag, body.value, children),
            False,
            frozenset(p + (rung.id, tag) for p in body.paths),
            body.causes,
            body.missing,
            body.unresolved,
        )
        self.memo[key] = res
        return res

    # -- expressions --------------------------------------------------------------------------

    def expr(self, e: Expr, stack: tuple[str, ...]) -> _Res:
        if isinstance(e, Ref):
            return self.tag(e.name, stack)
        if isinstance(e, Const):
            return _Res(e.value, Explanation("leaf", "TRUE" if e.value else "FALSE", e.value, []),
                        False, _NONE, (), _NONE, _NONE)
        if isinstance(e, Unresolved):
            return _Res(None, Explanation("leaf", e.text, None, []), False, _NONE, (), _NONE,
                        frozenset({e.text}))
        if isinstance(e, Not):
            # transparent: the operand (value = negation) is the single contributor
            child = self.expr(e.child, stack)
            value = None if child.value is None else not child.value
            return _Res(value, child.expl, child.gate, child.paths, child.causes, child.missing,
                        child.unresolved)
        if isinstance(e, (And, Or)):
            op = "AND" if isinstance(e, And) else "OR"
            kids = [self.expr(c, stack) for c in e.children]
            value = _kleene(op, [k.value for k in kids])
            contrib = [k for k in kids if k.value is value]  # bool/None singletons
            if len(contrib) == 1:
                return contrib[0]
            paths, causes, missing, unres = _merge(contrib)
            expl = Explanation(_kind(op, value), op, value, [k.expl for k in contrib])
            return _Res(value, expl, True, paths, causes, missing, unres)
        raise TypeError(f"unsupported expression node: {e!r}")  # pragma: no cover


def _status(value: bool | None) -> Status:
    return {True: "RUNNING", False: "BLOCKED", None: "INCOMPLETE"}[value]


def why(conn: relate.Connection, output: str, snapshot_id: str) -> Verdict:
    """Explain the value of ``output`` under snapshot ``snapshot_id``.

    Raises ``KeyError`` for an unknown snapshot. An unknown tag or a tag without a writer rung
    (an input) yields status ``NOT_FOUND``. ``root_causes`` / ``paths`` are filled only for
    BLOCKED and cover exactly the leaves that force the output false; ``missing`` / ``unresolved``
    list exactly the unknowns that make the result unknown (empty when a known value decides the
    verdict). The explanation tree is returned for every evaluated status.
    """
    output = output.strip().upper()
    values = snapshot_values(conn, snapshot_id)
    rungs = _load_cone(conn, output)
    if output not in rungs:
        return Verdict(output, snapshot_id, "NOT_FOUND", None, None, [], {}, [], [])
    res = _Evaluator(rungs, values).tag(output, ())
    blocked = res.value is False  # paths / root causes prove a block; RUNNING has none
    paths = [list(p) for p in sorted(res.paths, key=lambda p: (len(p), p))] if blocked else []
    return Verdict(
        output=output,
        snapshot=snapshot_id,
        status=_status(res.value),
        value=res.value,
        explanation=res.expl,
        paths=paths,
        root_causes=dict(sorted(res.causes)) if blocked else {},
        missing=sorted(res.missing),
        unresolved=sorted(res.unresolved),
    )

@dataclass
class ImpactHit:
    output: str
    path: list[str]


def _shortest(conn, start: str, end: str) -> list[str]:
    from .graph_store import _rows
    rows = _rows(conn, f"MATCH p = SHORTEST 1 (a:Tag {{name: $a}})-[:FEEDS|WRITES]->{{1,{MAX_HOPS}}}(o:Tag {{name: $o}}) RETURN nodes(p) AS n", {"a": start, "o": end})
    if not rows:
        return []
    return [n.get('name', n.get('id')) for n in rows[0]['n'] if 'name' in n or 'target' in n]


def impact(conn, tag: str) -> list[ImpactHit]:
    from .graph_store import all_tags
    tag = tag.strip().upper()
    return [ImpactHit(name, path) for name, info in all_tags(conn).items()
            if info.kind == 'output' and (path := _shortest(conn, tag, name))]


def upstream_inputs(conn, output: str) -> set[str]:
    from .graph_store import all_tags, writer_rung
    output = output.strip().upper()
    return {name for name in all_tags(conn) if writer_rung(conn, name) is None
            and _shortest(conn, name, output)}
