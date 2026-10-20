"""The demo must stay inside data/demo and never touch real data or the committed snapshot."""
from src import demo


def test_demo_writes_only_to_its_own_folder():
    env = demo.demo_env()
    for key in ("DATA_DIR", "DASHBOARD_SNAPSHOT_DIR", "DBT_DUCKDB_PATH"):
        assert env[key].startswith(str(demo.DEMO_DIR)), key
    assert env["PIPELINE_DEMO"] == "1"
    assert demo.DEMO_DIR.name == "demo" and demo.DEMO_DIR.parent.name == "data"  # data/ is git-ignored
