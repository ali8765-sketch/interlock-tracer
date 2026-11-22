"""Read-only MCP stdio server. Stores must already be built."""
import argparse
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from .tools import ToolBox, TOOL_SPECS

def build_server(tb: ToolBox) -> FastMCP:
    server=FastMCP('Interlock Tracer')
    def list_versions(): return tb.list_versions()
    def find_tag(text: str, version: str | None = None): return tb.find_tag(text,version)
    def why_blocked(output: str, snapshot: str, version: str | None = None): return tb.why_blocked(output,snapshot,version)
    def impact(tag: str, version: str | None = None): return tb.impact(tag,version)
    def diff(old_version: str, new_version: str): return tb.diff(old_version,new_version)
    def get_rung(target: str, version: str | None = None): return tb.get_rung(target,version)
    functions={f.__name__:f for f in (list_versions,find_tag,why_blocked,impact,diff,get_rung)}
    for spec in TOOL_SPECS: server.add_tool(functions[spec['name']], name=spec['name'], description=spec['description'])
    return server

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument('--store',action='append',metavar='VERSION=PATH')
    args=parser.parse_args(argv)
    stores={}
    for entry in args.store or ['1.3=data/stores/line3_v1.3','1.4=data/stores/line3_v1.4']:
        if '=' not in entry: parser.error('--store must be VERSION=PATH')
        version,path=entry.split('=',1); stores[version]=Path(path)
    build_server(ToolBox(stores)).run(transport='stdio')
if __name__=='__main__': main()
