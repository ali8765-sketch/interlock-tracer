"""Sanitised Relate full-text tag search."""
from dataclasses import dataclass
import re
from .graph_store import _rows

@dataclass
class TagHit:
    name: str
    score: float
    desc_en: str
    desc_de: str

def find_tags(conn, text: str, limit: int = 5) -> list[TagHit]:
    tokens = re.findall(r'[^\W]+', text, flags=re.UNICODE)
    if not tokens or limit <= 0:
        return []
    query = ' OR '.join(tokens)
    rows = _rows(conn, "CALL db.index.fulltext.queryNodes('tag_text', $q) YIELD node, score RETURN node.name AS name, score, node.desc_en AS desc_en, node.desc_de AS desc_de ORDER BY score DESC LIMIT $limit", {'q': query, 'limit': min(limit, 100)})
    return [TagHit(r['name'], r['score'], r['desc_en'] or '', r['desc_de'] or '') for r in rows]
