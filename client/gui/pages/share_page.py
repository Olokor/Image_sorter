"""
Share Page - Generate QR codes for student photo access
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QFormLayout, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap, QImage
import qrcode
from io import BytesIO


class SharePage(QWidget):
    """Page for generating QR codes and sharing photos"""
    
    def __init__(self, app_service, local_server):
        super().__init__()
        self.app_service = app_service
        self.local_server = local_server
        self.current_session_uuid = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup share UI"""
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Share Photos via QR Code")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Server status
        server_status = self.create_server_status()
        layout.addWidget(server_status)
        
        # Main content
        content_layout = QHBoxLayout()
        
        # Left: Generate QR
        qr_box = self.create_qr_generator()
        content_layout.addWidget(qr_box, stretch=2)
        
        # Right: Active sessions
        sessions_box = self.create_active_sessions()
        content_layout.addWidget(sessions_box, stretch=3)
        
        layout.addLayout(content_layout)
    
    def create_server_status(self):
        """Create server status display"""
        group = QGroupBox("Server Status")
        layout = QHBoxLayout(group)
        
        self.server_status_label = QLabel()
        self.server_status_label.setFont(QFont("Arial", 12))
        layout.addWidget(self.server_status_label)
        
        layout.addStretch()
        
        return group
    
    def create_qr_generator(self):
        """Create QR code generator"""
        group = QGroupBox("Generate Share Link")
        layout = QVBoxLayout(group)
        
        # Student search
        search_layout = QHBoxLayout()
        self.student_search_input = QLineEdit()
        self.student_search_input.setPlaceholderText("Enter student state code...")
        search_layout.addWidget(self.student_search_input)
        
        search_btn = QPushButton("🔍 Find Student")
        search_btn.clicked.connect(self.find_student)
        search_layout.addWidget(search_btn)
        
        layout.addLayout(search_layout)
        
        # Student info display
        self.student_info_label = QLabel("No student selected")
        self.student_info_label.setStyleSheet("""
            QLabel {
                padding: 15px;
                background-color: #f5f5f5;
                border-radius: 8px;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.student_info_label)
        
        # Share settings
        settings_layout = QFormLayout()
        
        self.expiry_hours = QSpinBox()
        self.expiry_hours.setRange(1, 168)  # 1 hour to 7 days
        self.expiry_hours.setValue(24)
        self.expiry_hours.setSuffix(" hours")
        
        self.download_limit = QSpinBox()
        self.download_limit.setRange(1, 1000)
        self.download_limit.setValue(50)
        self.download_limit.setSuffix(" downloads")
        
        settings_layout.addRow("Expiry Time:", self.expiry_hours)
        settings_layout.addRow("Download Limit:", self.download_limit)
        
        layout.addLayout(settings_layout)
        
        # Generate QR button
        generate_btn = QPushButton("📱 Generate QR Code")
        generate_btn.setMinimumHeight(50)
        generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        generate_btn.clicked.connect(self.generate_qr)
        layout.addWidget(generate_btn)
        
        # QR Code display
        self.qr_display = QLabel("QR Code will appear here")
        self.qr_display.setAlignment(Qt.AlignCenter)
        self.qr_display.setMinimumSize(300, 300)
        self.qr_display.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                border-radius: 10px;
                background-color: white;
            }
        """)
        layout.addWidget(self.qr_display)
        
        # Share URL display
        self.url_display = QLineEdit()
        self.url_display.setReadOnly(True)
        self.url_display.setPlaceholderText("Share URL will appear here")
        layout.addWidget(self.url_display)
        
        # Copy URL button
        copy_btn = QPushButton("📋 Copy URL")
        copy_btn.clicked.connect(self.copy_url)
        layout.addWidget(copy_btn)
        
        return group
    
    def create_active_sessions(self):
        """Create active sessions list"""
        group = QGroupBox("Active Share Sessions")
        layout = QVBoxLayout(group)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_sessions)
        layout.addWidget(refresh_btn)
        
        # Table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels([
            "Student", "Created", "Expires", "Downloads", "Status"
        ])
        layout.addWidget(self.sessions_table)
        
        return group
    
    def refresh(self):
        """Refresh page data"""
        # Update server status
        if self.local_server.is_running():
            ip = self.local_server.get_local_ip()
            port = self.local_server.get_port()
            self.server_status_label.setText(
                f"✓ Server Running: http://{ip}:{port}"
            )
            self.server_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.server_status_label.setText("✗ Server Offline")
            self.server_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        # Refresh sessions list
        self.refresh_sessions()
    
    def find_student(self):
        """Find student by state code"""
        state_code = self.student_search_input.text().strip()
        
        if not state_code:
            QMessageBox.warning(self, "Input Required", "Please enter a state code!")
            return
        
        student = self.app_service.search_student(state_code)
        
        if not student:
            QMessageBox.warning(
                self,
                "Not Found",
                f"No student found with state code: {state_code}"
            )
            self.student_info_label.setText("No student selected")
            self.current_student = None
            return
        
        # Get photo count
        photos = self.app_service.get_student_photos(student)
        
        # Display student info
        self.student_info_label.setText(
            f"✓ {student.full_name} ({student.state_code})\n"
            f"Photos available: {len(photos)}"
        )
        
        self.current_student = student
    
    def generate_qr(self):
        """Generate QR code for student"""
        if not hasattr(self, 'current_student') or not self.current_student:
            QMessageBox.warning(
                self,
                "No Student Selected",
                "Please search and select a student first!"
            )
            return
        
        if not self.local_server.is_running():
            QMessageBox.warning(
                self,
                "Server Offline",
                "Local server is not running. Cannot generate share link."
            )
            return
        
        try:
            # Create share session
            session_uuid = self.local_server.create_share_session(
                student_id=self.current_student.id,
                expiry_hours=self.expiry_hours.value(),
                download_limit=self.download_limit.value()
            )
            
            # Get share URL
            share_url = self.local_server.get_share_url(session_uuid)
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(share_url)
            qr.make(fit=True)
            
            # Convert to QPixmap
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert PIL image to QPixmap
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            qimage = QImage()
            qimage.loadFromData(buffer.read())
            pixmap = QPixmap.fromImage(qimage)
            
            # Display QR code
            scaled = pixmap.scaled(
                280, 280,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.qr_display.setPixmap(scaled)
            
            # Display URL
            self.url_display.setText(share_url)
            self.current_session_uuid = session_uuid
            
            # Show success message
            QMessageBox.information(
                self,
                "QR Code Generated",
                f"✓ Share link created for {self.current_student.full_name}!\n\n"
                f"Students can scan the QR code or visit:\n{share_url}\n\n"
                f"Link expires in {self.expiry_hours.value()} hours"
            )
            
            # Refresh sessions list
            self.refresh_sessions()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to generate QR code:\n{str(e)}"
            )
    
    def copy_url(self):
        """Copy share URL to clipboard"""
        url = self.url_display.text()
        if url:
            from PySide6.QtGui import QGuiApplication
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(url)
            QMessageBox.information(
                self,
                "Copied",
                "✓ URL copied to clipboard!"
            )
    
    def refresh_sessions(self):
        """Refresh active sessions table"""
        # Get active sessions from local server
        sessions = self.local_server.active_sessions
        
        self.sessions_table.setRowCount(len(sessions))
        
        for row, (uuid, data) in enumerate(sessions.items()):
            # Get student name
            student = self.app_service.db_session.query(
                self.app_service.db_session.query(Student).filter_by(
                    id=data['student_id']
                ).first().__class__
            ).get(data['student_id'])
            
            if student:
                student_name = f"{student.full_name} ({student.state_code})"
            else:
                student_name = f"ID: {data['student_id']}"
            
            created = data['created_at'].strftime('%Y-%m-%d %H:%M')
            expires = data['expires_at'].strftime('%Y-%m-%d %H:%M')
            downloads = f"{data['downloads_used']}/{data['download_limit']}"
            
            # Determine status
            from datetime import datetime
            if datetime.utcnow() > data['expires_at']:
                status = "🔴 Expired"
            elif data['downloads_used'] >= data['download_limit']:
                status = "⚠️ Limit Reached"
            else:
                status = "🟢 Active"
            
            self.sessions_table.setItem(row, 0, QTableWidgetItem(student_name))
            self.sessions_table.setItem(row, 1, QTableWidgetItem(created))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(expires))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(downloads))
            self.sessions_table.setItem(row, 4, QTableWidgetItem(status))