"""
Enhanced Application Service with Peewee ORM
- Multiple reference photos per student
- Backward matching (match new students against existing photos)
- CRUD operations for student embeddings
"""
import os
import numpy as np 
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from peewee import fn

from models import (
    db, init_db, Photographer, CampSession, Student, 
    Photo, Face, StudentPhoto
)
from face_service import EnhancedFaceService as FaceService


class EnhancedAppService:
    """Enhanced application service with backward matching"""
    
    def __init__(self, db_path='photos_sorter.db'):
        self.db = init_db(db_path)
        self.face_service = FaceService()
        self.current_photographer = None
        self.current_session = None
        self.viewing_session = None 
        
        self._init_photographer()
    

    def set_viewing_session(self, session_id: int):
        """Set which session to VIEW (doesn't affect operations)"""
        session = CampSession.get_or_none(CampSession.id == session_id)
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
            session = self.get_viewing_session()
        
        if not session:
            return []
        
        return list(Student.select().where(Student.session == session))
    
    def get_session_stats(self, session_id: int = None) -> Dict:
        """Get stats for specific session or viewing session"""
        if session_id:
            session = CampSession.get_or_none(CampSession.id == session_id)
        else:
            session = self.get_viewing_session()
        
        if not session:
            return {}
        
        cursor = db.execute_sql("""
            SELECT 
                (SELECT COUNT(*) FROM students WHERE session_id = ?) as students,
                (SELECT COUNT(*) FROM photos WHERE session_id = ?) as photos,
                (SELECT COALESCE(SUM(face_count), 0) FROM photos WHERE session_id = ?) as total_faces,
                (SELECT COUNT(*) FROM faces f JOIN photos p ON f.photo_id = p.id 
                 WHERE p.session_id = ? AND f.student_id IS NOT NULL) as matched,
                (SELECT COUNT(*) FROM faces f JOIN photos p ON f.photo_id = p.id 
                 WHERE p.session_id = ? AND f.needs_review = 1) as review
        """, (session.id, session.id, session.id, session.id, session.id))
        
        row = cursor.fetchone()
        
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
        photographer = Photographer.select().first()
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
        existing = Student.select().where(
            (Student.session == session) &
            (Student.state_code == state_code)
        ).first()
        
        if existing:
            return None  # Already enrolled
        
        # Compute embeddings from all reference photos
        embeddings = []
        successful_paths = []
        
        print(f"\n- Computing embeddings from {len(reference_photo_paths)} photo(s)...")
        for path in reference_photo_paths:
            emb = self.face_service.compute_embedding(path)
            if emb is not None:
                embeddings.append(emb)
                successful_paths.append(path)
                print(f"   {os.path.basename(path)}")
            else:
                print(f"   Failed: {os.path.basename(path)}")
        
        if not embeddings:
            raise Exception("Could not detect face in any reference photo")
        
        # Average the embeddings
        avg_embedding = self.face_service.compute_average_embedding(successful_paths)
        
        # Store all reference paths as comma-separated
        all_paths = ",".join(successful_paths)
        
        # Insert student
        embedding_bytes = self.face_service.save_embedding(avg_embedding)
        
        student = Student.create(
            session=session,
            state_code=state_code,
            full_name=full_name,
            email=email,
            phone=phone,
            reference_photo_path=all_paths,
            embedding=embedding_bytes,
            embedding_model=self.face_service.model_name,
            registered_at=datetime.utcnow()
        )
        
        # Update session count
        session.student_count += 1
        session.save()
        
        # BACKWARD MATCHING: Match this new student against existing photos
        if match_existing_photos and student:
            print(f"\n- Checking existing photos for matches with {full_name}...")
            matches_found = self._backward_match_student(student)
            if matches_found > 0:
                print(f"   Found {matches_found} existing photo(s) with {full_name}!")
        
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
        photos = list(Photo.select().where(
            (Photo.session == session) &
            (Photo.processed == True)
        ))
        
        matches_found = 0
        
        for photo in photos:
            # Get unmatched faces in this photo
            faces = list(Face.select().where(
                (Face.photo == photo) &
                (Face.student.is_null())
            ))
            
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
                    face.student = student
                    face.match_confidence = match_result['confidence']
                    face.needs_review = match_result['needs_review']
                    face.save()
                    
                    # Create student-photo association
                    existing_sp = StudentPhoto.select().where(
                        (StudentPhoto.student == student) &
                        (StudentPhoto.photo == photo)
                    ).first()
                    
                    if not existing_sp:
                        StudentPhoto.create(student=student, photo=photo)
                    
                    matches_found += 1
                    status = "REVIEW" if match_result['needs_review'] else ""
                    print(f"  {status} Matched in {os.path.basename(photo.original_path)} "
                          f"(confidence: {match_result['confidence']:.3f})")
        
        return matches_found
    
    # ==================== CRUD OPERATIONS ====================
    
    def add_student_reference_photo(self, student_id: int, photo_path: str) -> bool:
        """Add an additional reference photo to improve student's embedding"""
        student = Student.get_or_none(Student.id == student_id)
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
        
        student.embedding = embedding_bytes
        student.reference_photo_path = new_paths
        student.save()
        
        print(f" Added reference photo for {student.full_name}")
        return True
    
    def update_student_info(self, student_id: int, **kwargs) -> bool:
        """Update student information (name, email, phone, etc.)"""
        student = Student.get_or_none(Student.id == student_id)
        if not student:
            return False
        
        allowed_fields = ['full_name', 'email', 'phone', 'state_code']
        updated = False
        
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                setattr(student, field, value)
                updated = True
        
        if updated:
            student.save()
        
        return updated
    
    def delete_student(self, student_id: int) -> bool:
        """Delete a student and all associated data"""
        student = Student.get_or_none(Student.id == student_id)
        if not student:
            return False
        
        session = self.get_active_session()
        
        # Delete associated records (cascade should handle, but being explicit)
        StudentPhoto.delete().where(StudentPhoto.student == student).execute()
        Face.update(student=None).where(Face.student == student).execute()
        
        # Delete student
        student.delete_instance()
        
        # Update session count
        if session:
            session.student_count = max(0, session.student_count - 1)
            session.save()
        
        return True
    
    def recompute_student_embedding(self, student_id: int) -> bool:
        """Recompute embedding from all reference photos"""
        student = Student.get_or_none(Student.id == student_id)
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
        student.embedding = embedding_bytes
        student.save()
        
        print(f" Recomputed embedding for {student.full_name}")
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
        faces = list(Face.select().join(Photo).where(Photo.session == session))
        
        updated = 0
        matched = 0
        
        for face in faces:
            if not face.embedding:
                continue
            
            face_emb = self.face_service.load_embedding(face.embedding)
            match_result = self.face_service.match_face_enhanced(face_emb, student_embeddings)
            
            # Update if different
            current_student_id = face.student.id if face.student else None
            if match_result['student_id'] != current_student_id:
                if match_result['student_id']:
                    face.student = Student.get_by_id(match_result['student_id'])
                else:
                    face.student = None
                face.match_confidence = match_result['confidence']
                face.needs_review = match_result['needs_review']
                face.save()
                
                updated += 1
                if match_result['student_id']:
                    matched += 1
        
        return {'updated': updated, 'matched': matched}
    
    # ==================== SESSION MANAGEMENT ====================
    
    def create_session(self, name: str, location: str = None) -> CampSession:
        """Create a new camp session"""
        completed_count = CampSession.select().where(
            (CampSession.photographer == self.current_photographer) &
            (CampSession.payment_verified == True)
        ).count()
        
        is_free = (completed_count == 0)
        
        session = CampSession.create(
            photographer=self.current_photographer,
            name=name,
            location=location,
            is_free_trial=is_free,
            is_active=True,
            student_count=0,
            start_date=datetime.utcnow(),
            amount_due=0.0,
            payment_verified=False
        )
        
        self.current_session = session
        return session
    
    def get_active_session(self) -> Optional[CampSession]:
        """Get the current active session"""
        if self.current_session and self.current_session.is_active:
            return self.current_session
        
        session = CampSession.select().where(
            (CampSession.photographer == self.current_photographer) &
            (CampSession.is_active == True)
        ).first()
        
        self.current_session = session
        return session
    
    def get_all_sessions(self) -> List[CampSession]:
        """Get all sessions"""
        return list(CampSession.select().where(
            CampSession.photographer == self.current_photographer
        ).order_by(CampSession.start_date.desc()))
    
    def set_active_session(self, session_id: int):
        """Set active session"""
        session = CampSession.get_or_none(CampSession.id == session_id)
        if session:
            self.current_session = session
    
    def search_student(self, state_code: str) -> Optional[Student]:
        """Search student by state code"""
        session = self.get_active_session()
        if not session:
            return None
        
        return Student.select().where(
            (Student.session == session) &
            (Student.state_code == state_code)
        ).first()
    
    def get_student_photos(self, student: Student) -> List[Photo]:
        """Get photos containing a student"""
        try:
            # Query StudentPhoto table directly to avoid backref issues
            student_photo_records = list(StudentPhoto.select().where(
                StudentPhoto.student == student
            ))
            
            if not student_photo_records:
                print(f"[DEBUG] No student_photo records found for student {student.id}")
                return []
            
            photo_ids = [sp.photo_id for sp in student_photo_records]
            print(f"[DEBUG] Found {len(photo_ids)} photo IDs for student {student.id}: {photo_ids}")
            
            photos = list(Photo.select().where(Photo.id.in_(photo_ids)))
            print(f"[DEBUG] Retrieved {len(photos)} photo objects")
            return photos
        except Exception as e:
            print(f"[ERROR] get_student_photos failed: {e}")
            import traceback
            traceback.print_exc()
            return []
    
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
                
                # Check if already exists
                existing = Photo.select().where(
                    Photo.file_hash == metadata['file_hash']
                ).first()
                
                if existing:
                    results['skipped'] += 1
                    continue
                
                # Create photo record
                photo = Photo.create(
                    session=session,
                    original_path=photo_path,
                    thumbnail_path=processed_path,
                    file_hash=metadata['file_hash'],
                    file_size=metadata['original_size'],
                    width=metadata['width'],
                    height=metadata['height'],
                    processed=False,
                    face_count=0,
                    uploaded_at=datetime.utcnow()
                )
                
                # Detect faces
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
                    
                    student_obj = None
                    if match_result['student_id']:
                        student_obj = Student.get_by_id(match_result['student_id'])
                    
                    Face.create(
                        photo=photo,
                        student=student_obj,
                        bbox_x=bbox[0],
                        bbox_y=bbox[1],
                        bbox_width=bbox[2],
                        bbox_height=bbox[3],
                        confidence=face_data['confidence'],
                        embedding=embedding_bytes,
                        embedding_model=self.face_service.model_name,
                        match_confidence=match_result['confidence'],
                        needs_review=match_result['needs_review'],
                        detected_at=datetime.utcnow()
                    )
                    
                    if match_result['student_id']:
                        matched_students.add(match_result['student_id'])
                        results['faces_matched'] += 1
                
                # Create student-photo associations
                for student_id in matched_students:
                    student_obj = Student.get_by_id(student_id)
                    StudentPhoto.create(student=student_obj, photo=photo)
                
                # Update photo
                photo.processed = True
                photo.face_count = len(faces_data)
                photo.processed_at = datetime.utcnow()
                photo.save()
                
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
        
        return list(Face.select().join(Photo).where(
            (Photo.session == session) &
            (Face.needs_review == True)
        ))
    
    def confirm_match(self, face_id: int, student_id: int):
        """Confirm face match"""
        face = Face.get_or_none(Face.id == face_id)
        if not face:
            return
        
        student = Student.get_by_id(student_id)
        face.student = student
        face.needs_review = False
        face.manual_verified = True
        face.save()
        
        # Create student-photo association if not exists
        existing = StudentPhoto.select().where(
            (StudentPhoto.student == student) &
            (StudentPhoto.photo == face.photo)
        ).first()
        
        if not existing:
            StudentPhoto.create(student=student, photo=face.photo)
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'db') and self.db and not self.db.is_closed():
            self.db.close()


# Alias for backward compatibility
AppService = EnhancedAppService