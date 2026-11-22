"""Domain model: boolean expression tree, tags, rungs, snapshots and projects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Const:
    value: bool


@dataclass(frozen=True)
class Not:
    child: Expr


@dataclass(frozen=True)
class And:
    children: tuple[Expr, ...]


@dataclass(frozen=True)
class Or:
    children: tuple[Expr, ...]


@dataclass(frozen=True)
class Unresolved:
    """Text the parser could not interpret (e.g. an indirect address); evaluates to unknown."""

    text: str


Expr = Ref | Const | Not | And | Or | Unresolved


@dataclass(frozen=True)
class TagInfo:
    name: str
    kind: str  # input | output | internal | undeclared
    address: str = ""
    device: str = ""
    desc_en: str = ""
    desc_de: str = ""


@dataclass(frozen=True)
class Rung:
    routine: str
    target: str
    expr: Expr
    source: str
    line: int

    @property
    def id(self) -> str:
        return f"{self.routine}/{self.target}"


@dataclass
class Snapshot:
    id: str
    description: str
    values: dict[str, bool]


@dataclass
class Project:
    name: str
    version: str
    tags: dict[str, TagInfo] = field(default_factory=dict)
    rungs: list[Rung] = field(default_factory=list)
    snapshots: dict[str, Snapshot] = field(default_factory=dict)


def refs(expr: Expr) -> set[str]:
    """Names of all tags referenced by Ref nodes in the expression."""
    if isinstance(expr, Ref):
        return {expr.name}
    if isinstance(expr, Not):
        return refs(expr.child)
    if isinstance(expr, (And, Or)):
        out: set[str] = set()
        for child in expr.children:
            out |= refs(child)
        return out
    return set()


def unresolved(expr: Expr) -> list[str]:
    """Texts of all Unresolved atoms in source order."""
    if isinstance(expr, Unresolved):
        return [expr.text]
    if isinstance(expr, Not):
        return unresolved(expr.child)
    if isinstance(expr, (And, Or)):
        out: list[str] = []
        for child in expr.children:
            out.extend(unresolved(child))
        return out
    return []
