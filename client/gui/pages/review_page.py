"""Review Page - Manual review of borderline matches"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QScrollArea, QFrame, QMessageBox
)
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtCore import Qt, Signal


class ReviewPage(QWidget):
    """Manual review of face matches"""
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.pending_faces = []
        self.current_index = 0
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Review Face Matches")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Status
        self.status_label = QLabel("Loading...")
        self.status_label.setFont(QFont("Arial", 14))
        layout.addWidget(self.status_label)
        
        # Review area
        review_box = self.create_review_area()
        layout.addWidget(review_box, stretch=1)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        prev_btn = QPushButton("⬅ Previous")
        prev_btn.clicked.connect(self.previous_face)
        action_layout.addWidget(prev_btn)
        
        skip_btn = QPushButton("⏭ Skip")
        skip_btn.clicked.connect(self.skip_face)
        action_layout.addWidget(skip_btn)
        
        refresh_btn = QPushButton("🔄 Refresh List")
        refresh_btn.clicked.connect(self.refresh)
        action_layout.addWidget(refresh_btn)
        
        layout.addLayout(action_layout)
    
    def create_review_area(self):
        """Create face review area"""
        group = QGroupBox("Face to Review")
        layout = QVBoxLayout(group)
        
        # Face image
        self.face_image_label = QLabel("No faces to review")
        self.face_image_label.setAlignment(Qt.AlignCenter)
        self.face_image_label.setMinimumSize(400, 400)
        self.face_image_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                border-radius: 10px;
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.face_image_label)
        
        # Match info
        self.match_info_label = QLabel()
        self.match_info_label.setAlignment(Qt.AlignCenter)
        self.match_info_label.setFont(QFont("Arial", 12))
        layout.addWidget(self.match_info_label)
        
        # Student selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Assign to student:"))
        
        self.student_combo = QComboBox()
        self.student_combo.setMinimumWidth(300)
        selector_layout.addWidget(self.student_combo, stretch=1)
        
        layout.addLayout(selector_layout)
        
        # Confirm button
        confirm_btn = QPushButton("✓ Confirm Match")
        confirm_btn.setMinimumHeight(50)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ECC71;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #27AE60;
            }
        """)
        confirm_btn.clicked.connect(self.confirm_match)
        layout.addWidget(confirm_btn)
        
        return group
    
    def refresh(self):
        """Refresh faces needing review"""
        self.pending_faces = self.app_service.get_faces_needing_review()
        self.current_index = 0
        
        # Update status
        if self.pending_faces:
            self.status_label.setText(
                f"📋 {len(self.pending_faces)} face(s) need review"
            )
            self.load_students()
            self.show_current_face()
        else:
            self.status_label.setText("✓ No faces need review - All done!")
            self.face_image_label.setText("✓ All faces have been reviewed!")
            self.match_info_label.setText("")
            self.student_combo.clear()
    
    def load_students(self):
        """Load students into combo box"""
        self.student_combo.clear()
        students = self.app_service.get_students()
        
        for student in students:
            self.student_combo.addItem(
                f"{student.full_name} ({student.state_code})",
                student.id
            )
    
    def show_current_face(self):
        """Show current face for review"""
        if not self.pending_faces or self.current_index >= len(self.pending_faces):
            self.refresh()
            return
        
        from models import Photo
        face = self.pending_faces[self.current_index]
        photo = self.app_service.db_session.query(Photo).get(face.photo_id)
        
        if not photo:
            self.next_face()
            return
        
        # Load and display photo
        try:
            pixmap = QPixmap(photo.thumbnail_path or photo.original_path)
            
            # Crop to face bbox if available
            if face.bbox_x and face.bbox_y:
                rect = pixmap.rect()
                x = max(0, face.bbox_x - 20)
                y = max(0, face.bbox_y - 20)
                w = min(face.bbox_width + 40, rect.width() - x)
                h = min(face.bbox_height + 40, rect.height() - y)
                
                pixmap = pixmap.copy(x, y, w, h)
            
            scaled = pixmap.scaled(
                380, 380,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.face_image_label.setPixmap(scaled)
            
            # Show match info
            if face.student_id:
                from models import Student
                student = self.app_service.db_session.query(Student).get(face.student_id)
                match_text = f"Suggested match: {student.full_name}\n"
            else:
                match_text = "No match found\n"
            
            match_text += f"Confidence: {face.match_confidence:.3f}\n"
            match_text += f"Face #{self.current_index + 1} of {len(self.pending_faces)}"
            
            self.match_info_label.setText(match_text)
            
            # Select suggested student in combo
            if face.student_id:
                for i in range(self.student_combo.count()):
                    if self.student_combo.itemData(i) == face.student_id:
                        self.student_combo.setCurrentIndex(i)
                        break
        
        except Exception as e:
            self.face_image_label.setText(f"Error loading image:\n{str(e)}")
    
    def confirm_match(self):
        """Confirm the current match"""
        if not self.pending_faces:
            return
        
        face = self.pending_faces[self.current_index]
        student_id = self.student_combo.currentData()
        
        if not student_id:
            QMessageBox.warning(
                self,
                "No Student Selected",
                "Please select a student to assign this face to!"
            )
            return
        
        # Confirm match in database
        self.app_service.confirm_match(face.id, student_id)
        
        # Move to next
        self.next_face()
    
    def next_face(self):
        """Move to next face"""
        self.current_index += 1
        if self.current_index >= len(self.pending_faces):
            self.refresh()
        else:
            self.show_current_face()
    
    def previous_face(self):
        """Move to previous face"""
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_face()
    
    def skip_face(self):
        """Skip current face without confirming"""
        self.next_face()

