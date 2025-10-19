"""
Student Enrollment Page - Register students with reference photos
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFormLayout, QGroupBox, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap


class EnrollmentPage(QWidget):
    """Page for enrolling students"""
    
    student_enrolled = Signal()
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.selected_photo = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup enrollment UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Student Enrollment")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Main content in horizontal layout
        content_layout = QHBoxLayout()
        
        # Left: Enrollment form
        form_box = self.create_enrollment_form()
        content_layout.addWidget(form_box, stretch=2)
        
        # Right: Enrolled students list
        list_box = self.create_students_list()
        content_layout.addWidget(list_box, stretch=3)
        
        layout.addLayout(content_layout)
    
    def create_enrollment_form(self):
        """Create enrollment form"""
        group = QGroupBox("Enroll New Student")
        layout = QVBoxLayout(group)
        
        # Form inputs
        form_layout = QFormLayout()
        
        self.state_code_input = QLineEdit()
        self.state_code_input.setPlaceholderText("e.g., LAG001")
        
        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("Full name")
        
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("student@example.com")
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+234...")
        
        form_layout.addRow("State Code:*", self.state_code_input)
        form_layout.addRow("Full Name:*", self.full_name_input)
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Phone:", self.phone_input)
        
        layout.addLayout(form_layout)
        
        # Photo selection
        photo_layout = QVBoxLayout()
        
        self.photo_preview = QLabel("No photo selected")
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setMinimumSize(200, 200)
        self.photo_preview.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #f5f5f5;
            }
        """)
        photo_layout.addWidget(self.photo_preview)
        
        select_photo_btn = QPushButton("📷 Select Reference Photo")
        select_photo_btn.clicked.connect(self.select_reference_photo)
        photo_layout.addWidget(select_photo_btn)
        
        layout.addLayout(photo_layout)
        
        # Enroll button
        enroll_btn = QPushButton("✓ Enroll Student")
        enroll_btn.setMinimumHeight(50)
        enroll_btn.setStyleSheet("""
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
        enroll_btn.clicked.connect(self.enroll_student)
        layout.addWidget(enroll_btn)
        
        return group
    
    def create_students_list(self):
        """Create enrolled students list"""
        group = QGroupBox("Enrolled Students")
        layout = QVBoxLayout(group)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_input = QLineEdit()
        search_input.setPlaceholderText("🔍 Search by state code or name...")
        search_input.textChanged.connect(self.filter_students)
        search_layout.addWidget(search_input)
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh)
        search_layout.addWidget(refresh_btn)
        
        layout.addLayout(search_layout)
        
        # Table
        self.students_table = QTableWidget()
        self.students_table.setColumnCount(4)
        self.students_table.setHorizontalHeaderLabels([
            "State Code", "Full Name", "Contact", "Registered"
        ])
        self.students_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.students_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.students_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.students_table)
        
        return group
    
    def select_reference_photo(self):
        """Open file dialog to select reference photo"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Photo",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            self.selected_photo = file_path
            
            # Show preview
            pixmap = QPixmap(file_path)
            scaled = pixmap.scaled(
                200, 200,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.photo_preview.setPixmap(scaled)
    
    def enroll_student(self):
        """Enroll a new student"""
        # Validate inputs
        state_code = self.state_code_input.text().strip()
        full_name = self.full_name_input.text().strip()
        
        if not state_code or not full_name:
            QMessageBox.warning(
                self,
                "Validation Error",
                "State Code and Full Name are required!"
            )
            return
        
        if not self.selected_photo:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please select a reference photo!"
            )
            return
        
        # Check for active session
        if not self.app_service.get_active_session():
            QMessageBox.warning(
                self,
                "No Active Session",
                "Please create or select an active session first!"
            )
            return
        
        try:
            # Enroll student
            student = self.app_service.enroll_student(
                state_code=state_code,
                full_name=full_name,
                reference_photo_path=self.selected_photo,
                email=self.email_input.text().strip() or None,
                phone=self.phone_input.text().strip() or None
            )
            
            if student is None:
                QMessageBox.warning(
                    self,
                    "Duplicate Student",
                    f"Student with state code '{state_code}' is already enrolled!"
                )
                return
            
            # Success
            QMessageBox.information(
                self,
                "Success",
                f"✓ Successfully enrolled {full_name}!"
            )
            
            # Clear form
            self.clear_form()
            
            # Refresh list
            self.refresh()
            
            # Emit signal
            self.student_enrolled.emit()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Enrollment Error",
                f"Failed to enroll student:\n{str(e)}"
            )
    
    def clear_form(self):
        """Clear enrollment form"""
        self.state_code_input.clear()
        self.full_name_input.clear()
        self.email_input.clear()
        self.phone_input.clear()
        self.selected_photo = None
        self.photo_preview.clear()
        self.photo_preview.setText("No photo selected")
    
    def refresh(self):
        """Refresh students list"""
        students = self.app_service.get_students()
        
        self.students_table.setRowCount(len(students))
        
        for row, student in enumerate(students):
            self.students_table.setItem(row, 0, QTableWidgetItem(student.state_code))
            self.students_table.setItem(row, 1, QTableWidgetItem(student.full_name))
            
            contact = student.email or student.phone or "-"
            self.students_table.setItem(row, 2, QTableWidgetItem(contact))
            
            registered = student.registered_at.strftime('%Y-%m-%d %H:%M')
            self.students_table.setItem(row, 3, QTableWidgetItem(registered))
    
    def filter_students(self, text):
        """Filter students table by search text"""
        for row in range(self.students_table.rowCount()):
            match = False
            for col in range(2):  # Search in state code and name columns
                item = self.students_table.item(row, col)
                if item and text.lower() in item.text().lower():
                    match = True
                    break
            self.students_table.setRowHidden(row, not match)