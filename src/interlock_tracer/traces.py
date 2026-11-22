"""Record evidence in a separate append-only Relate store."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
import relate

def record_verdict(trace_store: Path, question: str, verdict, version: str = '') -> str:
    path=Path(trace_store); path.parent.mkdir(parents=True,exist_ok=True)
    ident=uuid4().hex
    c=relate.connect(str(path),read_only=False)
    try:
        c.autocommit=False
        c.execute('CREATE (:Question {id:$id, text:$text, ts:$ts})', {'id':ident,'text':question,'ts':datetime.now(timezone.utc).isoformat()})
        c.execute('CREATE (:Verdict {id:$id, status:$status, output:$output, snapshot:$snapshot, version:$version})', {'id':ident,'status':verdict.status,'output':verdict.output,'snapshot':verdict.snapshot,'version':version})
        c.execute('MATCH (q:Question {id:$id}), (v:Verdict {id:$id}) CREATE (q)-[:ANSWERED_WITH]->(v)', {'id':ident})
        if verdict.paths:
            c.execute('UNWIND $rows AS row MATCH (v:Verdict {id:$id}) CREATE (e:Evidence {path:row.path}) CREATE (v)-[:USED_EVIDENCE {rank:row.rank}]->(e)', {'id':ident,'rows':[{'rank':i,'path':json.dumps(p,ensure_ascii=False)} for i,p in enumerate(verdict.paths)]})
        c.commit()
    except BaseException:
        c.rollback(); raise
    finally: c.close()
    return ident
