import pytest
from datetime import datetime
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import init_db, Photographer, CampSession, Student
from services.app_service import AppService


@pytest.fixture
def app_service(tmp_path):
    """Fixture: create an AppService with in-memory SQLite"""
    db_url = f"sqlite:///{tmp_path}/test.db"
    service = AppService(db_path=db_url)
    
    # Mock FaceService to avoid running heavy ML models
    mock_face = MagicMock()
    mock_face.model_name = "test_model"
    mock_face.compute_embedding.return_value = [0.1, 0.2, 0.3]
    mock_face.save_embedding.return_value = b"fakebytes"
    mock_face.load_embedding.return_value = [0.1, 0.2, 0.3]
    mock_face.detect_faces.return_value = [
        {"embedding": [0.1, 0.2, 0.3], "bbox": (1, 2, 3, 4), "confidence": 0.95}
    ]
    mock_face.match_face.return_value = {
        "student_id": 1, "confidence": 0.99, "needs_review": False
    }

    service.face_service = mock_face
    return service


def test_init_photographer_created(app_service):
    """Ensure demo photographer is created on init"""
    photographer = app_service.current_photographer
    assert photographer is not None
    assert photographer.name == "Demo Photographer"
    assert isinstance(photographer.license_valid_until, datetime)


def test_create_session(app_service):
    """Should create a new session"""
    session = app_service.create_session("Camp 1", location="Lagos")
    assert session.name == "Camp 1"
    assert session.photographer_id == app_service.current_photographer.id


def test_get_active_session(app_service):
    """Ensure active session retrieval works"""
    s = app_service.create_session("Active Session")
    active = app_service.get_active_session()
    assert active.id == s.id
    assert active.is_active is True


def test_enroll_student(app_service, tmp_path):
    """Should enroll a student using mocked FaceService"""
    # Create a session first
    session = app_service.create_session("Student Camp")
    photo_path = tmp_path / "face.jpg"
    photo_path.write_text("fakeimage")

    student = app_service.enroll_student(
        state_code="TLP001",
        full_name="John Doe",
        reference_photo_path=str(photo_path)
    )
    assert student is not None
    assert student.full_name == "John Doe"
    assert student.session_id == session.id


def test_enroll_student_duplicate(app_service, tmp_path):
    """Should skip duplicate state_code enrollment"""
    session = app_service.create_session("Duplicate Camp")
    photo_path = tmp_path / "face.jpg"
    photo_path.write_text("fakeimage")

    app_service.enroll_student("TLP001", "Jane Doe", str(photo_path))
    dup = app_service.enroll_student("TLP001", "Jane Doe", str(photo_path))
    assert dup is None


def test_close_session(app_service):
    """Should close an active session and calculate amount"""
    session = app_service.create_session("Closing Test")
    session.student_count = 3
    app_service.close_session(session)
    closed = app_service.db_session.query(CampSession).get(session.id)
    assert closed.is_active == 0
    assert closed.amount_due >= 0


def test_check_license_validity(app_service):
    """Check that license is valid initially"""
    result = app_service.check_license()
    assert result["valid"] is True
    assert "expires" in result
    assert result["days_remaining"] >= 0


def test_get_session_stats(app_service):
    """Stats should return correct dictionary keys"""
    s = app_service.create_session("Stats Camp")
    stats = app_service.get_session_stats()
    assert isinstance(stats, dict)
    assert set(stats.keys()) >= {"session_name", "students", "photos", "matched_faces"}


def test_import_photos_basic(app_service, tmp_path):
    """Simulate photo import with mocked face detection"""
    session = app_service.create_session("Photo Camp")
    # enroll a student first
    ref_photo = tmp_path / "ref.jpg"
    ref_photo.write_text("fake")
    student = app_service.enroll_student("TLP001", "Student A", str(ref_photo))

    img_path = tmp_path / "photo1.jpg"
    img_path.write_text("fakephoto")

    # Patch preprocess_image
    app_service.face_service.preprocess_image.return_value = (
        str(img_path),
        {"file_hash": "hash123", "original_size": 1024, "width": 100, "height": 100}
    )

    results = app_service.import_photos([str(img_path)])
    assert results["processed"] >= 0
    assert "faces_detected" in results


def test_confirm_match_updates_face(app_service):
    """Should confirm a face match and create student-photo link"""
    session = app_service.create_session("Manual Match Camp")
    # fake face in DB
    from sqlalchemy import text

    face_id = app_service.db_session.execute(
        text("INSERT INTO faces (photo_id, confidence, detected_at) VALUES (1, 0.9, :now)"),
        {"now": datetime.utcnow()}
    ).lastrowid


    app_service.db_session.commit()

    app_service.confirm_match(face_id=face_id, student_id=1)
    face = app_service.db_session.execute(
    text("SELECT student_id, manual_verified FROM faces WHERE id = :fid"),
    {"fid": face_id}
).fetchone()

    assert face[0] == 1
    assert face[1] == 1
