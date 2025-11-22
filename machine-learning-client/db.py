"""Database helpers for the ML client."""

import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()


def _get_mongo_client() -> MongoClient:
    """Create and return a MongoClient based on MONGO_URI."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is not set.")

    client_kwargs = {}
    if "mongodb.net" in mongo_uri:
        client_kwargs["tlsAllowInvalidCertificates"] = True

    return MongoClient(mongo_uri, **client_kwargs)


def get_db():
    """Return the database selected by MONGO_DB_NAME."""
    client = _get_mongo_client()
    db_name = os.getenv("MONGO_DB_NAME")
    if not db_name:
        raise RuntimeError("MONGO_DB_NAME environment variable is not set.")
    return client[db_name]
