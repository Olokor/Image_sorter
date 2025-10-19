"""
SQLAlchemy models for NYSC Camp Photo Sorting DB
Handles photographers, sessions, students, photos, and face embeddings
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, LargeBinary, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

class Photographer(Base):
    __tablename__ = 'photographers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # License info (stored locally, synced from cloud)
    license_valid_until = Column(DateTime)
    sessions = relationship('CampSession', back_populates='photographer')


class CampSession(Base):
    __tablename__ = 'camp_sessions'
    
    id = Column(Integer, primary_key=True)
    photographer_id = Column(Integer, ForeignKey('photographers.id'), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., "Summer Camp 2025"
    location = Column(String(200))
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    
    # Billing
    is_free_trial = Column(Boolean, default=False)
    student_count = Column(Integer, default=0)
    amount_due = Column(Float, default=0.0)  # ₦200 per student
    payment_verified = Column(Boolean, default=False)
    payment_reference = Column(String(100))
    
    # Status
    is_active = Column(Boolean, default=True)
    closed_at = Column(DateTime)
    
    photographer = relationship('Photographer', back_populates='sessions')
    students = relationship('Student', back_populates='session')
    photos = relationship('Photo', back_populates='session')


class Student(Base):
    __tablename__ = 'students'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('camp_sessions.id'), nullable=False)
    
    # Identifiers
    state_code = Column(String(20), nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100))
    phone = Column(String(20))
    
    # Reference photo & embedding
    reference_photo_path = Column(String(500))
    embedding = Column(LargeBinary)  # Stored as numpy array bytes
    embedding_model = Column(String(50), default='Facenet')  # Track which model
    
    registered_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship('CampSession', back_populates='students')
    faces = relationship('Face', back_populates='student')
    student_photos = relationship('StudentPhoto', back_populates='student')


class Photo(Base):
    __tablename__ = 'photos'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('camp_sessions.id'), nullable=False)
    
    # File info
    original_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500))
    file_hash = Column(String(64), unique=True)  # SHA256 to detect duplicates
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    
    # Processing
    processed = Column(Boolean, default=False)
    face_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    
    session = relationship('CampSession', back_populates='photos')
    faces = relationship('Face', back_populates='photo')
    student_photos = relationship('StudentPhoto', back_populates='photo')


class Face(Base):
    __tablename__ = 'faces'
    
    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey('photos.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('students.id'))  # Null if unmatched
    
    # Face detection
    bbox_x = Column(Integer)
    bbox_y = Column(Integer)
    bbox_width = Column(Integer)
    bbox_height = Column(Integer)
    confidence = Column(Float)
    
    # Embedding
    embedding = Column(LargeBinary)
    embedding_model = Column(String(50), default='Facenet')
    
    # Matching
    match_confidence = Column(Float)  # Similarity score (0-1)
    manual_verified = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)  # For borderline matches
    
    detected_at = Column(DateTime, default=datetime.utcnow)
    
    photo = relationship('Photo', back_populates='faces')
    student = relationship('Student', back_populates='faces')


class StudentPhoto(Base):
    """Many-to-many relationship between students and photos"""
    __tablename__ = 'student_photos'
    
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    photo_id = Column(Integer, ForeignKey('photos.id'), nullable=False)
    
    # Sharing
    shared = Column(Boolean, default=False)
    shared_at = Column(DateTime)
    download_count = Column(Integer, default=0)
    
    student = relationship('Student', back_populates='student_photos')
    photo = relationship('Photo', back_populates='student_photos')


class ShareSession(Base):
    """Ephemeral sharing sessions for QR code access"""
    __tablename__ = 'share_sessions'
    
    id = Column(Integer, primary_key=True)
    session_uuid = Column(String(36), unique=True, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    
    # Access control
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    download_limit = Column(Integer, default=50)
    downloads_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    # Access log
    last_accessed = Column(DateTime)
    access_count = Column(Integer, default=0)


# Database initialization
def init_db(db_path='sqlite:///local.db'):
    """Initialize database and create all tables"""
    engine = create_engine(db_path, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session

if __name__ == '__main__':
    # Test database creation
    engine, Session = init_db('sqlite:///local.db')
    print("✓ Database tables created successfully")
    print(f"✓ Tables: {Base.metadata.tables.keys()}")