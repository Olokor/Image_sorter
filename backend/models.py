"""
Peewee models for NYSC Camp Photo Sorting DB
Lightweight ORM with no SQLAlchemy dependency
"""
from datetime import datetime
from typing import Optional
import hashlib
from peewee import *

# Database instance (will be initialized in init_db)
db = SqliteDatabase(None)


class BaseModel(Model):
    """Base model with database binding"""
    class Meta:
        database = db


class Photographer(BaseModel):
    id = AutoField(primary_key=True)
    name = CharField(max_length=100)
    email = CharField(max_length=100, unique=True, index=True)
    password_hash = CharField(max_length=256)
    phone = CharField(max_length=20, null=True)
    created_at = DateTimeField(default=datetime.utcnow)
    last_login = DateTimeField(null=True)
    is_active = BooleanField(default=True)
    license_valid_until = DateTimeField(null=True)
    
    # Session tracking fields
    current_session_student_count = IntegerField(default=0)
    total_students_registered = IntegerField(default=0)
    last_backend_sync = DateTimeField(null=True)
    
    class Meta:
        table_name = 'photographers'
    
    def set_password(self, password: str) -> None:
        """Hash and set password"""
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    def check_password(self, password: str) -> bool:
        """Verify password"""
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()


class CampSession(BaseModel):
    id = AutoField(primary_key=True)
    photographer = ForeignKeyField(Photographer, backref='sessions', on_delete='CASCADE')
    name = CharField(max_length=100)
    location = CharField(max_length=200, null=True)
    start_date = DateTimeField(default=datetime.utcnow)
    end_date = DateTimeField(null=True)
    
    is_free_trial = BooleanField(default=False)
    student_count = IntegerField(default=0)
    amount_due = FloatField(default=0.0)
    payment_verified = BooleanField(default=False)
    payment_reference = CharField(max_length=100, null=True)
    is_active = BooleanField(default=True)
    closed_at = DateTimeField(null=True)
    
    class Meta:
        table_name = 'camp_sessions'


class Student(BaseModel):
    id = AutoField(primary_key=True)
    session = ForeignKeyField(CampSession, backref='students', on_delete='CASCADE', index=True)
    state_code = CharField(max_length=20, index=True)
    full_name = CharField(max_length=100)
    email = CharField(max_length=100, null=True)
    phone = CharField(max_length=20, null=True)
    reference_photo_path = CharField(max_length=500, null=True)
    embedding = BlobField(null=True)
    embedding_model = CharField(max_length=50, default='buffalo_l')
    registered_at = DateTimeField(default=datetime.utcnow)
    
    # Download tracking
    total_downloads = IntegerField(default=0)
    
    class Meta:
        table_name = 'students'


class Photo(BaseModel):
    id = AutoField(primary_key=True)
    session = ForeignKeyField(CampSession, backref='photos', on_delete='CASCADE', index=True)
    original_path = CharField(max_length=500)
    thumbnail_path = CharField(max_length=500, null=True)
    file_hash = CharField(max_length=64, unique=True, index=True)
    file_size = IntegerField(null=True)
    width = IntegerField(null=True)
    height = IntegerField(null=True)
    processed = BooleanField(default=False)
    face_count = IntegerField(default=0)
    uploaded_at = DateTimeField(default=datetime.utcnow)
    processed_at = DateTimeField(null=True)
    
    class Meta:
        table_name = 'photos'


class Face(BaseModel):
    id = AutoField(primary_key=True)
    photo = ForeignKeyField(Photo, backref='faces', on_delete='CASCADE', index=True)
    student = ForeignKeyField(Student, backref='faces', null=True, on_delete='CASCADE', index=True)
    bbox_x = IntegerField(null=True)
    bbox_y = IntegerField(null=True)
    bbox_width = IntegerField(null=True)
    bbox_height = IntegerField(null=True)
    confidence = FloatField(null=True)
    embedding = BlobField(null=True)
    embedding_model = CharField(max_length=50, default='buffalo_l')
    match_confidence = FloatField(null=True)
    manual_verified = BooleanField(default=False)
    needs_review = BooleanField(default=False)
    detected_at = DateTimeField(default=datetime.utcnow)
    
    class Meta:
        table_name = 'faces'


class StudentPhoto(BaseModel):
    id = AutoField(primary_key=True)
    student = ForeignKeyField(Student, backref='student_photos', on_delete='CASCADE', index=True)
    photo = ForeignKeyField(Photo, backref='student_photos', on_delete='CASCADE', index=True)
    shared = BooleanField(default=False)
    shared_at = DateTimeField(null=True)
    download_count = IntegerField(default=0)
    
    class Meta:
        table_name = 'student_photos'


class ShareSession(BaseModel):
    id = AutoField(primary_key=True)
    session_uuid = CharField(max_length=36, unique=True, index=True)
    student = ForeignKeyField(Student, backref='share_sessions', on_delete='CASCADE', index=True)
    created_at = DateTimeField(default=datetime.utcnow)
    expires_at = DateTimeField()
    download_limit = IntegerField(default=50)
    downloads_used = IntegerField(default=0)
    is_active = BooleanField(default=True)
    last_accessed = DateTimeField(null=True)
    access_count = IntegerField(default=0)
    
    class Meta:
        table_name = 'share_sessions'


class PhotoDownload(BaseModel):
    id = AutoField(primary_key=True)
    share_session_uuid = CharField(max_length=36, index=True)
    student = ForeignKeyField(Student, backref='photo_downloads', on_delete='CASCADE', index=True)
    photo = ForeignKeyField(Photo, backref='photo_downloads', on_delete='CASCADE', index=True)
    downloaded_at = DateTimeField(default=datetime.utcnow)
    
    class Meta:
        table_name = 'photo_downloads'


class DownloadRequest(BaseModel):
    id = AutoField(primary_key=True)
    student = ForeignKeyField(Student, backref='download_requests', on_delete='CASCADE', index=True)
    share_session_uuid = CharField(max_length=36, index=True)
    requested_at = DateTimeField(default=datetime.utcnow)
    additional_downloads = IntegerField(default=10)
    reason = TextField(null=True)
    
    # Status: pending, approved, rejected
    status = CharField(max_length=20, default='pending')
    reviewed_at = DateTimeField(null=True)
    reviewed_by = ForeignKeyField(Photographer, backref='reviewed_requests', null=True, on_delete='SET NULL')
    
    class Meta:
        table_name = 'download_requests'


def init_db(db_path: str = 'local.db'):
    """Initialize database and return db instance"""
    # Remove sqlite:/// prefix if present
    if db_path.startswith('sqlite:///'):
        db_path = db_path.replace('sqlite:///', '')
    
    db.init(db_path)
    db.connect()
    
    # Create tables
    db.create_tables([
        Photographer,
        CampSession,
        Student,
        Photo,
        Face,
        StudentPhoto,
        ShareSession,
        PhotoDownload,
        DownloadRequest
    ], safe=True)
    
    return db


if __name__ == '__main__':
    # Test database creation
    database = init_db('test_local.db')
    print(" Database tables created successfully")
    
    # Test photographer creation
    photographer = Photographer.create(name="Test Photographer", email="test@example.com")
    photographer.set_password("test123")
    photographer.save()
    
    print(f" Created photographer: {photographer.name}")
    print(f" Password check: {photographer.check_password('test123')}")
    
    database.close()
    print("\n All tests passed!")