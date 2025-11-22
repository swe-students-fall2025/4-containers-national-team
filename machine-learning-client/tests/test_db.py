"""Unit tests for db.py in the machine-learning client."""

# We intentionally:
# - access a "protected" helper (_get_mongo_client) to test error handling
# - use a tiny FakeClient class with only one public method
# So we disable those specific pylint rules here.
# pylint: disable=protected-access,too-few-public-methods

from pathlib import Path
import sys

import pytest

# Make sure the parent directory (containing db.py) is on the path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db  # pylint: disable=import-error, wrong-import-position


def test_get_mongo_client_raises_when_mongo_uri_missing(monkeypatch):
    """If MONGO_URI isn't set, _get_mongo_client should raise RuntimeError."""
    monkeypatch.delenv("MONGO_URI", raising=False)

    # Accessing the helper directly is intentional in this test.
    with pytest.raises(RuntimeError):
        db._get_mongo_client()  # type: ignore[attr-defined]


def test_get_db_uses_mongo_db_name_env(monkeypatch):
    """get_db should index the MongoClient with the DB name from MONGO_DB_NAME."""

    class FakeClient:
        """Simple fake MongoClient that records which DB name was requested."""

        def __init__(self):
            self.requested_names = []

        def __getitem__(self, name):
            self.requested_names.append(name)
            # Return a simple object we can inspect
            return {"db_name": name}

    fake_client = FakeClient()

    # Ensure env vars exist
    monkeypatch.setenv("MONGO_URI", "mongodb://example:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "pitchdb_test")

    # Replace the real _get_mongo_client with our fake one
    monkeypatch.setattr(db, "_get_mongo_client", lambda: fake_client)

    db_obj = db.get_db()

    assert fake_client.requested_names == ["pitchdb_test"]
    assert db_obj["db_name"] == "pitchdb_test"
