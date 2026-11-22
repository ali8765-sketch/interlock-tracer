import json

import pytest

from interlock_tracer.graph_store import build_store, open_store
from interlock_tracer.loader import load_project
from interlock_tracer.trace import why

M101 = "Conveyors/M101_RUN"


def test_s1_blocked(c13):
    v = why(c13, "M101_RUN", "s1_m101_wont_start")
    assert (v.status, v.value) == ("BLOCKED", False)
    assert set(v.root_causes) == {"GUARD_DOOR_2_CLOSED", "MAINT_KEY_ON", "M102_OVERLOAD", "LS204_BIN_FULL"}
    assert v.root_causes["LS204_BIN_FULL"] is True
    assert ["LS204_BIN_FULL", M101, "M101_RUN"] in v.paths
    assert ["M102_OVERLOAD", "Conveyors/M102_RUN", "M102_RUN", M101, "M101_RUN"] in v.paths
    assert ["GUARD_DOOR_2_CLOSED", "Safety/GUARDS_OK", "GUARDS_OK", "Safety/SAFE_TO_RUN",
            "SAFE_TO_RUN", M101, "M101_RUN"] in v.paths
    assert v.paths == [list(p) for p in sorted(set(map(tuple, v.paths)), key=lambda p: (len(p), p))]


def test_s1_explanation_top_level(c13):
    e = why(c13, "M101_RUN", "s1_m101_wont_start").explanation
    assert (e.kind, e.label, e.value) == ("all_of", "M101_RUN", False)
    assert sorted(c.label for c in e.children) == ["LS204_BIN_FULL", "M102_RUN", "SAFE_TO_RUN"]
    # (GUARDS_OK OR MAINT_KEY_ON) is false -> fixing ANY one operand helps
    safe = next(c for c in e.children if c.label == "SAFE_TO_RUN")
    assert safe.kind == "any_of"
    assert sorted(c.label for c in safe.children) == ["GUARDS_OK", "MAINT_KEY_ON"]


def test_case_insensitive(c13):
    assert why(c13, "m101_run", "s1_m101_wont_start").root_causes == \
        why(c13, "M101_RUN", "s1_m101_wont_start").root_causes
    assert why(c13, "m101_run", "s1_m101_wont_start").output == "M101_RUN"


def test_running(c13):
    v = why(c13, "M101_RUN", "s3_all_ok")
    assert (v.status, v.paths) == ("RUNNING", [])


def test_known_blocker_beats_unknown(c13):
    assert why(c13, "M101_RUN", "s2_partial").status == "BLOCKED"


def test_missing_value(c13):
    v = why(c13, "HORN", "s2_partial")
    assert (v.status, v.missing) == ("INCOMPLETE", ["START_PB"])


def test_unresolved(c13):
    v = why(c13, "Y301_DIVERT", "s1_m101_wont_start")
    assert (v.status, v.unresolved) == ("INCOMPLETE", ["VALVE_ENABLE[STATION_IDX]"])


def test_not_found(c13):
    assert why(c13, "NOPE", "s1_m101_wont_start").status == "NOT_FOUND"
    assert why(c13, "START_PB", "s1_m101_wont_start").status == "NOT_FOUND"


def test_unknown_snapshot(c13):
    with pytest.raises(KeyError):
        why(c13, "M101_RUN", "no_such_snapshot")


def test_v14_new_blocker(c14):
    assert "AIR_PRESSURE_OK" in why(c14, "M101_RUN", "s1_m101_wont_start").root_causes


def _tiny_store(tmp_path, logic, values):
    proj = tmp_path / "proj"
    (proj / "snapshots").mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({"name": "tiny", "version": "0"}))
    (proj / "iolist.csv").write_text("tag,kind,address,device,desc_en,desc_de\n")
    (proj / "logic.st").write_text(logic)
    (proj / "snapshots" / "s.json").write_text(json.dumps({"id": "s", "values": values}))
    store = tmp_path / "store"
    build_store(load_project(proj), store)
    return open_store(store)


def test_seal_in_and_cycle(tmp_path):
    conn = _tiny_store(
        tmp_path,
        "PROGRAM P\n A := (B OR A) AND C;\n X := Y;\n Y := X;\nEND_PROGRAM\n",
        {"B": False, "A": True, "C": True, "X": False},
    )
    try:
        assert why(conn, "A", "s").status == "RUNNING"
        v = why(conn, "X", "s")
        assert v.status == "BLOCKED" and v.root_causes == {"X": False}
        assert v.paths == [["X", "P/Y", "Y", "P/X", "X"]]
    finally:
        conn.close()


def test_cycle_context_dependent_values(tmp_path):
    # T and Z form a cycle, so a tag's value depends on which cycle members are already on the
    # evaluation stack. A memo keyed by tag alone would wrongly reuse T=True from the first operand.
    conn = _tiny_store(
        tmp_path,
        "PROGRAM P\n R := Z AND T;\n T := Z;\n Z := T AND Q;\nEND_PROGRAM\n",
        {"T": False, "Z": True, "Q": True},
    )
    try:
        # R -> Z(stack R,Z) -> T(stack R,Z,T) -> Z on stack -> snapshot True ; T=True ; Z=True AND Q=True
        # R -> T(stack R,T) -> Z(stack R,T,Z) -> T on stack -> snapshot False ; Z=False ; T=False
        # => R = True AND False = False, the blocker is T's snapshot value via Z.
        v = why(conn, "R", "s")
        assert v.status == "BLOCKED"
        assert v.root_causes == {"T": False}
        assert v.paths == [["T", "P/Z", "Z", "P/T", "T", "P/R", "R"]]
    finally:
        conn.close()


def test_shared_subcone_is_memoised(c13, monkeypatch):
    import interlock_tracer.trace as trace

    calls = []
    real = trace.writer_rung
    monkeypatch.setattr(trace, "writer_rung", lambda conn, tag: calls.append(tag) or real(conn, tag))
    why(c13, "M101_RUN", "s1_m101_wont_start")
    assert len(calls) == len(set(calls))  # each tag's rung fetched once per call
