# GAME/tests/test_migrate_smoke.py
# GAME/tests/test_migrate_smoke.py
import importlib
import os


def test_migrate_creates_db(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "ci.db")
    from src.db import migrate

    importlib.reload(migrate)
    migrate.migrate()
    assert (tmp_path / "ci.db").exists()
