"""Human and machine-readable reports."""
from dataclasses import asdict, is_dataclass

def to_jsonable(obj):
    if is_dataclass(obj): return to_jsonable(asdict(obj))
    if isinstance(obj, dict): return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, set): return sorted(to_jsonable(x) for x in obj)
    if isinstance(obj, (list, tuple)): return [to_jsonable(x) for x in obj]
    return obj

def format_verdict(v, descriptions):
    lines = [f'{v.output} — {v.status} (snapshot: {v.snapshot})']
    for path in v.paths:
        lines.append(' → '.join([f'{path[0]}={str(v.root_causes[path[0]]).upper()}'] + path[1:]))
    if v.root_causes:
        lines.append('Contributing inputs:')
        lines.extend(f'  {tag}={str(val).upper()} — {descriptions.get(tag, "")}' for tag, val in v.root_causes.items())
        lines.append('Explanation tree:')
        def tree(node, depth=0):
            lines.append('  ' * depth + f'{node.kind}: {node.label} = {node.value}')
            for child in node.children: tree(child, depth+1)
        if v.explanation: tree(v.explanation)
    if v.missing: lines.append('Missing values: ' + ', '.join(v.missing))
    if v.unresolved: lines.append('Unresolved logic: ' + ', '.join(v.unresolved))
    return '\n'.join(lines)

def format_impact(tag, hits):
    return f'Potential downstream outputs for {tag.upper()}:' + ('\n' + '\n'.join(' → '.join(x.path) for x in hits) if hits else '\n  None found')

def format_diff(d):
    return f'Version {d.old_version} → {d.new_version}\nChanged rungs: {", ".join(d.changed_rungs) or "none"}\nNew tags: {", ".join(d.new_tags) or "none"}\nAdded dependencies:\n' + '\n'.join(f'  {k}: {", ".join(sorted(v))}' for k,v in d.new_dependencies.items()) + '\nLost dependencies:\n' + '\n'.join(f'  {k}: {", ".join(sorted(v))}' for k,v in d.lost_dependencies.items())

def format_hits(hits):
    return '\n'.join(f'{h.name} — {h.desc_en} / {h.desc_de} ({h.score:.2f})' for h in hits) or 'No matches.'
