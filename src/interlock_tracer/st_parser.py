"""Parser for the boolean Structured Text subset.

Grammar (identifiers are case-insensitive and upper-cased):
    or   ::= and (OR and)*
    and  ::= not (AND not)*
    not  ::= NOT not | atom
    atom ::= IDENT | TRUE | FALSE | '(' or ')' | <anything else> -> Unresolved
"""

from __future__ import annotations

import re

from .model import And, Const, Expr, Not, Or, Ref, Rung, Unresolved

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OPERATORS = {"AND", "OR", "NOT"}
_KEYWORDS = _OPERATORS | {"TRUE", "FALSE"}
_PROGRAM = re.compile(r"PROGRAM\b\s*", re.IGNORECASE)
_END_PROGRAM = re.compile(r"END_PROGRAM\b\s*;?", re.IGNORECASE)


class STParseError(ValueError):
    def __init__(self, message: str, line: int = 0):
        super().__init__(f"line {line}: {message}" if line else message)
        self.message = message
        self.line = line


# ---------------------------------------------------------------- expressions

def _tokenize(text: str) -> list[tuple[str, str]]:
    """Return (kind, value) tokens; kind is LP, RP, KW, IDENT or UNRES."""
    tokens: list[tuple[str, str]] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append(("LP", ch))
            i += 1
        elif ch == ")":
            tokens.append(("RP", ch))
            i += 1
        else:
            m = _IDENT.match(text, i)
            if m:
                end = m.end()
                word = m.group()
                glued = end < n and not text[end].isspace() and text[end] != ")"
                if glued and text[end] == "(" and word.upper() in _KEYWORDS:
                    glued = False  # e.g. NOT(A) or AND(B)
                if not glued and word.upper() not in _KEYWORDS:
                    # "X > 5" or "A B": junk after whitespace makes the whole run Unresolved.
                    glued = not _run_ends_at(text, _skip_space(text, end))
                if not glued:
                    if word.upper() in _KEYWORDS:
                        tokens.append(("KW", word.upper()))
                    else:
                        tokens.append(("IDENT", word.upper()))
                    i = end
                    continue
            end = _scan_unresolved(text, i)
            tokens.append(("UNRES", text[i:end].rstrip()))
            i = end
    return tokens


def _skip_space(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _run_ends_at(text: str, j: int) -> bool:
    """True if an unresolved run stops before offset ``j`` (end, ')' or operator keyword)."""
    n = len(text)
    if j >= n or text[j] == ")":
        return True
    m = _IDENT.match(text, j)
    return bool(
        m and m.group().upper() in _OPERATORS
        and (m.end() >= n or text[m.end()].isspace() or text[m.end()] == "(")
    )


def _scan_unresolved(text: str, start: int) -> int:
    """End offset of the unresolved run that begins at ``start``.

    The run stops at an unnested ')' , at whitespace followed by an operator
    keyword, or at the end of the text. Brackets and parentheses opened inside
    the run are balanced before stopping.
    """
    n = len(text)
    depth = 0
    i = start
    while i < n:
        ch = text[i]
        if ch in "[(":
            depth += 1
        elif ch in "])":
            if depth == 0:
                break
            depth -= 1
        elif ch.isspace() and depth == 0:
            j = _skip_space(text, i)
            if _run_ends_at(text, j):
                break
            i = j
            continue
        i += 1
    if depth:
        raise STParseError(f"unbalanced brackets in {text[start:].strip()!r}")
    return i


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def at_kw(self, word: str) -> bool:
        tok = self.peek()
        return tok is not None and tok == ("KW", word)

    def parse_or(self) -> Expr:
        items = [self.parse_and()]
        while self.at_kw("OR"):
            self.take()
            items.append(self.parse_and())
        return items[0] if len(items) == 1 else Or(tuple(items))

    def parse_and(self) -> Expr:
        items = [self.parse_not()]
        while self.at_kw("AND"):
            self.take()
            items.append(self.parse_not())
        return items[0] if len(items) == 1 else And(tuple(items))

    def parse_not(self) -> Expr:
        if self.at_kw("NOT"):
            self.take()
            return Not(self.parse_not())
        return self.parse_atom()

    def parse_atom(self) -> Expr:
        tok = self.peek()
        if tok is None:
            raise STParseError("unexpected end of expression")
        kind, value = self.take()
        if kind == "IDENT":
            return Ref(value)
        if kind == "UNRES":
            return Unresolved(value)
        if kind == "LP":
            inner = self.parse_or()
            if self.peek() != ("RP", ")"):
                raise STParseError("missing ')'")
            self.take()
            return inner
        if kind == "KW" and value in ("TRUE", "FALSE"):
            return Const(value == "TRUE")
        raise STParseError(f"unexpected {value!r}")


def parse_expr(text: str) -> Expr:
    parser = _Parser(_tokenize(text))
    expr = parser.parse_or()
    if parser.peek() is not None:
        raise STParseError(f"unexpected {parser.peek()[1]!r}")
    return expr


# -------------------------------------------------------------------- programs

def _blank_comments(src: str) -> str:
    """Replace comments with spaces, keeping newlines so offsets and lines survive."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif src.startswith("(*", i):
            j = src.find("*)", i + 2)
            if j < 0:
                raise STParseError("unterminated comment", src.count("\n", 0, i) + 1)
            out.append("".join("\n" if c == "\n" else " " for c in src[i:j + 2]))
            i = j + 2
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def parse_st(text: str) -> list[Rung]:
    clean = _blank_comments(text)
    n = len(clean)
    rungs: list[Rung] = []
    writers: set[str] = set()
    routine: str | None = None
    pos = 0

    def line_at(offset: int) -> int:
        return clean.count("\n", 0, offset) + 1

    while True:
        while pos < n and clean[pos].isspace():
            pos += 1
        if pos >= n:
            break
        m = _PROGRAM.match(clean, pos)
        if m:
            if routine is not None:
                raise STParseError("PROGRAM inside PROGRAM", line_at(pos))
            name = _IDENT.match(clean, m.end())
            if not name:
                raise STParseError("PROGRAM needs a name", line_at(pos))
            routine = name.group()
            pos = name.end()
            continue
        m = _END_PROGRAM.match(clean, pos)
        if m:
            if routine is None:
                raise STParseError("END_PROGRAM without PROGRAM", line_at(pos))
            routine = None
            pos = m.end()
            continue

        semi = clean.find(";", pos)
        if semi < 0:
            raise STParseError("statement is missing ';'", line_at(pos))
        stmt = clean[pos:semi]
        if routine is None:
            raise STParseError("statement outside PROGRAM", line_at(pos))
        target_text, sep, expr_text = stmt.partition(":=")
        target_m = _IDENT.fullmatch(target_text.strip())
        if not sep or not target_m:
            raise STParseError("expected 'TARGET := expression;'", line_at(pos))
        target = target_m.group().upper()
        line = line_at(pos)
        if target in writers:
            raise STParseError(f"tag {target} has more than one writer", line)
        try:
            if not expr_text.strip():
                raise STParseError("empty expression")
            expr = parse_expr(expr_text)
        except STParseError as exc:
            raise STParseError(exc.message, line) from None
        writers.add(target)
        rungs.append(Rung(routine, target, expr, " ".join(clean[pos:semi + 1].split()), line))
        pos = semi + 1

    if routine is not None:
        raise STParseError(f"PROGRAM {routine} is missing END_PROGRAM", line_at(n))
    return rungs
