"""
Application Service Layer
Bridges GUI and backend logic
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session as DBSession

from models import (
    init_db, Photographer, CampSession, Student, 
    Photo, Face, StudentPhoto, ShareSession
)
from face_service import FaceService


class AppService:
    """Main application service - manages all business logic"""
    
    def __init__(self, db_path='sqlite:///tlp_photos.db'):
        self.engine, SessionMaker = init_db(db_path)
        self.db_session = SessionMaker()
        self.face_service = FaceService()
        self.current_photographer = None
        self.current_session = None
        
        # Initialize photographer (in production, handle login)
        self._init_photographer()
    
    def _init_photographer(self):
        """Initialize or get photographer"""
        # Check if photographer exists
        photographer = self.db_session.query(Photographer).first()
        
        if not photographer:
            # Create default photographer (in production, this would be a registration flow)
            photographer = Photographer(
                name="Demo Photographer",
                email="demo@tlpphoto.com",
                license_valid_until=datetime.utcnow() + timedelta(days=30)
            )
            self.db_session.add(photographer)
            self.db_session.commit()
        
        self.current_photographer = photographer
    
    # ==================== SESSION MANAGEMENT ====================
    
    def create_session(self, name: str, location: str = None) -> CampSession:
        """Create a new camp session"""
        # Check if there's already an active session
        active = self.db_session.query(CampSession).filter_by(
            photographer_id=self.current_photographer.id,
            is_active=True
        ).first()
        
        # Determine if this is free trial
        completed_sessions = self.db_session.query(CampSession).filter_by(
            photographer_id=self.current_photographer.id,
            payment_verified=True
        ).count()
        
        is_free = completed_sessions == 0  # First session is free
        
        session = CampSession(
            photographer_id=self.current_photographer.id,
            name=name,
            location=location,
            is_free_trial=is_free,
            is_active=True
        )
        
        self.db_session.add(session)
        self.db_session.commit()
        
        self.current_session = session
        return session
    
    def get_active_session(self) -> Optional[CampSession]:
        """Get the current active session"""
        if self.current_session and self.current_session.is_active:
            return self.current_session
        
        session = self.db_session.query(CampSession).filter_by(
            photographer_id=self.current_photographer.id,
            is_active=True
        ).first()
        
        self.current_session = session
        return session
    
    def get_all_sessions(self) -> List[CampSession]:
        """Get all sessions for current photographer"""
        return self.db_session.query(CampSession).filter_by(
            photographer_id=self.current_photographer.id
        ).order_by(CampSession.start_date.desc()).all()
    
    def set_active_session(self, session_id: int):
        """Set a session as active"""
        session = self.db_session.query(CampSession).get(session_id)
        if session:
            self.current_session = session
    
    def close_session(self, session: CampSession):
        """Close a session and calculate billing"""
        session.is_active = False
        session.closed_at = datetime.utcnow()
        
        # Calculate amount due (₦200 per student)
        if not session.is_free_trial:
            session.amount_due = session.student_count * 200.0
        
        self.db_session.commit()
    
    # ==================== STUDENT ENROLLMENT ====================
    
    def enroll_student(self, state_code: str, full_name: str, 
                      reference_photo_path: str, email: str = None, 
                      phone: str = None) -> Optional[Student]:
        """Enroll a new student"""
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        # Check for duplicate
        existing = self.db_session.query(Student).filter_by(
            session_id=session.id,
            state_code=state_code
        ).first()
        
        if existing:
            return None  # Already enrolled
        
        # Compute embedding
        embedding = self.face_service.compute_embedding(reference_photo_path)
        if embedding is None:
            raise Exception("Could not detect face in reference photo")
        
        # Create student
        student = Student(
            session_id=session.id,
            state_code=state_code,
            full_name=full_name,
            email=email,
            phone=phone,
            reference_photo_path=reference_photo_path,
            embedding=self.face_service.save_embedding(embedding),
            embedding_model=self.face_service.model_name
        )
        
        self.db_session.add(student)
        
        # Update session count
        session.student_count += 1
        
        self.db_session.commit()
        return student
    
    def get_students(self, session: CampSession = None) -> List[Student]:
        """Get all students in a session"""
        if session is None:
            session = self.get_active_session()
        
        if not session:
            return []
        
        return self.db_session.query(Student).filter_by(
            session_id=session.id
        ).all()
    
    def search_student(self, state_code: str) -> Optional[Student]:
        """Search for student by state code"""
        session = self.get_active_session()
        if not session:
            return None
        
        return self.db_session.query(Student).filter_by(
            session_id=session.id,
            state_code=state_code
        ).first()
    
    # ==================== PHOTO PROCESSING ====================
    
    def import_photos(self, photo_paths: List[str], progress_callback=None) -> Dict:
        """Import and process photos"""
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        results = {
            'processed': 0,
            'skipped': 0,
            'faces_detected': 0,
            'faces_matched': 0
        }
        
        # Get student embeddings for matching
        students = self.get_students(session)
        student_embeddings = []
        for student in students:
            if student.embedding:
                emb = self.face_service.load_embedding(student.embedding)
                student_embeddings.append((student.id, emb))
        
        for idx, photo_path in enumerate(photo_paths):
            try:
                # Update progress
                if progress_callback:
                    progress_callback(idx + 1, len(photo_paths), os.path.basename(photo_path))
                
                # Preprocess
                processed_path, metadata = self.face_service.preprocess_image(
                    photo_path,
                    output_dir=f"processed_photos/session_{session.id}"
                )
                
                # Check duplicate
                existing = self.db_session.query(Photo).filter_by(
                    file_hash=metadata['file_hash']
                ).first()
                
                if existing:
                    results['skipped'] += 1
                    continue
                
                # Create photo record
                photo = Photo(
                    session_id=session.id,
                    original_path=photo_path,
                    thumbnail_path=processed_path,
                    file_hash=metadata['file_hash'],
                    file_size=metadata['original_size'],
                    width=metadata['width'],
                    height=metadata['height']
                )
                self.db_session.add(photo)
                self.db_session.flush()
                
                # Detect faces
                faces_data = self.face_service.detect_faces(processed_path)
                results['faces_detected'] += len(faces_data)
                
                matched_students = set()
                
                for face_data in faces_data:
                    # Match face
                    match_result = self.face_service.match_face(
                        face_data['embedding'],
                        student_embeddings
                    )
                    
                    # Store face
                    bbox = face_data['bbox']
                    face = Face(
                        photo_id=photo.id,
                        student_id=match_result['student_id'],
                        bbox_x=bbox[0],
                        bbox_y=bbox[1],
                        bbox_width=bbox[2],
                        bbox_height=bbox[3],
                        confidence=face_data['confidence'],
                        embedding=self.face_service.save_embedding(face_data['embedding']),
                        embedding_model=self.face_service.model_name,
                        match_confidence=match_result['confidence'],
                        needs_review=match_result['needs_review']
                    )
                    self.db_session.add(face)
                    
                    if match_result['student_id']:
                        matched_students.add(match_result['student_id'])
                        results['faces_matched'] += 1
                
                # Create associations
                for student_id in matched_students:
                    student_photo = StudentPhoto(
                        student_id=student_id,
                        photo_id=photo.id
                    )
                    self.db_session.add(student_photo)
                
                # Update photo
                photo.processed = True
                photo.face_count = len(faces_data)
                photo.processed_at = datetime.utcnow()
                
                results['processed'] += 1
                
            except Exception as e:
                print(f"Error processing {photo_path}: {e}")
                results['skipped'] += 1
        
        self.db_session.commit()
        return results
    
    def get_photos(self, session: CampSession = None) -> List[Photo]:
        """Get all photos in a session"""
        if session is None:
            session = self.get_active_session()
        
        if not session:
            return []
        
        return self.db_session.query(Photo).filter_by(
            session_id=session.id
        ).order_by(Photo.uploaded_at.desc()).all()
    
    def get_student_photos(self, student: Student) -> List[Photo]:
        """Get all photos for a student"""
        return self.db_session.query(Photo).join(StudentPhoto).filter(
            StudentPhoto.student_id == student.id
        ).all()
    
    # ==================== REVIEW & MATCHING ====================
    
    def get_faces_needing_review(self) -> List[Face]:
        """Get faces that need manual review"""
        session = self.get_active_session()
        if not session:
            return []
        
        return self.db_session.query(Face).join(Photo).filter(
            Photo.session_id == session.id,
            Face.needs_review == True
        ).all()
    
    def confirm_match(self, face_id: int, student_id: int):
        """Manually confirm a face match"""
        face = self.db_session.query(Face).get(face_id)
        if face:
            face.student_id = student_id
            face.needs_review = False
            face.manual_verified = True
            
            # Create association
            existing = self.db_session.query(StudentPhoto).filter_by(
                student_id=student_id,
                photo_id=face.photo_id
            ).first()
            
            if not existing:
                student_photo = StudentPhoto(
                    student_id=student_id,
                    photo_id=face.photo_id
                )
                self.db_session.add(student_photo)
            
            self.db_session.commit()
    
    # ==================== LICENSE MANAGEMENT ====================
    
    def check_license(self) -> Dict:
        """Check license validity"""
        if not self.current_photographer.license_valid_until:
            return {'valid': False, 'expires': None}
        
        now = datetime.utcnow()
        valid = now < self.current_photographer.license_valid_until
        
        return {
            'valid': valid,
            'expires': self.current_photographer.license_valid_until.strftime('%Y-%m-%d'),
            'days_remaining': (self.current_photographer.license_valid_until - now).days
        }
    
    def get_session_stats(self) -> Dict:
        """Get statistics for current session"""
        session = self.get_active_session()
        if not session:
            return {}
        
        photos = self.get_photos(session)
        students = self.get_students(session)
        
        total_faces = sum(p.face_count for p in photos)
        matched_faces = self.db_session.query(Face).join(Photo).filter(
            Photo.session_id == session.id,
            Face.student_id != None
        ).count()
        
        return {
            'session_name': session.name,
            'students': len(students),
            'photos': len(photos),
            'total_faces': total_faces,
            'matched_faces': matched_faces,
            'needs_review': self.db_session.query(Face).join(Photo).filter(
                Photo.session_id == session.id,
                Face.needs_review == True
            ).count()
        }
    
    def close(self):
        """Close database connection"""
        self.db_session.close()