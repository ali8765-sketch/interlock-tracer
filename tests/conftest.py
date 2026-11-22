from pathlib import Path

import pytest

from interlock_tracer.loader import load_project

EXAMPLES = Path(__file__).parents[1] / "examples" / "line3"


@pytest.fixture(scope="session")
def project13():
    return load_project(EXAMPLES / "v1.3")


@pytest.fixture(scope="session")
def project14():
    return load_project(EXAMPLES / "v1.4")


@pytest.fixture(scope="session")
def store13(project13, tmp_path_factory):
    from interlock_tracer.graph_store import build_store

    d = tmp_path_factory.mktemp("stores") / "v13"
    build_store(project13, d)
    return d


@pytest.fixture(scope="session")
def store14(project14, tmp_path_factory):
    from interlock_tracer.graph_store import build_store

    d = tmp_path_factory.mktemp("stores") / "v14"
    build_store(project14, d)
    return d


@pytest.fixture(scope="session")
def c13(store13):
    from interlock_tracer.graph_store import open_store

    conn = open_store(store13)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def c14(store14):
    from interlock_tracer.graph_store import open_store

    conn = open_store(store14)
    yield conn
    conn.close()
