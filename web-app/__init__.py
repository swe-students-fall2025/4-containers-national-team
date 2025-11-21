"""Application factory for the Pitch Detector web app."""

# pylint: disable=invalid-name, import-error

import os

from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient
from routes import bp as main_bp

load_dotenv()


def create_app() -> Flask:
    """Create and configure the flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.secret_key = os.getenv("SECRET_KEY", "to change later")

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI environment variable is not set")

    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True)
    db_name = os.getenv("MONGO_DB_NAME", "pitchdb")
    app.db = client[db_name]

    audio_dir = os.getenv("AUDIO_DIR", os.path.join("data", "recordings"))
    os.makedirs(audio_dir, exist_ok=True)
    app.config["AUDIO_DIR"] = audio_dir

    app.register_blueprint(main_bp)

    return app
