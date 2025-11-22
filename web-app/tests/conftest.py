"""Pytest fixtures and fake MongoDB for the web-app tests."""

# We intentionally create small helper classes with very few methods,
# and we redefine fixture names that pytest expects, so we relax
# a couple of pylint rules here.
# pylint: disable=too-few-public-methods, redefined-outer-name

from pathlib import Path
import os
import sys

import pytest
from bson import ObjectId

# Make sure the parent directory (containing __init__.py) is on the path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from __init__ import create_app  # pylint: disable=import-error, wrong-import-position


class FakeInsertResult:
    """Simple stand-in for pymongo's InsertOneResult."""

    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    """Chainable cursor supporting sort().limit() and iteration."""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction):
        """Sort the stored docs by key and return self."""
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def limit(self, count):
        """Limit the number of docs and return self."""
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    """Minimal subset of the pymongo Collection API used by our routes."""

    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        """Insert a document and assign an _id if missing."""
        new_doc = dict(doc)
        new_doc.setdefault("_id", ObjectId())
        self.docs.append(new_doc)
        return FakeInsertResult(new_doc["_id"])

    def find_one(self, query):
        """Return the first document matching the query, or None."""
        for document in self.docs:
            if all(document.get(k) == v for k, v in query.items()):
                return document
        return None

    def find(self, query):
        """Return a cursor over documents matching the query."""
        matched = [
            document
            for document in self.docs
            if all(document.get(k) == v for k, v in query.items())
        ]
        return FakeCursor(matched)


class FakeDB:
    """Fake database object with users and recordings collections."""

    def __init__(self):
        self.users = FakeCollection()
        self.recordings = FakeCollection()


@pytest.fixture
def app(tmp_path):
    """Create a Flask app instance with a fake DB and temp AUDIO_DIR."""
    # These env vars are read by create_app, but the real Mongo server
    # is never contacted because we immediately swap in FakeDB.
    os.environ["SECRET_KEY"] = "test-secret"
    os.environ["MONGO_URI"] = "mongodb://example"
    os.environ["MONGO_DB_NAME"] = "testdb"
    os.environ["AUDIO_DIR"] = str(tmp_path)

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    flask_app.db = FakeDB()  # swap in our fake DB

    return flask_app


@pytest.fixture
def client(app):
    """Return a Flask test client for the app fixture."""
    return app.test_client()


@pytest.fixture
def fake_db(app):
    """Return the FakeDB instance used by the app."""
    return app.db


@pytest.fixture
def auth_client(client):
    """Test client with a logged-in user created via real signup/login routes."""
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
