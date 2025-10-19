"""
CLI Prototype for NYSC Photo App
Demonstrates enrollment, face detection, and auto-matching workflow
"""
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as DBSession
from models import (
    init_db, Photographer, CampSession, Student, Photo, Face, StudentPhoto
)
from face_service import FaceService


class PhotoSorterCli:
    """Main application logic"""
    
    def __init__(self, db_path='sqlite:///NYSC_photos.db'):
        self.engine, SessionMaker = init_db(db_path)
        self.db_session = SessionMaker()
        self.face_service = FaceService()
        print(f"✓ App initialized with database: {db_path}")
    
    def create_photographer(self, name: str, email: str, phone: str = None) -> Photographer:
        """Create or get photographer"""
        photographer = self.db_session.query(Photographer).filter_by(email=email).first()
        
        if not photographer:
            photographer = Photographer(
                name=name,
                email=email,
                phone=phone,
                license_valid_until=datetime.utcnow() + timedelta(days=30) # 30-day trial
            )
            self.db_session.add(photographer)
            self.db_session.commit()
            print(f"✓ Created photographer: {name} ({email})")
        else:
            print(f"✓ Found existing photographer: {name}")
        
        return photographer
    
    def create_session(self, photographer: Photographer, name: str, location: str = None, is_free: bool = True) -> CampSession:
        """Create a new camp session"""
        session = CampSession(
            photographer_id=photographer.id,
            name=name,
            location=location,
            is_free_trial=is_free,
            start_date=datetime.utcnow()
        )
        self.db_session.add(session)
        self.db_session.commit()
        print(f"✓ Created session: {name} (ID: {session.id})")
        return session
    
    def enroll_student(self, session: CampSession, state_code: str, full_name: str, 
                      reference_photo_path: str, email: str = None, phone: str = None) -> Student:
        """
        Enroll a new student with reference photo
        Computes and stores embedding
        """
        print(f"/n→ Enrolling student: {full_name} ({state_code})")
        
        # Check if student already exists in this session
        existing = self.db_session.query(Student).filter_by(
            session_id=session.id,
            state_code=state_code
        ).first()
        
        if existing:
            print(f" ⚠ Student {state_code} already enrolled")
            return existing
        
        # Compute embedding from reference photo
        print(f" → Computing embedding from {reference_photo_path}...")
        embedding = self.face_service.compute_embedding(reference_photo_path)
        
        if embedding is None:
            print(f" ✗ Failed to detect face in reference photo")
            return None
        
        # Store embedding as bytes
        embedding_bytes = self.face_service.save_embedding(embedding)
        
        # Create student record
        student = Student(
            session_id=session.id,
            state_code=state_code,
            full_name=full_name,
            email=email,
            phone=phone,
            reference_photo_path=reference_photo_path,
            embedding=embedding_bytes,
            embedding_model=self.face_service.model_name
        )
        
        self.db_session.add(student)
        self.db_session.commit()
        
        # Update session student count
        session.student_count += 1
        self.db_session.commit()
        
        print(f" ✓ Enrolled {full_name} (ID: {student.id})")
        return student
    
    def process_photo(self, session: CampSession, photo_path: str):
        """
        Process a single photo:
        1. Preprocess and store metadata
        2. Detect all faces
        3. Match faces to enrolled students
        4. Create associations
        """
        print(f"/n→ Processing photo: {os.path.basename(photo_path)}")
        
        # Preprocess
        processed_path, metadata = self.face_service.preprocess_image(
            photo_path, 
            output_dir=f"processed_photos/session_{session.id}"
        )
        
        # Check for duplicate
        existing = self.db_session.query(Photo).filter_by(
            file_hash=metadata['file_hash']
        ).first()
        
        if existing:
            print(f" ⚠ Photo already processed (duplicate)")
            return
        
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
        self.db_session.commit()
        
        # Detect faces
        print(f" → Detecting faces...")
        faces_data = self.face_service.detect_faces(processed_path)
        print(f" ✓ Found {len(faces_data)} face(s)")
        
        if not faces_data:
            photo.processed = True
            photo.face_count = 0
            self.db_session.commit()
            return
        
        # Get all enrolled students for matching
        students = self.db_session.query(Student).filter_by(session_id=session.id).all()
        student_embeddings = []
        
        for student in students:
            if student.embedding:
                emb = self.face_service.load_embedding(student.embedding)
                student_embeddings.append((student.id, emb))
        
        print(f" → Matching against {len(student_embeddings)} enrolled student(s)...")
        
        matched_students = set()
        
        # Match each detected face
        for face_data in faces_data:
            face_embedding = face_data['embedding']
            bbox = face_data['bbox']
            
            # Match to student
            match_result = self.face_service.match_face(face_embedding, student_embeddings)
            
            # Store face record
            face = Face(
                photo_id=photo.id,
                student_id=match_result['student_id'],
                bbox_x=bbox[0],
                bbox_y=bbox[1],
                bbox_width=bbox[2],
                bbox_height=bbox[3],
                confidence=face_data['confidence'],
                embedding=self.face_service.save_embedding(face_embedding),
                embedding_model=self.face_service.model_name,
                match_confidence=match_result['confidence'],
                needs_review=match_result['needs_review']
            )
            self.db_session.add(face)
            
            # Create student-photo association if matched
            if match_result['student_id']:
                matched_students.add(match_result['student_id'])
                
                student = self.db_session.query(Student).get(match_result['student_id'])
                status = "⚠ NEEDS REVIEW" if match_result['needs_review'] else "✓"
                print(f" {status} Matched to {student.full_name} ({student.state_code}) - confidence: {match_result['confidence']:.3f}")
        
        # Create StudentPhoto associations
        for student_id in matched_students:
            student_photo = StudentPhoto(
                student_id=student_id,
                photo_id=photo.id
            )
            self.db_session.add(student_photo)
        
        # Update photo status
        photo.processed = True
        photo.face_count = len(faces_data)
        photo.processed_at = datetime.utcnow()
        self.db_session.commit()
        
        print(f" ✓ Photo processed: {len(matched_students)} student(s) matched")
    
    def process_photo_batch(self, session: CampSession, photo_dir: str):
        """Process all photos in a directory"""
        print(f"/n{'='*60}")
        print(f"BATCH PROCESSING: {photo_dir}")
        print(f"{'='*60}")
        
        valid_extensions = {'.jpg', '.jpeg', '.png'}
        photo_files = [
            os.path.join(photo_dir, f) 
            for f in os.listdir(photo_dir) 
            if os.path.splitext(f.lower())[1] in valid_extensions
        ]
        
        print(f"Found {len(photo_files)} photo(s)/n")
        
        for idx, photo_path in enumerate(photo_files, 1):
            print(f"[{idx}/{len(photo_files)}]")
            try:
                self.process_photo(session, photo_path)
            except Exception as e:
                print(f" ✗ Error processing {photo_path}: {e}")
    
    def get_student_photos(self, student: Student) -> list:
        """Get all photos for a student"""
        return self.db_session.query(Photo).join(StudentPhoto).filter(
            StudentPhoto.student_id == student.id
        ).all()
    
    def print_session_summary(self, session: CampSession):
        """Print summary of session"""
        students = self.db_session.query(Student).filter_by(session_id=session.id).all()
        photos = self.db_session.query(Photo).filter_by(session_id=session.id).all()
        total_faces = sum(p.face_count for p in photos)
        
        print(f"/n{'='*60}")
        print(f"SESSION SUMMARY: {session.name}")
        print(f"{'='*60}")
        print(f"Students enrolled: {len(students)}")
        print(f"Photos processed: {len(photos)}")
        print(f"Total faces detected: {total_faces}")
        print()
        
        for student in students:
            student_photos = self.get_student_photos(student)
            print(f" {student.full_name} ({student.state_code}): {len(student_photos)} photo(s)")
        
        print(f"{'='*60}/n")


