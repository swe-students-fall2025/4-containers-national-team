"""Flask routes for the pitch detector web app."""

import os
import uuid
from datetime import datetime
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from flask_login import (
    UserMixin,
    login_required,
    login_user,
    logout_user,
    current_user,
)

bp = Blueprint("main", __name__)

class User(UserMixin):
    """User class for Flask-Login."""

    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.username = doc["username"]

@bp.route("/")
def home():
    """Render the home page."""
    return render_template("index.html")

@bp.route("/api/signup", methods=["POST"])
def api_signup():
    """Create a new user account."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    db = current_app.db

    existing = db.users.find_one({"username": username})
    if existing:
        return jsonify({"message": "Username already taken"}), 400


    password_hash = generate_password_hash(password)

    user_doc = {
        "username": username,
        "password_hash": password_hash,
        "created_at": datetime.utcnow(),
    }

    result = db.users.insert_one(user_doc)

    return (
        jsonify(
            {
                "message": "Signup successful",
                "user_id": str(result.inserted_id),
            }
        ),
        201,
    )

@bp.route("/api/login", methods=["POST"])
def api_login():
    """Log in an existing user."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"message": "Username and password are required"}), 400

    db = current_app.db

    doc = db.users.find_one({"username": username})
    if not doc:
        return jsonify({"message": "Invalid username or password"}), 401

    if not check_password_hash(doc["password_hash"], password):
        return jsonify({"message": "Invalid username or password"}), 401

    user = User(doc)
    login_user(user)

    return jsonify({"message": "Login successful"}), 200

@bp.route("/pitch")
@login_required
def pitch_page():
    """Render the recording page."""
    return render_template("pitch.html")


@bp.route("/history")
@login_required
def history_page():
    """Render the history page."""
    return render_template("history.html")


@bp.route("/api/upload", methods=["POST"])
def upload_audio():
    """Handle audio upload, save file, and create a recording document."""
    if "audio" not in request.files:
        return jsonify({"error": "missing 'audio' file field"}), 400

    file = request.files["audio"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    # create a random filename with same extension
    ext = os.path.splitext(file.filename)[1] or ".webm"
    filename = f"{uuid.uuid4().hex}{ext}"

    audio_dir = current_app.config["AUDIO_DIR"]
    save_path = os.path.join(audio_dir, filename)
    file.save(save_path)

    db = current_app.db  # type: ignore[attr-defined]

    doc = {
        "user_id": ObjectId(current_user.id),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "source": "mic",
        "audio_filename": filename,
        "duration_s": None,  # can be filled later by frontend
        "status": "pending",
        "analysis": None,
        "error_message": None,
    }

    result = db.recordings.insert_one(doc)
    recording_id = str(result.inserted_id)

    # for now just a dummy analysis
    # ml client will take care of this when it's done
    dummy_analysis = {
        "pitch_hz": 440.0,
        "pitch_note": "A4",
        "confidence": 1.0,
        "method": "dummy",
    }
    db.recordings.update_one(
        {"_id": result.inserted_id},
        {
            "$set": {
                "analysis": dummy_analysis,
                "status": "done",
                "updated_at": datetime.utcnow(),
            }
        },
    )
    # --------------------------

    return jsonify({"id": recording_id, "analysis": dummy_analysis}), 201


@bp.route("/api/recordings", methods=["GET"])
@login_required
def list_recordings():
    """Return recent recordings and their pitch analysis as JSON."""
    db = current_app.db  # type: ignore[attr-defined]

    cursor = (
        db.recordings.find({"user_id": ObjectId(current_user.id)})
        .sort("created_at", -1)
        .limit(20)
    )

    recordings = []
    for doc in cursor:
        rec_id = str(doc["_id"])
        analysis = doc.get("analysis") or {}
        recordings.append(
            {
                "id": rec_id,
                "created_at": (
                    doc.get("created_at").isoformat() if doc.get("created_at") else None
                ),
                "status": doc.get("status"),
                "audio_filename": doc.get("audio_filename"),
                "audio_url": f"/recordings/{doc.get('audio_filename')}",
                "analysis": {
                    "pitch_hz": analysis.get("pitch_hz"),
                    "pitch_note": analysis.get("pitch_note"),
                    "confidence": analysis.get("confidence"),
                },
            }
        )

    return jsonify({"recordings": recordings})


@bp.route("/recordings/<path:filename>", methods=["GET"])
def serve_recording(filename: str):
    """Serve a saved audio file by filename."""
    audio_dir = current_app.config["AUDIO_DIR"]
    return send_from_directory(audio_dir, filename)

@bp.route("/api/logout", methods=["POST"])
@login_required
def api_logout():
    """Log out the current user."""
    logout_user()
    return jsonify({"message": "Logged out"}), 200
