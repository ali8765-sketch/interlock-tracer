"""Compare two read-only Relate project graphs."""
from dataclasses import dataclass
from .graph_store import all_rungs, all_tags, project_meta
from .trace import upstream_inputs

@dataclass
class VersionDiff:
    old_version: str
    new_version: str
    changed_rungs: list[str]
    added_rungs: list[str]
    removed_rungs: list[str]
    new_tags: list[str]
    removed_tags: list[str]
    new_dependencies: dict[str, set[str]]
    lost_dependencies: dict[str, set[str]]

def diff_stores(old, new) -> VersionDiff:
    a, b = all_rungs(old), all_rungs(new)
    at, bt = all_tags(old), all_tags(new)
    additions, losses = {}, {}
    outputs = sorted(k for k in at.keys() & bt.keys() if at[k].kind == bt[k].kind == 'output')
    for output in outputs:
        x, y = upstream_inputs(old, output), upstream_inputs(new, output)
        if y - x: additions[output] = y - x
        if x - y: losses[output] = x - y
    return VersionDiff(project_meta(old)[1], project_meta(new)[1],
        sorted(k for k in a.keys() & b.keys() if ' '.join(a[k].split()) != ' '.join(b[k].split())),
        sorted(b.keys()-a.keys()), sorted(a.keys()-b.keys()), sorted(bt.keys()-at.keys()), sorted(at.keys()-bt.keys()), additions, losses)
