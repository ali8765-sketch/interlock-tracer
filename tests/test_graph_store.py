import pytest
import relate

from interlock_tracer.graph_store import (
    MAX_HOPS,
    all_rungs,
    all_tags,
    build_store,
    open_store,
    project_meta,
    snapshot_ids,
    snapshot_values,
    tag_info,
    writer_rung,
)


def test_roundtrip_every_rung(project13, store13):
    conn = open_store(store13)
    for r in project13.rungs:
        assert writer_rung(conn, r.target) == r
    assert writer_rung(conn, "START_PB") is None


def test_roundtrip_v14(project14, store14):
    conn = open_store(store14)
    for r in project14.rungs:
        assert writer_rung(conn, r.target) == r


def test_meta_tags_snapshots(store13):
    conn = open_store(store13)
    assert project_meta(conn) == ("line3", "1.3")
    assert tag_info(conn, "guard_door_2_closed").desc_en == "Guard door 2 closed"
    assert snapshot_values(conn, "s1_m101_wont_start")["M102_OVERLOAD"] is True
    assert snapshot_ids(conn) == ["s1_m101_wont_start", "s2_partial", "s3_all_ok"]
    with pytest.raises(KeyError):
        snapshot_values(conn, "nope")


def test_all_tags_and_rungs(project13, store13):
    conn = open_store(store13)
    assert all_tags(conn) == project13.tags
    assert all_rungs(conn) == {r.id: r.source for r in project13.rungs}
    assert tag_info(conn, "NO_SUCH_TAG") is None
    assert MAX_HOPS == 60


def test_read_only(store13):
    with pytest.raises(relate.OperationalError):
        open_store(store13).execute("CREATE (:X)")


def test_lifecycle(project13, tmp_path):
    d = tmp_path / "s"
    build_store(project13, d)
    build_store(project13, d)  # rebuild over existing
    a, b = open_store(d), open_store(d)  # two read-only opens
    assert project_meta(a) == project_meta(b)
    with pytest.raises(FileNotFoundError):
        open_store(tmp_path / "missing")
