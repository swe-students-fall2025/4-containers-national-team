"""Flask routes for the pitch detector web app."""

import os
import uuid
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    """Render the home page."""
    return render_template("index.html")


@bp.route("/pitch")
def pitch_page():
    """Render the recording page."""
    return render_template("pitch.html")


@bp.route("/history")
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
def list_recordings():
    """Return recent recordings and their pitch analysis as JSON."""
    db = current_app.db  # type: ignore[attr-defined]

    cursor = db.recordings.find().sort("created_at", -1).limit(20)

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
