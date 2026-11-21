import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDERRADAR_DB", str(tmp_path / "screening.sqlite3"))
