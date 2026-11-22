from interlock_tracer.st_parser import parse_expr, parse_st, STParseError
from interlock_tracer.model import Ref, Not, And, Or, Const, Unresolved, refs, unresolved
import pytest

def test_precedence_and_flattening():
    assert parse_expr("A AND B AND NOT C OR D") == Or((And((Ref("A"), Ref("B"), Not(Ref("C")))), Ref("D")))

def test_parens_and_case_insensitive():
    assert parse_expr("(start_pb or M101_Run) and not Stop_PB") == And((Or((Ref("START_PB"), Ref("M101_RUN"))), Not(Ref("STOP_PB"))))

def test_constants():
    assert parse_expr("TRUE AND false") == And((Const(True), Const(False)))

def test_indirect_address_is_unresolved():
    e = parse_expr("DIVERT_REQ AND VALVE_ENABLE[STATION_IDX]")
    assert e == And((Ref("DIVERT_REQ"), Unresolved("VALVE_ENABLE[STATION_IDX]")))
    assert unresolved(e) == ["VALVE_ENABLE[STATION_IDX]"] and refs(e) == {"DIVERT_REQ"}

def test_parse_st_programs_comments_lines():
    src = "PROGRAM Safety\n  // c\n  (* block\n comment *)\n  OK := A AND B;\nEND_PROGRAM\nPROGRAM Conv\n  m1 := OK;\nEND_PROGRAM\n"
    rungs = parse_st(src)
    assert [(r.id, r.line) for r in rungs] == [("Safety/OK", 5), ("Conv/M1", 8)]
    assert rungs[0].source == "OK := A AND B;"

def test_duplicate_writer_rejected():
    with pytest.raises(STParseError) as ei:
        parse_st("PROGRAM P\n X := A;\n x := B;\nEND_PROGRAM\n")
    assert ei.value.line == 3

def test_statement_outside_program_rejected():
    with pytest.raises(STParseError):
        parse_st("X := A;\n")

def test_identifier_then_junk_is_unresolved():
    assert parse_expr("X > 5") == Unresolved("X > 5")
    assert parse_expr("A B") == Unresolved("A B")
    assert parse_expr("A AND X > 5") == And((Ref("A"), Unresolved("X > 5")))
    assert parse_expr("A AND X > 5 OR B") == Or((And((Ref("A"), Unresolved("X > 5"))), Ref("B")))
    assert parse_expr("(X > 5) AND B") == And((Unresolved("X > 5"), Ref("B")))

def test_parse_st_mixed_case_target():
    rungs = parse_st("program Mixed\n  m101_run := Start_PB and not stop;\nend_program\n")
    assert [(r.routine, r.target) for r in rungs] == [("Mixed", "M101_RUN")]
    assert rungs[0].expr == And((Ref("START_PB"), Not(Ref("STOP"))))

def test_parse_st_missing_semicolon_and_end_program():
    with pytest.raises(STParseError) as ei:
        parse_st("PROGRAM P\n X := A\nEND_PROGRAM\n")
    assert ei.value.line == 2
    with pytest.raises(STParseError):
        parse_st("PROGRAM P\n X := A;\n")
