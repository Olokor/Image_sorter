"""
Application Service Layer - RAW SQL FIX
Uses raw SQL for operations causing recursion
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import text

from models import (
    init_db, Photographer, CampSession, Student, 
    Photo, Face, StudentPhoto
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
        
        self._init_photographer()
    
    def _init_photographer(self):
        """Initialize or get photographer"""
        photographer = self.db_session.query(Photographer).first()
        
        if not photographer:
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
        """Create a new camp session - RAW SQL"""
        # Count using raw SQL
        result = self.db_session.execute(text(
            "SELECT COUNT(*) FROM camp_sessions WHERE photographer_id = :pid AND payment_verified = 1"
        ), {"pid": self.current_photographer.id})
        completed_count = result.scalar()
        
        is_free = (completed_count == 0)
        
        # Insert using raw SQL
        now = datetime.utcnow()
        self.db_session.execute(text(
            """INSERT INTO camp_sessions 
            (photographer_id, name, location, is_free_trial, is_active, student_count, start_date, amount_due, payment_verified)
            VALUES (:pid, :name, :loc, :free, 1, 0, :start, 0.0, 0)"""
        ), {
            "pid": self.current_photographer.id,
            "name": name,
            "loc": location,
            "free": 1 if is_free else 0,
            "start": now
        })
        self.db_session.commit()
        
        # Get the created session
        session = self.db_session.query(CampSession).filter(
            CampSession.photographer_id == self.current_photographer.id,
            CampSession.name == name
        ).order_by(CampSession.id.desc()).first()
        
        self.current_session = session
        return session
    
    def get_active_session(self) -> Optional[CampSession]:
        """Get the current active session"""
        if self.current_session and self.current_session.is_active:
            return self.current_session
        
        session = self.db_session.query(CampSession).filter(
            CampSession.photographer_id == self.current_photographer.id,
            CampSession.is_active == True
        ).first()
        
        self.current_session = session
        return session
    
    def get_all_sessions(self) -> List[CampSession]:
        """Get all sessions for current photographer"""
        return self.db_session.query(CampSession).filter(
            CampSession.photographer_id == self.current_photographer.id
        ).order_by(CampSession.start_date.desc()).all()
    
    def set_active_session(self, session_id: int):
        """Set a session as active"""
        session = self.db_session.query(CampSession).get(session_id)
        if session:
            self.current_session = session
    
    def close_session(self, session: CampSession):
        """Close a session and calculate billing"""
        amount = 0.0 if session.is_free_trial else session.student_count * 200.0
        
        self.db_session.execute(text(
            "UPDATE camp_sessions SET is_active = 0, closed_at = :now, amount_due = :amount WHERE id = :id"
        ), {"now": datetime.utcnow(), "amount": amount, "id": session.id})
        self.db_session.commit()
    
    # ==================== STUDENT ENROLLMENT ====================
    
    def enroll_student(self, state_code: str, full_name: str, 
                      reference_photo_path: str, email: str = None, 
                      phone: str = None) -> Optional[Student]:
        """Enroll a new student - RAW SQL"""
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        # Check duplicate using raw SQL
        result = self.db_session.execute(text(
            "SELECT id FROM students WHERE session_id = :sid AND state_code = :code"
        ), {"sid": session.id, "code": state_code})
        
        if result.fetchone():
            return None  # Already enrolled
        
        # Compute embedding
        embedding = self.face_service.compute_embedding(reference_photo_path)
        if embedding is None:
            raise Exception("Could not detect face in reference photo")
        
        # Insert using raw SQL
        embedding_bytes = self.face_service.save_embedding(embedding)
        
        self.db_session.execute(text(
            """INSERT INTO students 
            (session_id, state_code, full_name, email, phone, reference_photo_path, embedding, embedding_model, registered_at)
            VALUES (:sid, :code, :name, :email, :phone, :photo, :emb, :model, :reg)"""
        ), {
            "sid": session.id,
            "code": state_code,
            "name": full_name,
            "email": email,
            "phone": phone,
            "photo": reference_photo_path,
            "emb": embedding_bytes,
            "model": self.face_service.model_name,
            "reg": datetime.utcnow()
        })
        
        # Update session count
        self.db_session.execute(text(
            "UPDATE camp_sessions SET student_count = student_count + 1 WHERE id = :id"
        ), {"id": session.id})
        
        self.db_session.commit()
        
        # Get the created student
        student = self.db_session.query(Student).filter(
            Student.session_id == session.id,
            Student.state_code == state_code
        ).first()
        
        return student
    
    def get_students(self, session: CampSession = None) -> List[Student]:
        """Get all students in a session"""
        if session is None:
            session = self.get_active_session()
        
        if not session:
            return []
        
        return self.db_session.query(Student).filter(
            Student.session_id == session.id
        ).all()
    
    def search_student(self, state_code: str) -> Optional[Student]:
        """Search for student by state code"""
        session = self.get_active_session()
        if not session:
            return None
        
        return self.db_session.query(Student).filter(
            Student.session_id == session.id,
            Student.state_code == state_code
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
        
        # Get student embeddings
        students = self.get_students(session)
        student_embeddings = []
        for student in students:
            if student.embedding:
                emb = self.face_service.load_embedding(student.embedding)
                student_embeddings.append((student.id, emb))
        
        for idx, photo_path in enumerate(photo_paths):
            try:
                if progress_callback:
                    progress_callback(idx + 1, len(photo_paths), os.path.basename(photo_path))
                
                # Preprocess
                processed_path, metadata = self.face_service.preprocess_image(
                    photo_path,
                    output_dir=f"processed_photos/session_{session.id}"
                )
                
                # Check duplicate
                result = self.db_session.execute(text(
                    "SELECT id FROM photos WHERE file_hash = :hash"
                ), {"hash": metadata['file_hash']})
                
                if result.fetchone():
                    results['skipped'] += 1
                    continue
                
                # Insert photo using raw SQL
                self.db_session.execute(text(
                    """INSERT INTO photos 
                    (session_id, original_path, thumbnail_path, file_hash, file_size, width, height, 
                     processed, face_count, uploaded_at)
                    VALUES (:sid, :orig, :thumb, :hash, :size, :w, :h, 0, 0, :up)"""
                ), {
                    "sid": session.id,
                    "orig": photo_path,
                    "thumb": processed_path,
                    "hash": metadata['file_hash'],
                    "size": metadata['original_size'],
                    "w": metadata['width'],
                    "h": metadata['height'],
                    "up": datetime.utcnow()
                })
                self.db_session.commit()
                
                # Get photo ID
                result = self.db_session.execute(text(
                    "SELECT id FROM photos WHERE file_hash = :hash"
                ), {"hash": metadata['file_hash']})
                photo_id = result.scalar()
                
                # Detect faces
                faces_data = self.face_service.detect_faces(processed_path)
                results['faces_detected'] += len(faces_data)
                
                matched_students = set()
                
                for face_data in faces_data:
                    match_result = self.face_service.match_face(
                        face_data['embedding'],
                        student_embeddings
                    )
                    
                    bbox = face_data['bbox']
                    embedding_bytes = self.face_service.save_embedding(face_data['embedding'])
                    
                    # Insert face using raw SQL
                    self.db_session.execute(text(
                        """INSERT INTO faces 
                        (photo_id, student_id, bbox_x, bbox_y, bbox_width, bbox_height, 
                         confidence, embedding, embedding_model, match_confidence, needs_review, detected_at)
                        VALUES (:pid, :sid, :x, :y, :w, :h, :conf, :emb, :model, :match, :review, :det)"""
                    ), {
                        "pid": photo_id,
                        "sid": match_result['student_id'],
                        "x": bbox[0],
                        "y": bbox[1],
                        "w": bbox[2],
                        "h": bbox[3],
                        "conf": face_data['confidence'],
                        "emb": embedding_bytes,
                        "model": self.face_service.model_name,
                        "match": match_result['confidence'],
                        "review": 1 if match_result['needs_review'] else 0,
                        "det": datetime.utcnow()
                    })
                    
                    if match_result['student_id']:
                        matched_students.add(match_result['student_id'])
                        results['faces_matched'] += 1
                
                # Create associations
                for student_id in matched_students:
                    self.db_session.execute(text(
                        "INSERT INTO student_photos (student_id, photo_id) VALUES (:sid, :pid)"
                    ), {"sid": student_id, "pid": photo_id})
                
                # Update photo
                self.db_session.execute(text(
                    "UPDATE photos SET processed = 1, face_count = :count, processed_at = :now WHERE id = :id"
                ), {"count": len(faces_data), "now": datetime.utcnow(), "id": photo_id})
                
                self.db_session.commit()
                results['processed'] += 1
                
            except Exception as e:
                print(f"Error processing {photo_path}: {e}")
                import traceback
                traceback.print_exc()
                results['skipped'] += 1
        
        return results
    
    def get_photos(self, session: CampSession = None) -> List[Photo]:
        """Get all photos in a session"""
        if session is None:
            session = self.get_active_session()
        
        if not session:
            return []
        
        return self.db_session.query(Photo).filter(
            Photo.session_id == session.id
        ).order_by(Photo.uploaded_at.desc()).all()
    
    def get_student_photos(self, student: Student) -> List[Photo]:
        """Get all photos for a student"""
        result = self.db_session.execute(text(
            "SELECT photo_id FROM student_photos WHERE student_id = :sid"
        ), {"sid": student.id})
        
        photo_ids = [row[0] for row in result]
        
        if not photo_ids:
            return []
        
        return self.db_session.query(Photo).filter(
            Photo.id.in_(photo_ids)
        ).all()
    
    def get_faces_needing_review(self) -> List[Face]:
        """Get faces that need manual review"""
        session = self.get_active_session()
        if not session:
            return []
        
        result = self.db_session.execute(text(
            """SELECT f.* FROM faces f 
            JOIN photos p ON f.photo_id = p.id 
            WHERE p.session_id = :sid AND f.needs_review = 1"""
        ), {"sid": session.id})
        
        face_ids = [row[0] for row in result]
        
        if not face_ids:
            return []
        
        return self.db_session.query(Face).filter(Face.id.in_(face_ids)).all()
    
    def confirm_match(self, face_id: int, student_id: int):
        """Manually confirm a face match"""
        face = self.db_session.get(Face, face_id)
        if not face:
            return
        
        # Update face
        self.db_session.execute(text(
            "UPDATE faces SET student_id = :sid, needs_review = 0, manual_verified = 1 WHERE id = :fid"
        ), {"sid": student_id, "fid": face_id})
        
        # Check if association exists
        result = self.db_session.execute(text(
            "SELECT id FROM student_photos WHERE student_id = :sid AND photo_id = :pid"
        ), {"sid": student_id, "pid": face.photo_id})
        
        if not result.fetchone():
            self.db_session.execute(text(
                "INSERT INTO student_photos (student_id, photo_id) VALUES (:sid, :pid)"
            ), {"sid": student_id, "pid": face.photo_id})
        
        self.db_session.commit()
    
    def check_license(self) -> Dict:
        """Check license validity"""
        if not self.current_photographer.license_valid_until:
            return {'valid': False, 'expires': None, 'days_remaining': 0}
        
        now = datetime.utcnow()
        valid = now < self.current_photographer.license_valid_until
        
        return {
            'valid': valid,
            'expires': self.current_photographer.license_valid_until.strftime('%Y-%m-%d'),
            'days_remaining': max(0, (self.current_photographer.license_valid_until - now).days)
        }
    
    def get_session_stats(self) -> Dict:
        """Get statistics for current session"""
        session = self.get_active_session()
        if not session:
            return {}
        
        result = self.db_session.execute(text(
            """SELECT 
                (SELECT COUNT(*) FROM students WHERE session_id = :sid) as students,
                (SELECT COUNT(*) FROM photos WHERE session_id = :sid) as photos,
                (SELECT COALESCE(SUM(face_count), 0) FROM photos WHERE session_id = :sid) as total_faces,
                (SELECT COUNT(*) FROM faces f JOIN photos p ON f.photo_id = p.id 
                 WHERE p.session_id = :sid AND f.student_id IS NOT NULL) as matched,
                (SELECT COUNT(*) FROM faces f JOIN photos p ON f.photo_id = p.id 
                 WHERE p.session_id = :sid AND f.needs_review = 1) as review"""
        ), {"sid": session.id})
        
        row = result.fetchone()
        
        return {
            'session_name': session.name,
            'students': row[0],
            'photos': row[1],
            'total_faces': row[2],
            'matched_faces': row[3],
            'needs_review': row[4]
        }
    
    def close(self):
        """Close database connection"""
        self.db_session.close()