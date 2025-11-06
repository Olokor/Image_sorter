"""
Enhanced Application Service with:
- Multiple reference photos per student
- Backward matching (match new students against existing photos)
- CRUD operations for student embeddings
- Raw SQL to avoid recursion errors
"""
import os
import numpy as np 
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from sqlalchemy import text

from models import (
    init_db, Photographer, CampSession, Student, 
    Photo, Face, StudentPhoto
)
from face_service import EnhancedFaceService as FaceService


class EnhancedAppService:
    """Enhanced application service with backward matching"""
    
    def __init__(self, db_path='sqlite:///photos_sorter.db'):
        self.engine, SessionMaker = init_db(db_path)
        self.db_session = SessionMaker()
        self.face_service = FaceService()
        self.current_photographer = None
        self.current_session = None
        self.current_session = None  # For operations (enroll, import)
        self.viewing_session = None 
        
        self._init_photographer()
    

    def set_viewing_session(self, session_id: int):
        """Set which session to VIEW (doesn't affect operations)"""
        session = self.db_session.query(CampSession).get(session_id)
        if session:
            self.viewing_session = session
            return session
        return None
    
    def get_viewing_session(self) -> Optional[CampSession]:
        """Get session currently being viewed"""
        if self.viewing_session:
            return self.viewing_session
        # Default to active session if no viewing session set
        return self.get_active_session()
    
    def get_students(self, session: CampSession = None) -> List[Student]:
        """Get students - now accepts optional session parameter"""
        if session is None:
            session = self.get_viewing_session()  # Changed!
        
        if not session:
            return []
        
        return self.db_session.query(Student).filter(
            Student.session_id == session.id
        ).all()
    
    def get_session_stats(self, session_id: int = None) -> Dict:
        """Get stats for specific session or viewing session"""
        if session_id:
            session = self.db_session.query(CampSession).get(session_id)
        else:
            session = self.get_viewing_session()
        
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
            'session_id': session.id,
            'session_name': session.name,
            'is_active': session.is_active,
            'students': row[0],
            'photos': row[1],
            'total_faces': row[2],
            'matched_faces': row[3],
            'needs_review': row[4]
        }
    def _init_photographer(self):
        """Initialize or get photographer"""
        photographer = self.db_session.query(Photographer).first()
        
        # if not photographer:
        #     photographer = Photographer(
        #         name="Demo Photographer",
        #         email="demo@tlpphoto.com",
        #         license_valid_until=datetime.utcnow() + timedelta(days=30)
        #     )
        #     self.db_session.add(photographer)
        #     self.db_session.commit()
        
        self.current_photographer = photographer
    
    # ==================== ENHANCED ENROLLMENT WITH MULTIPLE PHOTOS ====================
    
    def enroll_student_multiple_photos(self, state_code: str, full_name: str, 
                                      reference_photo_paths: List[str], 
                                      email: str = None, phone: str = None,
                                      match_existing_photos: bool = True) -> Optional[Student]:
        """
        Enroll student with multiple reference photos for better accuracy
        Optionally matches against existing unmatched photos
        """
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        # Check duplicate
        result = self.db_session.execute(text(
            "SELECT id FROM students WHERE session_id = :sid AND state_code = :code"
        ), {"sid": session.id, "code": state_code})
        
        if result.fetchone():
            return None  # Already enrolled
        
        # Compute embeddings from all reference photos
        embeddings = []
        successful_paths = []
        
        print(f"\n→ Computing embeddings from {len(reference_photo_paths)} photo(s)...")
        for path in reference_photo_paths:
            emb = self.face_service.compute_embedding(path)
            if emb is not None:
                embeddings.append(emb)
                successful_paths.append(path)
                print(f"  ✓ {os.path.basename(path)}")
            else:
                print(f"  ✗ Failed: {os.path.basename(path)}")
        
        if not embeddings:
            raise Exception("Could not detect face in any reference photo")
        
        # Average the embeddings
        avg_embedding = self.face_service.compute_average_embedding(successful_paths)
        
        # Store all reference paths as JSON or comma-separated
        all_paths = ",".join(successful_paths)
        
        # Insert student
        embedding_bytes = self.face_service.save_embedding(avg_embedding)
        
        self.db_session.execute(text(
            """INSERT INTO students 
            (session_id, state_code, full_name, email, phone, reference_photo_path, 
             embedding, embedding_model, registered_at)
            VALUES (:sid, :code, :name, :email, :phone, :photo, :emb, :model, :reg)"""
        ), {
            "sid": session.id,
            "code": state_code,
            "name": full_name,
            "email": email,
            "phone": phone,
            "photo": all_paths,
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
        
        # BACKWARD MATCHING: Match this new student against existing photos
        if match_existing_photos and student:
            print(f"\n→ Checking existing photos for matches with {full_name}...")
            matches_found = self._backward_match_student(student)
            if matches_found > 0:
                print(f"  ✓ Found {matches_found} existing photo(s) with {full_name}!")
        
        return student
    
    def _backward_match_student(self, student: Student) -> int:
        """
        Match a newly enrolled student against all existing photos in session
        Returns number of new matches found
        """
        session = self.get_active_session()
        if not session:
            return 0
        
        # Get student embedding
        student_emb = self.face_service.load_embedding(student.embedding)
        student_embeddings = [(student.id, student_emb)]
        
        # Get all processed photos in session
        photos = self.db_session.query(Photo).filter(
            Photo.session_id == session.id,
            Photo.processed == True
        ).all()
        
        matches_found = 0
        
        for photo in photos:
            # Get unmatched faces in this photo
            faces = self.db_session.query(Face).filter(
                Face.photo_id == photo.id,
                Face.student_id == None  # Only unmatched faces
            ).all()
            
            for face in faces:
                if not face.embedding:
                    continue
                
                face_emb = self.face_service.load_embedding(face.embedding)
                
                # Try to match
                match_result = self.face_service.match_face_enhanced(
                    face_emb, 
                    student_embeddings
                )
                
                if match_result['student_id'] == student.id:
                    # Update face with match
                    self.db_session.execute(text(
                        """UPDATE faces 
                        SET student_id = :sid, match_confidence = :conf, needs_review = :review
                        WHERE id = :fid"""
                    ), {
                        "sid": student.id,
                        "conf": match_result['confidence'],
                        "review": 1 if match_result['needs_review'] else 0,
                        "fid": face.id
                    })
                    
                    # Create student-photo association
                    result = self.db_session.execute(text(
                        "SELECT id FROM student_photos WHERE student_id = :sid AND photo_id = :pid"
                    ), {"sid": student.id, "pid": photo.id})
                    
                    if not result.fetchone():
                        self.db_session.execute(text(
                            "INSERT INTO student_photos (student_id, photo_id) VALUES (:sid, :pid)"
                        ), {"sid": student.id, "pid": photo.id})
                    
                    matches_found += 1
                    status = "⚠ REVIEW" if match_result['needs_review'] else "✓"
                    print(f"  {status} Matched in {os.path.basename(photo.original_path)} "
                          f"(confidence: {match_result['confidence']:.3f})")
        
        self.db_session.commit()
        return matches_found
    
    # ==================== CRUD OPERATIONS ====================
    
    def add_student_reference_photo(self, student_id: int, photo_path: str) -> bool:
        """Add an additional reference photo to improve student's embedding"""
        student = self.db_session.query(Student).get(student_id)
        if not student or not student.embedding:
            return False
        
        # Compute new embedding
        new_emb = self.face_service.compute_embedding(photo_path)
        if new_emb is None:
            return False
        
        # Load existing embedding
        existing_emb = self.face_service.load_embedding(student.embedding)
        
        # Average old and new
        combined_emb = (existing_emb + new_emb) / 2.0
        
        # Normalize
        norm = np.linalg.norm(combined_emb)
        if norm > 0:
            combined_emb = combined_emb / norm
        
        # Update student
        embedding_bytes = self.face_service.save_embedding(combined_emb)
        
        # Update reference photo paths
        current_paths = student.reference_photo_path or ""
        new_paths = f"{current_paths},{photo_path}" if current_paths else photo_path
        
        self.db_session.execute(text(
            """UPDATE students 
            SET embedding = :emb, reference_photo_path = :paths 
            WHERE id = :id"""
        ), {"emb": embedding_bytes, "paths": new_paths, "id": student_id})
        
        self.db_session.commit()
        
        print(f"✓ Added reference photo for {student.full_name}")
        return True
    
    def update_student_info(self, student_id: int, **kwargs) -> bool:
        """Update student information (name, email, phone, etc.)"""
        student = self.db_session.query(Student).get(student_id)
        if not student:
            return False
        
        allowed_fields = ['full_name', 'email', 'phone', 'state_code']
        updates = []
        params = {"id": student_id}
        
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                updates.append(f"{field} = :{field}")
                params[field] = value
        
        if not updates:
            return False
        
        query = f"UPDATE students SET {', '.join(updates)} WHERE id = :id"
        self.db_session.execute(text(query), params)
        self.db_session.commit()
        
        return True
    
    def delete_student(self, student_id: int) -> bool:
        """Delete a student and all associated data"""
        student = self.db_session.query(Student).get(student_id)
        if not student:
            return False
        
        session = self.get_active_session()
        
        # Delete in correct order to avoid foreign key issues
        self.db_session.execute(text("DELETE FROM student_photos WHERE student_id = :id"), {"id": student_id})
        self.db_session.execute(text("DELETE FROM faces WHERE student_id = :id"), {"id": student_id})
        self.db_session.execute(text("DELETE FROM students WHERE id = :id"), {"id": student_id})
        
        # Update session count
        if session:
            self.db_session.execute(text(
                "UPDATE camp_sessions SET student_count = student_count - 1 WHERE id = :id"
            ), {"id": session.id})
        
        self.db_session.commit()
        return True
    
    def recompute_student_embedding(self, student_id: int) -> bool:
        """Recompute embedding from all reference photos"""
        student = self.db_session.query(Student).get(student_id)
        if not student or not student.reference_photo_path:
            return False
        
        # Get all reference paths
        paths = student.reference_photo_path.split(',')
        paths = [p.strip() for p in paths if p.strip()]
        
        if not paths:
            return False
        
        # Compute new embedding
        avg_embedding = self.face_service.compute_average_embedding(paths)
        if avg_embedding is None:
            return False
        
        # Update
        embedding_bytes = self.face_service.save_embedding(avg_embedding)
        self.db_session.execute(text(
            "UPDATE students SET embedding = :emb WHERE id = :id"
        ), {"emb": embedding_bytes, "id": student_id})
        
        self.db_session.commit()
        
        print(f"✓ Recomputed embedding for {student.full_name}")
        return True
    
    def rematch_all_photos(self) -> Dict:
        """Re-run face matching for all photos in current session"""
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        # Get all students
        students = self.get_students(session)
        student_embeddings = []
        for student in students:
            if student.embedding:
                emb = self.face_service.load_embedding(student.embedding)
                student_embeddings.append((student.id, emb))
        
        if not student_embeddings:
            return {'updated': 0, 'matched': 0}
        
        # Get all faces
        result = self.db_session.execute(text(
            """SELECT f.id FROM faces f 
            JOIN photos p ON f.photo_id = p.id 
            WHERE p.session_id = :sid"""
        ), {"sid": session.id})
        
        face_ids = [row[0] for row in result]
        
        updated = 0
        matched = 0
        
        for face_id in face_ids:
            face = self.db_session.query(Face).get(face_id)
            if not face or not face.embedding:
                continue
            
            face_emb = self.face_service.load_embedding(face.embedding)
            match_result = self.face_service.match_face_enhanced(face_emb, student_embeddings)
            
            # Update if different
            if match_result['student_id'] != face.student_id:
                self.db_session.execute(text(
                    """UPDATE faces 
                    SET student_id = :sid, match_confidence = :conf, needs_review = :review
                    WHERE id = :fid"""
                ), {
                    "sid": match_result['student_id'],
                    "conf": match_result['confidence'],
                    "review": 1 if match_result['needs_review'] else 0,
                    "fid": face_id
                })
                updated += 1
                if match_result['student_id']:
                    matched += 1
        
        self.db_session.commit()
        
        return {'updated': updated, 'matched': matched}
    
    # ==================== SESSION MANAGEMENT (from original) ====================
    
    def create_session(self, name: str, location: str = None) -> CampSession:
        """Create a new camp session"""
        result = self.db_session.execute(text(
            "SELECT COUNT(*) FROM camp_sessions WHERE photographer_id = :pid AND payment_verified = 1"
        ), {"pid": self.current_photographer.id})
        completed_count = result.scalar()
        
        is_free = (completed_count == 0)
        
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
        """Get all sessions"""
        return self.db_session.query(CampSession).filter(
            CampSession.photographer_id == self.current_photographer.id
        ).order_by(CampSession.start_date.desc()).all()
    
    def set_active_session(self, session_id: int):
        """Set active session"""
        session = self.db_session.query(CampSession).get(session_id)
        if session:
            self.current_session = session
    
    def get_students(self, session: CampSession = None) -> List[Student]:
        """Get all students"""
        if session is None:
            session = self.get_active_session()
        
        if not session:
            return []
        
        return self.db_session.query(Student).filter(
            Student.session_id == session.id
        ).all()
    
    def search_student(self, state_code: str) -> Optional[Student]:
        """Search student by state code"""
        session = self.get_active_session()
        if not session:
            return None
        
        return self.db_session.query(Student).filter(
            Student.session_id == session.id,
            Student.state_code == state_code
        ).first()
    
    def get_student_photos(self, student: Student) -> List[Photo]:
        """Get photos containing a student"""
        result = self.db_session.execute(text(
            "SELECT photo_id FROM student_photos WHERE student_id = :sid"
        ), {"sid": student.id})
        
        photo_ids = [row[0] for row in result]
        
        if not photo_ids:
            return []
        
        return self.db_session.query(Photo).filter(Photo.id.in_(photo_ids)).all()
    
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
        """Get session statistics"""
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
    
    def import_photos(self, photo_paths: List[str], progress_callback=None) -> Dict:
        """Import photos with enhanced face detection"""
        session = self.get_active_session()
        if not session:
            raise Exception("No active session")
        
        results = {
            'processed': 0,
            'skipped': 0,
            'faces_detected': 0,
            'faces_matched': 0
        }
        
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
                
                processed_path, metadata = self.face_service.preprocess_image(
                    photo_path,
                    output_dir=f"processed_photos/session_{session.id}"
                )
                
                result = self.db_session.execute(text(
                    "SELECT id FROM photos WHERE file_hash = :hash"
                ), {"hash": metadata['file_hash']})
                
                if result.fetchone():
                    results['skipped'] += 1
                    continue
                
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
                
                result = self.db_session.execute(text(
                    "SELECT id FROM photos WHERE file_hash = :hash"
                ), {"hash": metadata['file_hash']})
                photo_id = result.scalar()
                
                faces_data = self.face_service.detect_faces_enhanced(processed_path)
                results['faces_detected'] += len(faces_data)
                
                matched_students = set()
                
                for face_data in faces_data:
                    match_result = self.face_service.match_face_enhanced(
                        face_data['embedding'],
                        student_embeddings
                    )
                    
                    bbox = face_data['bbox']
                    embedding_bytes = self.face_service.save_embedding(face_data['embedding'])
                    
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
                
                for student_id in matched_students:
                    self.db_session.execute(text(
                        "INSERT INTO student_photos (student_id, photo_id) VALUES (:sid, :pid)"
                    ), {"sid": student_id, "pid": photo_id})
                
                self.db_session.execute(text(
                    "UPDATE photos SET processed = 1, face_count = :count, processed_at = :now WHERE id = :id"
                ), {"count": len(faces_data), "now": datetime.utcnow(), "id": photo_id})
                
                self.db_session.commit()
                results['processed'] += 1
                
            except Exception as e:
                print(f"Error processing {photo_path}: {e}")
                results['skipped'] += 1
        
        return results
    
    def get_faces_needing_review(self) -> List[Face]:
        """Get faces needing review"""
        session = self.get_active_session()
        if not session:
            return []
        
        result = self.db_session.execute(text(
            """SELECT f.id FROM faces f 
            JOIN photos p ON f.photo_id = p.id 
            WHERE p.session_id = :sid AND f.needs_review = 1"""
        ), {"sid": session.id})
        
        face_ids = [row[0] for row in result]
        
        if not face_ids:
            return []
        
        return self.db_session.query(Face).filter(Face.id.in_(face_ids)).all()
    
    def confirm_match(self, face_id: int, student_id: int):
        """Confirm face match"""
        face = self.db_session.query(Face).get(face_id)
        if not face:
            return
        
        self.db_session.execute(text(
            "UPDATE faces SET student_id = :sid, needs_review = 0, manual_verified = 1 WHERE id = :fid"
        ), {"sid": student_id, "fid": face_id})
        
        result = self.db_session.execute(text(
            "SELECT id FROM student_photos WHERE student_id = :sid AND photo_id = :pid"
        ), {"sid": student_id, "pid": face.photo_id})
        
        if not result.fetchone():
            self.db_session.execute(text(
                "INSERT INTO student_photos (student_id, photo_id) VALUES (:sid, :pid)"
            ), {"sid": student_id, "pid": face.photo_id})
        
        self.db_session.commit()
    
    def close(self):
        """Close database connection"""
        self.db_session.close()


# Alias for backward compatibility
AppService = EnhancedAppService