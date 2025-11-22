"""Unit tests for db.py in the machine-learning client."""

# We intentionally:
# - access a "protected" helper (_get_mongo_client) to test error handling
# - use tiny fake client classes with only one public method
# So we disable those specific pylint rules here.
# pylint: disable=protected-access,too-few-public-methods

from pathlib import Path
import sys

from pymongo.mongo_client import MongoClient
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


def test_get_mongo_client_returns_client_when_env_present(monkeypatch):
    """When MONGO_URI is set, _get_mongo_client should return a MongoClient."""
    # Make sure the env var exists with some dummy URI
    monkeypatch.setenv("MONGO_URI", "mongodb://example:27017")

    client = db._get_mongo_client()  # type: ignore[attr-defined]

    # We don't care if it actually connects; just that we got a MongoClient back.
    assert isinstance(client, MongoClient)


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


def test_get_db_raises_when_db_name_missing(monkeypatch):
    """If MONGO_DB_NAME is unset, get_db should raise RuntimeError."""

    class DummyClient:
        """Tiny dummy client used only to avoid constructing a real MongoClient."""

    # MONGO_URI must be set so _get_mongo_client would succeed, but
    # we stub it out anyway so we don't create a real MongoClient.
    monkeypatch.setenv("MONGO_URI", "mongodb://example:27017")
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)

    def fake_get_mongo_client():
        """Return a dummy client instead of a real MongoClient."""
        return DummyClient()

    # Avoid touching the real MongoClient
    monkeypatch.setattr(db, "_get_mongo_client", fake_get_mongo_client)

    with pytest.raises(RuntimeError):
        db.get_db()
