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
                license_valid_until=datetime.utcnow() + timedelta(days=30)
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
        Computes and stores embedding.
        Also checks for face duplication in existing database.
        """
        print(f"\n→ Enrolling student: {full_name} ({state_code})")

        # Check if student already exists in this session
        existing = self.db_session.query(Student).filter_by(
            session_id=session.id,
            state_code=state_code
        ).first()

        if existing:
            print(f" ⚠ Student {state_code} already enrolled.")
            return existing

        # Compute embedding
        print(f" → Computing embedding from {reference_photo_path}...")
        embedding = self.face_service.compute_embedding(reference_photo_path)

        if embedding is None:
            print(f" ✗ Failed to detect face in reference photo")
            return None

        # 🔍 Compare new embedding against all existing ones to prevent duplicate registration
        print(" → Checking for similar faces in existing database...")
        all_students = self.db_session.query(Student).filter(Student.embedding != None).all()
        for s in all_students:
            emb = self.face_service.load_embedding(s.embedding)
            similarity = self.face_service.compare_embeddings(embedding, emb)
            if similarity > 0.75:  # adjustable threshold
                print(f" ⚠ Possible duplicate: {s.full_name} ({s.state_code}) — similarity: {similarity:.3f}")
                break
        else:
            print(" ✓ No similar face found. Proceeding with enrollment...")

        # Save embedding as bytes
        embedding_bytes = self.face_service.save_embedding(embedding)

        student = Student(
            session_id=session.id,
            state_code=state_code,
            full_name=full_name,
            email=email,
            phone=phone,
            reference_photo_path=reference_photo_path,
            embedding=embedding_bytes,
            embedding_model=getattr(self.face_service, "model_name", "unknown")
        )

        self.db_session.add(student)
        self.db_session.commit()

        # Update session count
        session.student_count += 1
        self.db_session.commit()

        print(f" ✓ Enrolled {full_name} (ID: {student.id})")
        return student

    def process_photo(self, session: CampSession, photo_path: str):
        """Process a single photo"""
        print(f"\n→ Processing photo: {os.path.basename(photo_path)}")

        processed_path, metadata = self.face_service.preprocess_image(
            photo_path,
            output_dir=f"processed_photos/session_{session.id}"
        )

        existing = self.db_session.query(Photo).filter_by(
            file_hash=metadata['file_hash']
        ).first()
        if existing:
            print(f" ⚠ Photo already processed (duplicate)")
            return

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

        students = self.db_session.query(Student).filter_by(session_id=session.id).all()
        student_embeddings = [
            (s.id, self.face_service.load_embedding(s.embedding))
            for s in students if s.embedding
        ]

        print(f" → Matching against {len(student_embeddings)} enrolled student(s)...")
        matched_students = set()

        for face_data in faces_data:
            face_embedding = face_data['embedding']
            bbox = face_data['bbox']

            match_result = self.face_service.match_face(face_embedding, student_embeddings)

            face = Face(
                photo_id=photo.id,
                student_id=match_result['student_id'],
                bbox_x=bbox[0],
                bbox_y=bbox[1],
                bbox_width=bbox[2],
                bbox_height=bbox[3],
                confidence=face_data['confidence'],
                embedding=self.face_service.save_embedding(face_embedding),
                embedding_model=getattr(self.face_service, "model_name", "unknown"),
                match_confidence=match_result['confidence'],
                needs_review=match_result['needs_review']
            )
            self.db_session.add(face)

            if match_result['student_id']:
                matched_students.add(match_result['student_id'])
                student = self.db_session.query(Student).get(match_result['student_id'])
                status = "⚠ NEEDS REVIEW" if match_result['needs_review'] else "✓"
                print(f" {status} Matched to {student.full_name} ({student.state_code}) - confidence: {match_result['confidence']:.3f}")

        for sid in matched_students:
            self.db_session.add(StudentPhoto(student_id=sid, photo_id=photo.id))

        photo.processed = True
        photo.face_count = len(faces_data)
        photo.processed_at = datetime.utcnow()
        self.db_session.commit()

        print(f" ✓ Photo processed: {len(matched_students)} student(s) matched")

    def process_photo_batch(self, session: CampSession, photo_dir: str):
        """Process all photos in a directory"""
        print(f"\n{'='*60}")
        print(f"BATCH PROCESSING: {photo_dir}")
        print(f"{'='*60}")

        valid_ext = {'.jpg', '.jpeg', '.png'}
        photo_files = [
            os.path.join(photo_dir, f)
            for f in os.listdir(photo_dir)
            if os.path.splitext(f.lower())[1] in valid_ext
        ]

        print(f"Found {len(photo_files)} photo(s)\n")

        for idx, path in enumerate(photo_files, 1):
            print(f"[{idx}/{len(photo_files)}]")
            try:
                self.process_photo(session, path)
            except Exception as e:
                print(f" ✗ Error processing {path}: {e}")

    def print_session_summary(self, session: CampSession):
        """Print summary of session"""
        students = self.db_session.query(Student).filter_by(session_id=session.id).all()
        photos = self.db_session.query(Photo).filter_by(session_id=session.id).all()
        total_faces = sum(p.face_count for p in photos)

        print(f"\n{'='*60}")
        print(f"SESSION SUMMARY: {session.name}")
        print(f"{'='*60}")
        print(f"Students enrolled: {len(students)}")
        print(f"Photos processed: {len(photos)}")
        print(f"Total faces detected: {total_faces}\n")

        for s in students:
            count = len(self.db_session.query(StudentPhoto).filter_by(student_id=s.id).all())
            print(f" {s.full_name} ({s.state_code}): {count} photo(s)")

        print(f"{'='*60}\n")


def main():
    """Demo workflow"""
    print("\n" + "="*60)
    print("NYSC PHOTO APP - CLI PROTOTYPE")
    print("="*60 + "\n")

    app = PhotoSorterCli('sqlite:///demo_NYSC.db')

    photographer = app.create_photographer("John Photographer", "john@example.com", "+2348012345678")
    session = app.create_session(photographer, "Summer Camp 2025", "Lagos", True)

    app.enroll_student(session, "LAG001", "Moses Oghene", "C:/Users/oloko/Desktop/Image_sorter/images/20250801_133801.jpg")
    # app.enroll_student(session, "LAG002", "Iyang Jush", "C:/Users/oloko/Desktop/Image_sorter/images/20250805_154446.jpg")

    app.process_photo(session, "C:/Users/oloko/Desktop/Image_sorter/images/20250801_133801.jpg")
    app.process_photo_batch(session, "C:/Users/oloko/Desktop/Image_sorter/images")

    app.print_session_summary(session)
    print("\n✓ Demo complete!\n")


if __name__ == '__main__':
    main()
