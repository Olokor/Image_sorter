"""
SQLAlchemy models for NYSC Camp Photo Sorting DB
Recursion-safe relationships and debug-friendly reprs
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

class Photographer(Base):
    __tablename__ = 'photographers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    license_valid_until = Column(DateTime)
    
    sessions = relationship('CampSession', back_populates='photographer', lazy='select')
    
    def __repr__(self):
        return f"<Photographer(id={self.id}, name='{self.name}')>"


class CampSession(Base):
    __tablename__ = 'camp_sessions'
    
    id = Column(Integer, primary_key=True)
    photographer_id = Column(Integer, ForeignKey('photographers.id'), nullable=False)
    name = Column(String(100), nullable=False)
    location = Column(String(200))
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    
    is_free_trial = Column(Boolean, default=False)
    student_count = Column(Integer, default=0)
    amount_due = Column(Float, default=0.0)
    payment_verified = Column(Boolean, default=False)
    payment_reference = Column(String(100))
    is_active = Column(Boolean, default=True)
    closed_at = Column(DateTime)
    
    photographer = relationship('Photographer', back_populates='sessions', lazy='select', )
    students = relationship('Student', back_populates='session', lazy='select', cascade='all, delete-orphan', )
    photos = relationship('Photo', back_populates='session', lazy='select', cascade='all, delete-orphan', )
    
    def __repr__(self):
        return f"<CampSession(id={self.id}, name='{self.name}')>"


class Student(Base):
    __tablename__ = 'students'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('camp_sessions.id'), nullable=False)
    state_code = Column(String(20), nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100))
    phone = Column(String(20))
    reference_photo_path = Column(String(500))
    embedding = Column(LargeBinary)
    embedding_model = Column(String(50), default='buffalo_l')
    registered_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship('CampSession', back_populates='students', lazy='select', )
    faces = relationship('Face', back_populates='student', lazy='select', cascade='all, delete-orphan', )
    student_photos = relationship('StudentPhoto', back_populates='student', lazy='select', cascade='all, delete-orphan', )
    
    def __repr__(self):
        return f"<Student(id={self.id}, full_name='{self.full_name}')>"


class Photo(Base):
    __tablename__ = 'photos'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('camp_sessions.id'), nullable=False)
    original_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500))
    file_hash = Column(String(64), unique=True)
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    processed = Column(Boolean, default=False)
    face_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    
    session = relationship('CampSession', back_populates='photos', lazy='select', )
    faces = relationship('Face', back_populates='photo', lazy='select', cascade='all, delete-orphan', )
    student_photos = relationship('StudentPhoto', back_populates='photo', lazy='select', cascade='all, delete-orphan', )
    
    def __repr__(self):
        return f"<Photo(id={self.id}, path='{self.original_path}')>"


class Face(Base):
    __tablename__ = 'faces'
    
    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey('photos.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('students.id'))
    bbox_x = Column(Integer)
    bbox_y = Column(Integer)
    bbox_width = Column(Integer)
    bbox_height = Column(Integer)
    confidence = Column(Float)
    embedding = Column(LargeBinary)
    embedding_model = Column(String(50), default='buffalo_l')
    match_confidence = Column(Float)
    manual_verified = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)
    
    photo = relationship('Photo', back_populates='faces', lazy='select', )
    student = relationship('Student', back_populates='faces', lazy='select', )
    
    def __repr__(self):
        return f"<Face(id={self.id}, match_conf={self.match_confidence})>"


class StudentPhoto(Base):
    __tablename__ = 'student_photos'
    
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    photo_id = Column(Integer, ForeignKey('photos.id'), nullable=False)
    shared = Column(Boolean, default=False)
    shared_at = Column(DateTime)
    download_count = Column(Integer, default=0)
    
    student = relationship('Student', back_populates='student_photos', lazy='select', )
    photo = relationship('Photo', back_populates='student_photos', lazy='select', )
    
    def __repr__(self):
        return f"<StudentPhoto(id={self.id}, shared={self.shared})>"


class ShareSession(Base):
    __tablename__ = 'share_sessions'
    
    id = Column(Integer, primary_key=True)
    session_uuid = Column(String(36), unique=True, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey('students.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    download_limit = Column(Integer, default=50)
    downloads_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_accessed = Column(DateTime)
    access_count = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<ShareSession(id={self.id}, uuid={self.session_uuid})>"


def init_db(db_path='sqlite:///local.db'):
    engine = create_engine(db_path, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


if __name__ == '__main__':
    engine, Session = init_db('sqlite:///test_local.db')
    print("✓ Database tables created successfully")
    print(f"✓ Tables: {list(Base.metadata.tables.keys())}")
    
    session = Session()
    photographer = Photographer(name="Test Photographer", email="test@example.com")
    session.add(photographer)
    session.commit()
    
    print(f"✓ Created photographer: {photographer.name}")
    print(f"✓ Queried photographer: {session.query(Photographer).first().name}")
    session.close()
    print("\n✓ All tests passed!")
