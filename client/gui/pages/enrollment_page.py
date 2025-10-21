"""
Enhanced Student Enrollment Page - Multiple Reference Photos
Supports adding 1-5 reference photos per student for better accuracy
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFormLayout, QGroupBox, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QFrame, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap


class MultiPhotoEnrollmentPage(QWidget):
    """Enhanced enrollment page supporting multiple reference photos"""
    
    student_enrolled = Signal()
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.selected_photos = []  # List of photo paths
        self.max_photos = 5
        self.setup_ui()
    
    def setup_ui(self):
        """Setup enrollment UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Student Enrollment (Multi-Photo)")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Info banner
        info_banner = QLabel(
            "💡 Tip: Upload 2-5 clear photos of the student for best results. "
            "Different angles and lighting improve face recognition accuracy."
        )
        info_banner.setStyleSheet("""
            QLabel {
                background-color: #E3F2FD;
                color: #1976D2;
                padding: 12px;
                border-radius: 8px;
                font-size: 13px;
            }
        """)
        info_banner.setWordWrap(True)
        layout.addWidget(info_banner)
        
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
        """Create enrollment form with multi-photo support"""
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
        
        # Photo selection section
        photo_section = QGroupBox("Reference Photos (1-5 recommended)")
        photo_layout = QVBoxLayout(photo_section)
        
        # Photo grid container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(300)
        
        scroll_content = QWidget()
        self.photo_grid = QGridLayout(scroll_content)
        self.photo_grid.setSpacing(10)
        scroll.setWidget(scroll_content)
        
        photo_layout.addWidget(scroll)
        
        # Photo action buttons
        photo_buttons = QHBoxLayout()
        
        add_photo_btn = QPushButton("➕ Add Photo")
        add_photo_btn.clicked.connect(self.add_reference_photo)
        photo_buttons.addWidget(add_photo_btn)
        
        add_multiple_btn = QPushButton("📁 Add Multiple")
        add_multiple_btn.clicked.connect(self.add_multiple_photos)
        photo_buttons.addWidget(add_multiple_btn)
        
        clear_photos_btn = QPushButton("🗑 Clear All")
        clear_photos_btn.clicked.connect(self.clear_photos)
        photo_buttons.addWidget(clear_photos_btn)
        
        photo_layout.addLayout(photo_buttons)
        
        # Photo count label
        self.photo_count_label = QLabel("📷 0/5 photos selected")
        self.photo_count_label.setAlignment(Qt.AlignCenter)
        self.photo_count_label.setStyleSheet("font-weight: bold; color: #666;")
        photo_layout.addWidget(self.photo_count_label)
        
        layout.addWidget(photo_section)
        
        # Backward matching option
        self.backward_match_check = QCheckBox(
            "🔍 Match against existing photos after enrollment"
        )
        self.backward_match_check.setChecked(True)
        self.backward_match_check.setToolTip(
            "If enabled, will search for this student in already-uploaded photos"
        )
        layout.addWidget(self.backward_match_check)
        
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
            QPushButton:disabled {
                background-color: #BDC3C7;
            }
        """)
        enroll_btn.clicked.connect(self.enroll_student)
        layout.addWidget(enroll_btn)
        
        return group
    
    def add_reference_photo(self):
        """Add a single reference photo"""
        if len(self.selected_photos) >= self.max_photos:
            QMessageBox.warning(
                self,
                "Maximum Photos",
                f"You can only add up to {self.max_photos} reference photos."
            )
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Photo",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            self.selected_photos.append(file_path)
            self.update_photo_grid()
    
    def add_multiple_photos(self):
        """Add multiple reference photos at once"""
        if len(self.selected_photos) >= self.max_photos:
            QMessageBox.warning(
                self,
                "Maximum Photos",
                f"Maximum of {self.max_photos} photos already selected."
            )
            return
        
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Reference Photos",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_paths:
            remaining = self.max_photos - len(self.selected_photos)
            if len(file_paths) > remaining:
                QMessageBox.warning(
                    self,
                    "Too Many Photos",
                    f"Only adding first {remaining} photos to stay within limit."
                )
                file_paths = file_paths[:remaining]
            
            self.selected_photos.extend(file_paths)
            self.update_photo_grid()
    
    def clear_photos(self):
        """Clear all selected photos"""
        if self.selected_photos:
            reply = QMessageBox.question(
                self,
                "Clear Photos",
                "Remove all selected photos?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.selected_photos.clear()
                self.update_photo_grid()
    
    def update_photo_grid(self):
        """Update the photo preview grid"""
        # Clear existing items
        while self.photo_grid.count():
            item = self.photo_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add photo previews
        for idx, photo_path in enumerate(self.selected_photos):
            photo_widget = self.create_photo_preview(photo_path, idx)
            row = idx // 3
            col = idx % 3
            self.photo_grid.addWidget(photo_widget, row, col)
        
        # Update count label
        count = len(self.selected_photos)
        self.photo_count_label.setText(f"📷 {count}/{self.max_photos} photos selected")
        
        if count == 0:
            self.photo_count_label.setStyleSheet("font-weight: bold; color: #E74C3C;")
        elif count < 2:
            self.photo_count_label.setStyleSheet("font-weight: bold; color: #F39C12;")
        else:
            self.photo_count_label.setStyleSheet("font-weight: bold; color: #27AE60;")
    
    def create_photo_preview(self, photo_path, index):
        """Create a photo preview widget with remove button"""
        container = QFrame()
        container.setFrameStyle(QFrame.Box | QFrame.Raised)
        container.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 5px;
            }
            QFrame:hover {
                border-color: #3498DB;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Photo label
        photo_label = QLabel()
        pixmap = QPixmap(photo_path)
        scaled = pixmap.scaled(
            120, 120,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        photo_label.setPixmap(scaled)
        photo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(photo_label)
        
        # Photo number
        number_label = QLabel(f"Photo {index + 1}")
        number_label.setAlignment(Qt.AlignCenter)
        number_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        layout.addWidget(number_label)
        
        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setMaximumWidth(40)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_photo(index))
        layout.addWidget(remove_btn, alignment=Qt.AlignCenter)
        
        return container
    
    def remove_photo(self, index):
        """Remove a photo from selection"""
        if 0 <= index < len(self.selected_photos):
            self.selected_photos.pop(index)
            self.update_photo_grid()
    
    def enroll_student(self):
        """Enroll student with multiple reference photos"""
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
        
        if not self.selected_photos:
            QMessageBox.warning(
                self,
                "No Photos",
                "Please add at least one reference photo!"
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
        
        # Show progress
        progress = QMessageBox(self)
        progress.setWindowTitle("Enrolling Student")
        progress.setText(f"Processing {len(self.selected_photos)} photo(s)...\nPlease wait.")
        progress.setStandardButtons(QMessageBox.NoButton)
        progress.show()
        
        try:
            # Enroll student with multiple photos
            student = self.app_service.enroll_student_multiple_photos(
                state_code=state_code,
                full_name=full_name,
                reference_photo_paths=self.selected_photos,
                email=self.email_input.text().strip() or None,
                phone=self.phone_input.text().strip() or None,
                match_existing_photos=self.backward_match_check.isChecked()
            )
            
            progress.close()
            
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
                f"✓ Successfully enrolled {full_name}!\n\n"
                f"Reference photos used: {len(self.selected_photos)}\n"
                f"Enhanced accuracy: {'Yes' if len(self.selected_photos) > 1 else 'Single photo'}"
            )
            
            # Clear form
            self.clear_form()
            
            # Refresh list
            self.refresh()
            
            # Emit signal
            self.student_enrolled.emit()
            
        except Exception as e:
            progress.close()
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
        self.selected_photos.clear()
        self.update_photo_grid()
    
    def create_students_list(self):
        """Create enrolled students list with CRUD operations"""
        group = QGroupBox("Enrolled Students")
        layout = QVBoxLayout(group)
        
        # Search and actions bar
        top_bar = QHBoxLayout()
        
        search_input = QLineEdit()
        search_input.setPlaceholderText("🔍 Search by state code or name...")
        search_input.textChanged.connect(self.filter_students)
        top_bar.addWidget(search_input)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh list")
        refresh_btn.clicked.connect(self.refresh)
        refresh_btn.setMaximumWidth(40)
        top_bar.addWidget(refresh_btn)
        
        layout.addLayout(top_bar)
        
        # Table
        self.students_table = QTableWidget()
        self.students_table.setColumnCount(5)
        self.students_table.setHorizontalHeaderLabels([
            "State Code", "Full Name", "Photos", "Registered", "Actions"
        ])
        self.students_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.students_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.students_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.students_table)
        
        return group
    
    def refresh(self):
        """Refresh students list"""
        students = self.app_service.get_students()
        
        self.students_table.setRowCount(len(students))
        
        for row, student in enumerate(students):
            # State code
            self.students_table.setItem(row, 0, QTableWidgetItem(student.state_code))
            
            # Full name
            self.students_table.setItem(row, 1, QTableWidgetItem(student.full_name))
            
            # Photo count
            photo_count = len(student.reference_photo_path.split(',')) if student.reference_photo_path else 0
            self.students_table.setItem(row, 2, QTableWidgetItem(str(photo_count)))
            
            # Registered date
            registered = student.registered_at.strftime('%Y-%m-%d %H:%M')
            self.students_table.setItem(row, 3, QTableWidgetItem(registered))
            
            # Actions
            actions_widget = self.create_action_buttons(student)
            self.students_table.setCellWidget(row, 4, actions_widget)
    
    def create_action_buttons(self, student):
        """Create action buttons for each student row"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        
        # Add photo button
        add_btn = QPushButton("➕")
        add_btn.setToolTip("Add reference photo")
        add_btn.setMaximumWidth(30)
        add_btn.clicked.connect(lambda: self.add_student_photo(student.id))
        layout.addWidget(add_btn)
        
        # Edit button
        edit_btn = QPushButton("✏")
        edit_btn.setToolTip("Edit student info")
        edit_btn.setMaximumWidth(30)
        edit_btn.clicked.connect(lambda: self.edit_student(student.id))
        layout.addWidget(edit_btn)
        
        # Delete button
        delete_btn = QPushButton("🗑")
        delete_btn.setToolTip("Delete student")
        delete_btn.setMaximumWidth(30)
        delete_btn.setStyleSheet("QPushButton { color: red; }")
        delete_btn.clicked.connect(lambda: self.delete_student(student.id))
        layout.addWidget(delete_btn)
        
        return widget
    
    def add_student_photo(self, student_id):
        """Add additional reference photo to existing student"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Additional Reference Photo",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            try:
                success = self.app_service.add_student_reference_photo(student_id, file_path)
                if success:
                    QMessageBox.information(
                        self,
                        "Success",
                        "✓ Reference photo added successfully!\n"
                        "Student's embedding has been updated for better accuracy."
                    )
                    self.refresh()
                else:
                    QMessageBox.warning(
                        self,
                        "Failed",
                        "Failed to add reference photo. Face not detected or student not found."
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error adding photo:\n{str(e)}"
                )
    
    def edit_student(self, student_id):
        """Edit student information"""
        # This would open a dialog - simplified for now
        QMessageBox.information(
            self,
            "Edit Student",
            "Edit functionality coming soon!\n"
            "Will allow updating name, email, phone, and state code."
        )
    
    def delete_student(self, student_id):
        """Delete student"""
        reply = QMessageBox.question(
            self,
            "Delete Student",
            "Are you sure you want to delete this student?\n"
            "This will remove all their data and face matches.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                success = self.app_service.delete_student(student_id)
                if success:
                    QMessageBox.information(
                        self,
                        "Success",
                        "✓ Student deleted successfully!"
                    )
                    self.refresh()
                    self.student_enrolled.emit()  # Trigger refresh elsewhere
                else:
                    QMessageBox.warning(
                        self,
                        "Failed",
                        "Failed to delete student. Student not found."
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error deleting student:\n{str(e)}"
                )
    
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


# Missing import
from PySide6.QtWidgets import QCheckBox