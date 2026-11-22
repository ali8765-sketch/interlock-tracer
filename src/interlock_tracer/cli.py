"""Offline command-line interface for Interlock Tracer."""
import argparse, json, sys
from pathlib import Path
from .loader import load_project
from .graph_store import build_store, open_store, all_tags
from .trace import why, impact
from .search import find_tags
from .diff import diff_stores
from .report import format_verdict, format_impact, format_hits, format_diff, to_jsonable
from .viewer import render_verdict_html

DEFAULT = 'data/stores/line3_v1.4'
def _desc(c):
    return {n: f'{t.desc_en} / {t.desc_de}' for n,t in all_tags(c).items()}
def _emit(value, text, as_json):
    print(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2) if as_json else text)
def _store_option(p): p.add_argument('--store', default=DEFAULT); p.add_argument('--json', action='store_true')

def parser():
    p=argparse.ArgumentParser(prog='itrace', description='Explain PLC interlocks using an offline Relate graph.')
    sub=p.add_subparsers(dest='command', required=True)
    x=sub.add_parser('build'); x.add_argument('project_dir'); x.add_argument('--store')
    x=sub.add_parser('why'); x.add_argument('output'); x.add_argument('--snapshot',required=True); _store_option(x); x.add_argument('--html'); x.add_argument('--record')
    x=sub.add_parser('impact'); x.add_argument('tag'); _store_option(x)
    x=sub.add_parser('find'); x.add_argument('text'); _store_option(x)
    x=sub.add_parser('diff'); x.add_argument('--old',required=True); x.add_argument('--new',required=True); x.add_argument('--json',action='store_true')
    x=sub.add_parser('ask'); x.add_argument('question'); x.add_argument('--snapshot'); x.add_argument('--store',default=DEFAULT); x.add_argument('--version',default='1.4')
    sub.add_parser('demo')
    x=sub.add_parser('eval'); x.add_argument('--cases',default='eval/questions.json')
    return p

def demo():
    stores={}
    for version in ('1.3','1.4'):
        project=load_project(Path('examples/line3')/('v'+version))
        store=Path('data/stores')/f'line3_v{version}'
        build_store(project,store); stores[version]=store
    a,b=open_store(stores['1.3']),open_store(stores['1.4'])
    try:
        snap='s1_m101_wont_start'
        print('\n=== Find: Schutztür 2 ===\n'+format_hits(find_tags(a,'Schutztür 2')))
        v=why(a,'M101_RUN',snap); descriptions=_desc(a)
        print('\n=== Why M101, v1.3 ===\n'+format_verdict(v,descriptions))
        print('\n=== Impact: guard door 2 ===\n'+format_impact('GUARD_DOOR_2_CLOSED',impact(a,'GUARD_DOOR_2_CLOSED')))
        print('\n=== Version changes ===\n'+format_diff(diff_stores(a,b)))
        print('\n=== Why M101, v1.4 ===\n'+format_verdict(why(b,'M101_RUN',snap),_desc(b)))
        print('\n=== Unresolved logic ===\n'+format_verdict(why(b,'Y301_DIVERT',snap),_desc(b)))
        target=Path('data/why_M101_RUN.html'); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(render_verdict_html(v,descriptions),encoding='utf-8')
        print(f'\nOffline evidence viewer: {target}')
    finally: a.close(); b.close()
    return 0

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='demo': return demo()
        if args.command=='eval':
            from .evaluate import evaluate
            result=evaluate({'1.3':Path('data/stores/line3_v1.3'),'1.4':Path('data/stores/line3_v1.4')},args.cases)
            print(json.dumps(result,indent=2)); return 0 if not result['failures'] else 1
        if args.command=='build':
            project=load_project(Path(args.project_dir)); store=Path(args.store or f'data/stores/{project.name}_v{project.version}')
            build_store(project,store); print(f'Built {project.name} v{project.version}: {store}'); return 0
        if args.command=='ask':
            import os
            if not os.environ.get('ANTHROPIC_API_KEY'): print('Set ANTHROPIC_API_KEY or use `itrace why`.',file=sys.stderr); return 2
            from .agent import ask
            from .tools import ToolBox
            print(ask(args.question,ToolBox({args.version:Path(args.store)}),snapshot=args.snapshot).answer); return 0
        if args.command=='diff':
            a,b=open_store(Path(args.old)),open_store(Path(args.new))
            try: d=diff_stores(a,b); _emit(d,format_diff(d),args.json)
            finally: a.close(); b.close()
            return 0
        c=open_store(Path(args.store))
        try:
            if args.command=='why':
                v=why(c,args.output,args.snapshot); desc=_desc(c); _emit(v,format_verdict(v,desc),args.json)
                if args.html: Path(args.html).write_text(render_verdict_html(v,desc),encoding='utf-8')
                if args.record:
                    from .traces import record_verdict
                    from .graph_store import project_meta
                    if Path(args.record).resolve() == Path(args.store).resolve(): raise ValueError('Trace store must be separate from the project graph')
                    record_verdict(Path(args.record),f'Why {args.output}?',v,project_meta(c)[1])
                return 2 if v.status=='NOT_FOUND' else 0
            if args.command=='find':
                hits=find_tags(c,args.text); _emit(hits,format_hits(hits),args.json)
            if args.command=='impact':
                hits=impact(c,args.tag); _emit(hits,format_impact(args.tag,hits),args.json)
        finally: c.close()
        return 0
    except (FileNotFoundError,KeyError,ValueError) as e:
        print(f'Error: {e}',file=sys.stderr); return 2
    except Exception as e:
        print(f'Error: {e}',file=sys.stderr); return 1

if __name__ == '__main__': sys.exit(main())
