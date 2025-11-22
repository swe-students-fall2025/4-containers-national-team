"""Application factory for the Pitch Detector web app."""

# pylint: disable=invalid-name, import-error

import os

from dotenv import load_dotenv
from flask import Flask, current_app
from flask_login import LoginManager
from bson import ObjectId
from pymongo import MongoClient
from routes import bp as main_bp
from routes import User

load_dotenv()

login_manager = LoginManager()

def create_app() -> Flask:
    """Create and configure the flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.secret_key = os.getenv("SECRET_KEY", "to change later")

    login_manager.init_app(app)
    login_manager.login_view = "main.home"

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

    @login_manager.user_loader
    def load_user(user_id):
        db = current_app.db
        doc = db.users.find_one({"_id": ObjectId(user_id)})
        if doc:
            return User(doc)
        return None

    return app
