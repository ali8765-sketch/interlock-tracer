"""Evaluate curated synthetic cases; not a measure of real-world accuracy."""
import json
from pathlib import Path
from .graph_store import open_store
from .trace import why

def evaluate(stores, cases_path):
    cases=json.loads(Path(cases_path).read_text(encoding='utf-8'))
    passed=0; failures=[]
    for case in cases:
        c=open_store(stores[case['version']])
        try: v=why(c,case['output'],case['snapshot'])
        finally: c.close()
        ok=(v.status==case['status'] and set(v.root_causes)==set(case['expected_root_causes']))
        if ok: passed+=1
        else: failures.append({'case':case,'actual_status':v.status,'actual_root_causes':sorted(v.root_causes)})
    return {'passed':passed,'total':len(cases),'failures':failures}
