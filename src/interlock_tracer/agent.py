"""Optional Claude explanation, grounded in read-only deterministic tools."""
import json, os
from dataclasses import dataclass
from .tools import TOOL_SPECS

@dataclass
class AskResult:
    answer: str
    tool_calls: list[dict]

def ask(question, tb, client=None, model=None, snapshot=None, max_turns=8):
    if client is None:
        if not os.getenv('ANTHROPIC_API_KEY'): raise ValueError('Set ANTHROPIC_API_KEY or use `itrace why`')
        from anthropic import Anthropic
        client=Anthropic()
    model=model or os.getenv('ITRACE_MODEL', 'claude-sonnet-4-6')
    system='Answer only from tool results. Do not compute verdicts yourself. Quote evidence paths verbatim. State INCOMPLETE or NOT_FOUND and missing information explicitly. Do not invent facts. Respond in the user language. This is not a safety system.'
    messages=[{'role':'user','content': question + (f'\nSnapshot: {snapshot}' if snapshot else '')}]
    calls=[]
    for _ in range(max_turns):
        response=client.messages.create(model=model,max_tokens=1500,system=system,tools=TOOL_SPECS,messages=messages)
        blocks=response.content
        text='\n'.join(b.text for b in blocks if b.type=='text')
        toolblocks=[b for b in blocks if b.type=='tool_use']
        if not toolblocks: return AskResult(text,calls)
        messages.append({'role':'assistant','content':[b.model_dump(exclude_none=True) if hasattr(b,'model_dump') else vars(b) for b in blocks]})
        results=[]
        for b in toolblocks:
            permitted={s['name'] for s in TOOL_SPECS}
            try: result=getattr(tb,b.name)(**b.input) if b.name in permitted else {'error':'Unknown tool'}
            except Exception as e: result={'error':str(e)}
            calls.append({'name':b.name,'input':b.input,'result':result})
            results.append({'type':'tool_result','tool_use_id':b.id,'content':json.dumps(result,ensure_ascii=False)})
        messages.append({'role':'user','content':results})
    return AskResult('Tool-call limit reached; no final answer was produced.',calls)
