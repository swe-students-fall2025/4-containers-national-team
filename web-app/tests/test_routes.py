from datetime import datetime
from io import BytesIO

from bson import ObjectId


def test_home_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # Just sanity-check that we got HTML back
    assert b"<html" in resp.data


def test_signup_validation(client):
    # Missing username and password
    resp = client.post("/api/signup", json={})
    assert resp.status_code == 400

    # Valid signup
    resp = client.post(
        "/api/signup",
        json={"username": "bob", "password": "pw123"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "user_id" in data

    # Duplicate username
    resp2 = client.post(
        "/api/signup",
        json={"username": "bob", "password": "another"},
    )
    assert resp2.status_code == 400


def test_login_validation(client):
    # Need username + password
    resp = client.post("/api/login", json={})
    assert resp.status_code == 400

    # Create a user to log in as
    client.post("/api/signup", json={"username": "carol", "password": "pw"})

    # Wrong username
    resp = client.post(
        "/api/login",
        json={"username": "nope", "password": "pw"},
    )
    assert resp.status_code == 401

    # Wrong password
    resp = client.post(
        "/api/login",
        json={"username": "carol", "password": "wrong"},
    )
    assert resp.status_code == 401

    # Correct credentials
    resp = client.post(
        "/api/login",
        json={"username": "carol", "password": "pw"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Login successful"


def test_pitch_requires_login(client):
    resp = client.get("/pitch")
    # Flask-Login should redirect anonymous users to the login view ("/")
    assert resp.status_code == 302
    assert "/" in resp.headers["Location"]


def test_history_requires_login(client):
    resp = client.get("/history")
    assert resp.status_code == 302


def test_pitch_page_after_login(auth_client):
    resp = auth_client.get("/pitch")
    assert resp.status_code == 200
    # Page should contain some of the text from the template
    assert b"Record Your Voice" in resp.data


def test_upload_audio_validation(auth_client):
    # No 'audio' field
    resp = auth_client.post("/api/upload", data={})
    assert resp.status_code == 400

    # Empty filename
    resp = auth_client.post(
        "/api/upload",
        data={"audio": (BytesIO(b"test"), "")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_upload_audio_success(auth_client, app, fake_db):
    audio_dir = app.config["AUDIO_DIR"]

    resp = auth_client.post(
        "/api/upload",
        data={"audio": (BytesIO(b"fake-audio-bytes"), "sample.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    rec_id = data["id"]
    assert data["status"] == "pending"

    # File should have been written into AUDIO_DIR
    import os

    files = os.listdir(audio_dir)
    assert len(files) == 1

    # DB should contain the new recording
    from bson import ObjectId as _OID

    doc = fake_db.recordings.find_one({"_id": _OID(rec_id)})
    assert doc is not None
    assert doc["status"] == "pending"


def test_get_recording_invalid_id(client):
    resp = client.get("/api/recordings/not-an-objectid")
    assert resp.status_code == 400


def test_get_recording_not_found(client):
    # Valid ObjectId, but nothing in fake DB
    resp = client.get(f"/api/recordings/{ObjectId()}")
    assert resp.status_code == 404


def test_get_recording_success(auth_client, fake_db):
    # Create a recording document directly in the fake DB
    rec_doc = {
        "user_id": ObjectId(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "status": "done",
        "audio_filename": "foo.webm",
        "analysis": {
            "pitch_hz": 440.0,
            "pitch_note": "A4",
            "confidence": 0.95,
        },
        "error_message": None,
    }
    result = fake_db.recordings.insert_one(rec_doc)
    rec_id = str(result.inserted_id)

    resp = auth_client.get(f"/api/recordings/{rec_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == rec_id
    assert data["analysis"]["pitch_note"] == "A4"
    assert data["analysis"]["pitch_hz"] == 440.0


def test_list_recordings_filters_by_user(auth_client, fake_db):
    # Grab the logged-in user from fake_db.users
    assert fake_db.users.docs  # created by /api/signup in auth_client
    user_id = fake_db.users.docs[0]["_id"]

    # Recording for this user
    fake_db.recordings.insert_one(
        {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "status": "done",
            "audio_filename": "mine.webm",
            "analysis": {"pitch_note": "C4", "pitch_hz": 261.6, "confidence": 0.8},
        }
    )
    # Recording for another user should be ignored
    fake_db.recordings.insert_one(
        {
            "user_id": ObjectId(),
            "created_at": datetime.utcnow(),
            "status": "done",
            "audio_filename": "theirs.webm",
            "analysis": {},
        }
    )

    resp = auth_client.get("/api/recordings")
    assert resp.status_code == 200
    data = resp.get_json()
    recs = data["recordings"]
    assert len(recs) == 1
    assert recs[0]["audio_filename"] == "mine.webm"


def test_serve_recording(auth_client, app):
    import os

    audio_dir = app.config["AUDIO_DIR"]
    filename = "clip.webm"
    path = os.path.join(audio_dir, filename)
    with open(path, "wb") as f:
        f.write(b"12345")

    resp = auth_client.get(f"/recordings/{filename}")
    assert resp.status_code == 200
    assert resp.data == b"12345"


def test_logout(auth_client):
    resp = auth_client.post("/api/logout")
    assert resp.status_code == 200

    # Now accessing a protected page should redirect again
    resp2 = auth_client.get("/pitch")
    assert resp2.status_code == 302
