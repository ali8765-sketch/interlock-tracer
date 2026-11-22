import json
import shutil

import pytest

from interlock_tracer.loader import coerce_bool, load_project
from interlock_tracer.model import Unresolved

from conftest import EXAMPLES


def test_load_v13(project13):
    assert (project13.name, project13.version) == ("line3", "1.3")
    assert len(project13.rungs) == 8
    assert project13.tags["GUARD_DOOR_2_CLOSED"].desc_de == "Schutztür 2 geschlossen"
    assert "VALVE_ENABLE" not in project13.tags          # part of an Unresolved, not a Ref
    assert "STATION_IDX" not in project13.tags
    assert project13.tags["ESTOP_CHAIN_OK"].kind == "internal"
    assert project13.snapshots["s1_m101_wont_start"].values["LS204_BIN_FULL"] is True
    assert "START_PB" not in project13.snapshots["s2_partial"].values


def test_v13_unresolved_rung(project13):
    rung = next(r for r in project13.rungs if r.target == "Y301_DIVERT")
    assert any(isinstance(n, Unresolved) for n in rung.expr.children)


def test_v14_differs(project14):
    assert "AIR_PRESSURE_OK" in project14.tags and project14.version == "1.4"
    assert project14.snapshots["s1_m101_wont_start"].values["AIR_PRESSURE_OK"] is False
    assert project14.snapshots["s3_all_ok"].values["AIR_PRESSURE_OK"] is True


@pytest.mark.parametrize("raw,expected", [(1, True), (0, False), ("TRUE", True), ("false", False), (True, True),
                                          (False, False), ("1", True), ("0", False)])
def test_coerce_ok(raw, expected):
    assert coerce_bool("X", raw) is expected


@pytest.mark.parametrize("raw", ["maybe", 2, None, 1.0, "", [True]])
def test_coerce_rejects(raw):
    with pytest.raises(ValueError, match="X"):
        coerce_bool("X", raw)


def test_snapshot_tags_uppercased(tmp_path):
    dst = tmp_path / "v1.3"
    shutil.copytree(EXAMPLES / "v1.3", dst)
    (dst / "snapshots" / "s4_lower.json").write_text(
        json.dumps({"description": "lower", "values": {"start_pb": 1, "Stop_Pb": "false"}}), encoding="utf-8")
    project = load_project(dst)
    snap = project.snapshots["s4_lower"]          # id defaults to file stem
    assert snap.values == {"START_PB": True, "STOP_PB": False}


def test_snapshot_bad_value_names_tag(tmp_path):
    dst = tmp_path / "v1.3"
    shutil.copytree(EXAMPLES / "v1.3", dst)
    (dst / "snapshots" / "bad.json").write_text(
        json.dumps({"values": {"start_pb": "maybe"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="START_PB"):
        load_project(dst)


def test_undeclared_tags_added(tmp_path):
    dst = tmp_path / "v1.3"
    shutil.copytree(EXAMPLES / "v1.3", dst)
    with open(dst / "logic.st", "a", encoding="utf-8") as f:
        f.write("PROGRAM Extra\n  LAMP := GHOST_IN;\nEND_PROGRAM\n")
    project = load_project(dst)
    for name in ("LAMP", "GHOST_IN"):
        info = project.tags[name]
        assert (info.kind, info.address, info.device, info.desc_en, info.desc_de) == ("undeclared", "", "", "", "")


def test_missing_project_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "nope")
