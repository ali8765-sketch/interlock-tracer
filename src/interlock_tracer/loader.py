"""Load a project directory (project.json, iolist.csv, logic.st, snapshots/*.json) into a Project."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .model import Project, Snapshot, TagInfo, refs
from .st_parser import parse_st

_KINDS = {"input", "output", "internal"}
_TRUE = {"true", "1"}
_FALSE = {"false", "0"}


def coerce_bool(tag: str, value: object) -> bool:
    """Accept True/False, int 1/0 and "true"/"false"/"1"/"0" (any case); reject everything else."""
    if isinstance(value, bool):  # must precede int: bool is an int subclass
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
    elif isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise ValueError(f"snapshot value for tag {tag!r} is not a boolean: {value!r}")


def _load_tags(path: Path) -> dict[str, TagInfo]:
    tags: dict[str, TagInfo] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("tag") or "").strip().upper()
            if not name:
                continue
            kind = (row.get("kind") or "").strip().lower()
            if kind not in _KINDS:
                raise ValueError(f"{path.name}: tag {name!r} has invalid kind {kind!r}")
            if name in tags:
                raise ValueError(f"{path.name}: duplicate tag {name!r}")
            tags[name] = TagInfo(
                name=name,
                kind=kind,
                address=(row.get("address") or "").strip(),
                device=(row.get("device") or "").strip(),
                desc_en=(row.get("desc_en") or "").strip(),
                desc_de=(row.get("desc_de") or "").strip(),
            )
    return tags


def _load_snapshot(path: Path) -> Snapshot:
    data = json.loads(path.read_text(encoding="utf-8"))
    values: dict[str, bool] = {}
    for key, raw in (data.get("values") or {}).items():
        name = str(key).strip().upper()
        values[name] = coerce_bool(name, raw)
    return Snapshot(
        id=str(data.get("id") or path.stem),
        description=str(data.get("description") or ""),
        values=values,
    )


def load_project(path: Path) -> Project:
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"project directory not found: {root}")
    meta = json.loads((root / "project.json").read_text(encoding="utf-8"))
    tags = _load_tags(root / "iolist.csv")
    rungs = parse_st((root / "logic.st").read_text(encoding="utf-8"))

    for rung in rungs:
        for name in sorted({rung.target} | refs(rung.expr)):
            if name not in tags:
                tags[name] = TagInfo(name=name, kind="undeclared")

    snapshots: dict[str, Snapshot] = {}
    snap_dir = root / "snapshots"
    if snap_dir.is_dir():
        for file in sorted(snap_dir.glob("*.json")):
            snap = _load_snapshot(file)
            snapshots[snap.id] = snap

    return Project(
        name=str(meta["name"]),
        version=str(meta["version"]),
        tags=tags,
        rungs=rungs,
        snapshots=snapshots,
    )