def main():
    """Demo workflow"""
    print("/n" + "="*60)
    print("NYSC PHOTO APP - CLI PROTOTYPE")
    print("="*60 + "/n")
    
    # Initialize app
    app = PhotoSorterCli('sqlite:///demo_NYSC.db')
    
    # Create photographer
    photographer = app.create_photographer(
        name="John Photographer",
        email="john@example.com",
        phone="+2348012345678"
    )
    
    # Create session
    session = app.create_session(
        photographer=photographer,
        name="Summer Camp 2025",
        location="Lagos",
        is_free=True
    )
    
    app.enroll_student(session, "LAG001", "moses oghene", "C:/Users/oloko/Desktop/Image_sorter/images/20250801_133801.jpg")
    # app.enroll_student(session, "LAG002", "iyang jush", "C:/Users/oloko/Desktop/Image_sorter/images/20250805_154446.jpg")
    # app.enroll_student(session, "LAG03", "jerry miles", "C:/Users/oloko/Desktop/Image_sorter/images/20250804_134212.jpg")

    # Simulate processing photos
    app.process_photo(session, "C:/Users/oloko/Desktop/Image_sorter/images/20250801_133801.jpg")
    # app.process_photo(session, "C:/Users/oloko/Desktop/Image_sorter/images/20250805_154446.jpg")
    # app.process_photo(session, "C:/Users/oloko/Desktop/Image_sorter/images/20250804_134212.jpg")

    app.process_photo_batch(session, "C:/Users/oloko/Desktop/Image_sorter/images")
    
    # Show summary
    app.print_session_summary(session)
    
    print("/n✓ Demo setup complete!")
    print("/nNext steps:")
    print("1. Add reference photos to enroll students")
    print("2. Process photos from the event")
    print("3. Review matches and associations")
    print("/nDatabase: demo_NYSC.db/n")


if __name__ == '__main__':
    main()
