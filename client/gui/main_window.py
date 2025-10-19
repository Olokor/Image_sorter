"""
Main Window - Primary application interface
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QStackedWidget, QLabel, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from datetime import datetime

from gui.pages.dashboard_page import DashboardPage
from gui.pages.enrollment_page import EnrollmentPage
from gui.pages.photo_import_page import PhotoImportPage
from gui.pages.review_page import ReviewPage
from gui.pages.share_page import SharePage
from gui.pages.license_page import LicensePage
from services.app_service import AppService
from services.local_server import LocalServer


class MainWindow(QMainWindow):
    """Main application window with navigation"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TLP Photo App - Photographer Edition")
        self.setMinimumSize(1200, 800)
        
        # Initialize services
        self.app_service = AppService()
        self.local_server = LocalServer(app_service=self.app_service)
        
        # Setup UI
        self.setup_ui()
        
        # Start local server
        self.local_server.start()
        
        # Check license on startup
        self.check_license()
    
    def setup_ui(self):
        """Setup the user interface"""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create sidebar
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)
        
        # Create content area
        content_area = self.create_content_area()
        main_layout.addWidget(content_area, stretch=1)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        self.server_status_label = QLabel("Server: Starting...")
        self.statusBar().addPermanentWidget(self.server_status_label)
        
        # Update server status periodically
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_server_status)
        self.status_timer.start(2000)  # Every 2 seconds
    
    def create_sidebar(self):
        """Create navigation sidebar"""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sidebar.setStyleSheet("""
            QFrame#sidebar {
                background-color: #2C3E50;
                border-right: 2px solid #34495E;
            }
            QPushButton {
                background-color: transparent;
                color: #ECF0F1;
                text-align: left;
                padding: 15px 20px;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #34495E;
            }
            QPushButton:checked {
                background-color: #3498DB;
                border-left: 4px solid #2ECC71;
            }
            QLabel {
                color: #ECF0F1;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # App title
        title = QLabel("TLP Photo App")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("padding: 30px 10px;")
        layout.addWidget(title)
        
        # Navigation buttons
        self.nav_buttons = []
        
        pages = [
            ("Dashboard", "📊"),
            ("Enroll Students", "👤"),
            ("Import Photos", "📷"),
            ("Review Matches", "✓"),
            ("Share & QR", "📱"),
            ("License & Payment", "💳"),
        ]
        
        for i, (name, icon) in enumerate(pages):
            btn = QPushButton(f"{icon}  {name}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=i: self.switch_page(idx))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        # Set first button as active
        self.nav_buttons[0].setChecked(True)
        
        layout.addStretch()
        
        # Footer info
        session_info = QLabel("No active session")
        session_info.setObjectName("sessionInfo")
        session_info.setStyleSheet("font-size: 12px; padding: 15px;")
        layout.addWidget(session_info)
        self.session_info_label = session_info
        
        return sidebar
    
    def create_content_area(self):
        """Create main content area with stacked pages"""
        self.content_stack = QStackedWidget()
        
        # Create pages
        self.dashboard_page = DashboardPage(self.app_service)
        self.enrollment_page = EnrollmentPage(self.app_service)
        self.photo_import_page = PhotoImportPage(self.app_service)
        self.review_page = ReviewPage(self.app_service)
        self.share_page = SharePage(self.app_service, self.local_server)
        self.license_page = LicensePage(self.app_service)
        
        # Add pages to stack
        self.content_stack.addWidget(self.dashboard_page)
        self.content_stack.addWidget(self.enrollment_page)
        self.content_stack.addWidget(self.photo_import_page)
        self.content_stack.addWidget(self.review_page)
        self.content_stack.addWidget(self.share_page)
        self.content_stack.addWidget(self.license_page)
        
        # Connect signals
        self.dashboard_page.session_changed.connect(self.on_session_changed)
        self.enrollment_page.student_enrolled.connect(self.refresh_dashboard)
        self.photo_import_page.photos_imported.connect(self.refresh_dashboard)
        
        return self.content_stack
    
    def switch_page(self, index):
        """Switch to a different page"""
        # Update button states
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        
        # Switch page
        self.content_stack.setCurrentIndex(index)
        
        # Refresh page if needed
        current_page = self.content_stack.currentWidget()
        if hasattr(current_page, 'refresh'):
            current_page.refresh()
    
    def on_session_changed(self, session):
        """Handle session change"""
        if session:
            self.session_info_label.setText(
                f"Session: {session.name}\n"
                f"Students: {session.student_count}"
            )
        else:
            self.session_info_label.setText("No active session")
    
    def refresh_dashboard(self):
        """Refresh dashboard after changes"""
        self.dashboard_page.refresh()
    
    def update_server_status(self):
        """Update server status in status bar"""
        if self.local_server.is_running():
            port = self.local_server.get_port()
            self.server_status_label.setText(f"✓ Server: http://localhost:{port}")
            self.server_status_label.setStyleSheet("color: green;")
        else:
            self.server_status_label.setText("✗ Server: Offline")
            self.server_status_label.setStyleSheet("color: red;")
    
    def check_license(self):
        """Check license validity on startup"""
        license_status = self.app_service.check_license()
        
        if not license_status['valid']:
            QMessageBox.warning(
                self,
                "License Expired",
                f"Your license has expired.\n\n"
                f"Expires: {license_status.get('expires', 'Unknown')}\n\n"
                f"Please renew your license to continue using the app.",
                QMessageBox.Ok
            )
            # Switch to license page
            self.switch_page(5)
    
    def closeEvent(self, event):
        """Handle application close"""
        # Stop local server
        self.local_server.stop()
        
        # Close database connections
        self.app_service.close()
        
        event.accept()