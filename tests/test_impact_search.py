from interlock_tracer.graph_store import open_store
from interlock_tracer.trace import impact, upstream_inputs
from interlock_tracer.search import find_tags
from interlock_tracer.diff import diff_stores

def test_graph_queries(store13, store14):
    a, b = open_store(store13), open_store(store14)
    try:
        hits = impact(a, 'guard_door_2_closed')
        assert [h.output for h in hits] == ['HORN', 'M101_RUN', 'M102_RUN', 'M103_RUN']
        assert hits[1].path[0] == 'GUARD_DOOR_2_CLOSED' and hits[1].path[-1] == 'M101_RUN'
        assert upstream_inputs(b, 'M101_RUN') - upstream_inputs(a, 'M101_RUN') == {'AIR_PRESSURE_OK', 'GUARD_DOOR_3_CLOSED'}
        assert find_tags(a, 'Schutztür 2')[0].name == 'GUARD_DOOR_2_CLOSED'
        assert find_tags(a, '" *') == []
        d = diff_stores(a, b)
        assert d.changed_rungs == ['Conveyors/M101_RUN', 'Safety/GUARDS_OK']
        assert d.new_dependencies['M101_RUN'] == {'AIR_PRESSURE_OK', 'GUARD_DOOR_3_CLOSED'}
    finally:
        a.close(); b.close()
