import os
from datetime import datetime

import pytest
from bson import ObjectId
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from __init__ import create_app


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    """Simple chainable cursor supporting sort().limit() and iteration."""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    """Very small subset of pymongo Collection API used by our routes."""

    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        d = dict(doc)
        d.setdefault("_id", ObjectId())
        self.docs.append(d)
        return FakeInsertResult(d["_id"])

    def find_one(self, query):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    def find(self, query):
        matched = [
            d for d in self.docs
            if all(d.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(matched)


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.recordings = FakeCollection()


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a Flask app instance with a fake DB and temp AUDIO_DIR."""
    # Make sure env vars exist, but the real Mongo isn't actually used
    os.environ["SECRET_KEY"] = "test-secret"
    os.environ["MONGO_URI"] = "mongodb://example"
    os.environ["MONGO_DB_NAME"] = "testdb"
    os.environ["AUDIO_DIR"] = str(tmp_path)

    app = create_app()
    app.config["TESTING"] = True
    app.db = FakeDB()  # swap in our fake DB

    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def fake_db(app):
    """Access to the fake DB used by the app."""
    return app.db


@pytest.fixture
def auth_client(client):
    """
    Test client with a logged-in user.

    We go through the real /api/signup and /api/login routes so we exercise
    the actual app logic.
    """
    # Signup
    resp = client.post(
        "/api/signup",
        json={"username": "alice", "password": "secret"},
    )
    assert resp.status_code == 201

    # Login
    resp = client.post(
        "/api/login",
        json={"username": "alice", "password": "secret"},
    )
    assert resp.status_code == 200

    return client
