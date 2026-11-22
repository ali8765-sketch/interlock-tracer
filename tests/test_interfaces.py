import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from interlock_tracer.cli import main
from interlock_tracer.tools import ToolBox, TOOL_SPECS
from interlock_tracer.agent import ask
from interlock_tracer.mcp_server import build_server

def test_toolbox(store13, store14):
    tb=ToolBox({'1.3':store13,'1.4':store14})
    assert tb.why_blocked('m101_run','s1_m101_wont_start')['status']=='BLOCKED'
    assert 'AIR_PRESSURE_OK' in tb.why_blocked('m101_run','s1_m101_wont_start')['root_causes']
    assert 'error' in tb.why_blocked('M101_RUN','missing')
    assert tb.get_rung('M101_RUN','1.3')['id']=='Conveyors/M101_RUN'

def test_cli_html_json(store13, tmp_path, capsys):
    out=tmp_path/'viewer.html'
    assert main(['why','m101_run','--snapshot','s1_m101_wont_start','--store',str(store13),'--html',str(out),'--json'])==0
    assert json.loads(capsys.readouterr().out)['status']=='BLOCKED'
    text=out.read_text(); assert 'Füllstandsschalter' in text and 'LS204_BIN_FULL' in text and 'src="http' not in text

def test_mcp_memory(store13):
    from mcp.shared.memory import create_connected_server_and_client_session
    server=build_server(ToolBox({'1.3':store13}))
    async def run():
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            result=await session.list_tools()
            assert {x.name for x in result.tools} == {s['name'] for s in TOOL_SPECS}
            response=await session.call_tool('why_blocked',{'output':'M101_RUN','snapshot':'s1_m101_wont_start','version':'1.3'})
            assert 'BLOCKED' in str(response)
    asyncio.run(run())

def test_agent_uses_tool(store13):
    class Tool:
        type='tool_use'; name='why_blocked'; id='tool1'; input={'output':'M101_RUN','snapshot':'s1_m101_wont_start'}
    class Text:
        type='text'; text='Blocked, based on the tool result.'
    class Messages:
        def __init__(self): self.calls=[]
        def create(self,**kw):
            self.calls.append(kw)
            return SimpleNamespace(content=[Tool()] if len(self.calls)==1 else [Text()])
    messages=Messages(); result=ask('Why?',ToolBox({'1.3':store13}),client=SimpleNamespace(messages=messages))
    assert result.tool_calls[0]['result']['status']=='BLOCKED'
    assert 'BLOCKED' in messages.calls[1]['messages'][-1]['content'][0]['content']

def test_record_separate_store(store13,tmp_path):
    import relate
    from interlock_tracer.graph_store import open_store
    from interlock_tracer.trace import why
    from interlock_tracer.traces import record_verdict
    c=open_store(store13)
    try: verdict=why(c,'M101_RUN','s1_m101_wont_start')
    finally: c.close()
    path=tmp_path/'trace'
    ident=record_verdict(path,'Why?',verdict,'1.3')
    c=relate.connect(str(path),read_only=True)
    try:
        row=next(iter(c.execute('MATCH (v:Verdict {id:$id})-[:USED_EVIDENCE]->(e:Evidence) RETURN count(e) AS count',{'id':ident}))).data()
        assert row['count']==len(verdict.paths)
    finally: c.close()
