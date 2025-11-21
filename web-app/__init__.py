# web-app/__init__.py
from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient

load_dotenv()


def create_app() -> Flask:
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

    from routes import bp as main_bp

    app.register_blueprint(main_bp)

    return app
