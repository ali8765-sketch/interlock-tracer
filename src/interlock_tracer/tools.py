"""Bounded read-only tool interface shared by CLI, MCP and Claude."""
from contextlib import contextmanager
from pathlib import Path
from .graph_store import open_store, project_meta, writer_rung
from .trace import why, impact
from .diff import diff_stores
from .search import find_tags
from .report import to_jsonable

def _spec(name, desc, properties, required=()):
    return {'name': name, 'description': desc, 'input_schema': {'type':'object', 'properties':{x:{'type':'string','description':d} for x,d in properties.items()}, 'required':list(required), 'additionalProperties':False}}

TOOL_SPECS = [
 _spec('list_versions','List available PLC project versions.',{}),
 _spec('find_tag','Find tags by English or German description.',{'text':'Search text','version':'Project version'},('text',)),
 _spec('why_blocked','Evaluate output deterministically for a snapshot and return evidence paths.',{'output':'Output tag','snapshot':'Snapshot ID','version':'Project version'},('output','snapshot')),
 _spec('impact','Find potentially affected outputs, not runtime verdicts.',{'tag':'Input tag','version':'Project version'},('tag',)),
 _spec('diff','Compare two project versions.',{'old_version':'Old version','new_version':'New version'},('old_version','new_version')),
 _spec('get_rung','Read the logic writing a tag.',{'target':'Target tag','version':'Project version'},('target',)),
]

def _version_key(v): return tuple(int(x) for x in v.split('.'))

class ToolBox:
    def __init__(self, stores: dict[str, Path]): self.stores = {str(k):Path(v) for k,v in stores.items()}
    @contextmanager
    def _conn(self, version=None):
        if not self.stores: raise ValueError('No stores configured')
        version = version or max(self.stores, key=_version_key)
        if version not in self.stores: raise ValueError(f'Unknown version: {version}')
        c = open_store(self.stores[version])
        try: yield c
        finally: c.close()
    def _safe(self, fn):
        try: return to_jsonable(fn())
        except Exception as e: return {'error': str(e)}
    def list_versions(self):
        def run():
            result=[]
            for v in sorted(self.stores, key=_version_key):
                with self._conn(v) as c: result.append({'version': v, 'project':project_meta(c)[0]})
            return result
        return self._safe(run)
    def find_tag(self, text, version=None):
        def run():
            with self._conn(version) as c: return find_tags(c,text)
        return self._safe(run)
    def why_blocked(self, output, snapshot, version=None):
        def run():
            with self._conn(version) as c: return why(c,output,snapshot)
        return self._safe(run)
    def impact(self, tag, version=None):
        def run():
            with self._conn(version) as c: return impact(c,tag)
        return self._safe(run)
    def diff(self, old_version, new_version):
        def run():
            with self._conn(old_version) as a:
                with self._conn(new_version) as b: return diff_stores(a,b)
        return self._safe(run)
    def get_rung(self, target, version=None):
        def run():
            with self._conn(version) as c:
                r=writer_rung(c,target)
                return {'id':r.id, 'target':r.target, 'source':r.source, 'line':r.line} if r else {'error':f'No writer for {target}'}
        return self._safe(run)
