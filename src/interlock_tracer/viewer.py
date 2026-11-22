"""Create a self-contained, offline Cytoscape evidence viewer."""
import html, json
from pathlib import Path
from .report import format_verdict

def render_verdict_html(v, descriptions):
    nodes, edges = {}, {}
    for path in v.paths:
        for name in path:
            nodes[name] = {'data':{'id':name,'label':name,'kind':'root' if name in v.root_causes else 'output' if name == v.output else 'rung' if '/' in name else 'tag'}}
        for a,b in zip(path,path[1:]): edges[(a,b)] = {'data':{'id':a+'→'+b,'source':a,'target':b}}
    data=json.dumps(list(nodes.values())+list(edges.values()), ensure_ascii=False).replace('<','\\u003c')
    js=(Path(__file__).parent/'vendor'/'cytoscape.min.js').read_text(encoding='utf-8')
    summary=html.escape(format_verdict(v,descriptions))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Interlock Tracer — {html.escape(v.output)}</title><style>body{{font:15px system-ui;margin:0;background:#101d2e;color:#e7f1fa}}header{{padding:18px 24px;background:#152a40}}main{{display:flex;min-height:80vh}}#cy{{flex:2;background:#edf3f8;min-height:600px}}aside{{flex:1;padding:20px;overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}@media(max-width:800px){{main{{display:block}}#cy{{min-height:450px}}}}</style></head><body><header><h1>Interlock Tracer</h1><p>Deterministic evidence graph · synthetic example · not a safety system</p></header><main><div id="cy"></div><aside><h2>{html.escape(v.status)}</h2><pre>{summary}</pre></aside></main><script>{js}</script><script>cytoscape({{container:document.getElementById('cy'),elements:{data},style:[{{selector:'node',style:{{'label':'data(label)','font-size':10,'text-wrap':'wrap','text-max-width':110,'background-color':'#6b88a4','color':'#132538','text-valign':'bottom','text-margin-y':6}}}},{{selector:'node[kind="root"]',style:{{'background-color':'#d64e4e'}}}},{{selector:'node[kind="output"]',style:{{'background-color':'#246ac4'}}}},{{selector:'node[kind="rung"]',style:{{'shape':'round-rectangle','width':90,'height':35}}}},{{selector:'edge',style:{{'width':2,'line-color':'#7991a5','target-arrow-color':'#7991a5','target-arrow-shape':'triangle','curve-style':'bezier'}}}}],layout:{{name:'breadthfirst',directed:true,spacingFactor:1.5,transform:function(node,pos){{return {{x:pos.y,y:pos.x}}}}}}}});</script></body></html>'''
