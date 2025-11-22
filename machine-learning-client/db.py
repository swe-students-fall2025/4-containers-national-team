import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()


def _get_mongo_client() -> MongoClient:
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is not set. ")
    return MongoClient(mongo_uri, tlsAllowInvalidCertificates=True)


def get_db():
    client = _get_mongo_client()
    db_name = os.getenv("MONGO_DB_NAME")
    return client[db_name]
