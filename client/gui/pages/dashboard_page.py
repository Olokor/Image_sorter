"""
Dashboard Page - Session overview and management
Uses centralized dependency manager
"""
from dependencies import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QGridLayout, QComboBox,
    QDialog, QLineEdit, QDialogButtonBox, QFormLayout,
    Qt, Signal, QFont
)


class DashboardPage(QWidget):
    """Dashboard with session stats and quick actions"""
    
    session_changed = Signal(object)  # Emits current session
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        """Setup dashboard UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("Dashboard")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Session selector
        session_box = self.create_session_selector()
        layout.addWidget(session_box)
        
        # Statistics cards
        stats_layout = QHBoxLayout()
        
        self.students_card = self.create_stat_card("Students", "0", "#3498DB")
        self.photos_card = self.create_stat_card("Photos", "0", "#2ECC71")
        self.faces_card = self.create_stat_card("Faces Detected", "0", "#9B59B6")
        self.matched_card = self.create_stat_card("Matched", "0", "#E67E22")
        
        stats_layout.addWidget(self.students_card)
        stats_layout.addWidget(self.photos_card)
        stats_layout.addWidget(self.faces_card)
        stats_layout.addWidget(self.matched_card)
        
        layout.addLayout(stats_layout)
        
        # Quick actions
        actions_box = self.create_quick_actions()
        layout.addWidget(actions_box)
        
        # Session info
        info_box = self.create_session_info()
        layout.addWidget(info_box)
        
        layout.addStretch()
    
    def create_session_selector(self):
        """Create session selector"""
        group = QGroupBox("Active Session")
        layout = QHBoxLayout(group)
        
        self.session_combo = QComboBox()
        self.session_combo.currentIndexChanged.connect(self.on_session_selected)
        layout.addWidget(QLabel("Session:"))
        layout.addWidget(self.session_combo, stretch=1)
        
        new_btn = QPushButton("+ New Session")
        new_btn.clicked.connect(self.create_new_session)
        layout.addWidget(new_btn)
        
        return group
    
    def create_stat_card(self, title, value, color):
        """Create a statistic card"""
        card = QGroupBox()
        card.setStyleSheet(f"""
            QGroupBox {{
                background-color: {color};
                border-radius: 10px;
                padding: 20px;
            }}
            QLabel {{
                color: white;
            }}
        """)
        
        layout = QVBoxLayout(card)
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 36, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName("value")
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14))
        title_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        
        return card
    
    def create_quick_actions(self):
        """Create quick action buttons"""
        group = QGroupBox("Quick Actions")
        layout = QGridLayout(group)
        
        actions = [
            ("👤 Enroll Student", self.go_to_enrollment),
            ("📷 Import Photos", self.go_to_import),
            ("✓ Review Matches", self.go_to_review),
            ("📱 Share via QR", self.go_to_share),
        ]
        
        for idx, (text, callback) in enumerate(actions):
            btn = QPushButton(text)
            btn.setMinimumHeight(50)
            btn.clicked.connect(callback)
            row = idx // 2
            col = idx % 2
            layout.addWidget(btn, row, col)
        
        return group
    
    def create_session_info(self):
        """Create session information panel"""
        group = QGroupBox("Session Information")
        layout = QFormLayout(group)
        
        self.session_name_label = QLabel("-")
        self.session_location_label = QLabel("-")
        self.session_date_label = QLabel("-")
        self.session_status_label = QLabel("-")
        
        layout.addRow("Name:", self.session_name_label)
        layout.addRow("Location:", self.session_location_label)
        layout.addRow("Started:", self.session_date_label)
        layout.addRow("Status:", self.session_status_label)
        
        return group
    
    def refresh(self):
        """Refresh dashboard data"""
        if not self.app_service:
            return
            
        # Load sessions
        self.session_combo.clear()
        sessions = self.app_service.get_all_sessions()
        
        for session in sessions:
            self.session_combo.addItem(
                f"{session.name} ({session.start_date.strftime('%Y-%m-%d')})",
                session.id
            )
        
        # Get current session
        current_session = self.app_service.get_active_session()
        
        if current_session:
            # Find and select current session
            for i in range(self.session_combo.count()):
                if self.session_combo.itemData(i) == current_session.id:
                    self.session_combo.setCurrentIndex(i)
                    break
            
            # Update stats
            stats = self.app_service.get_session_stats()
            self.update_stats(stats)
            
            # Update session info
            self.update_session_info(current_session)
            
            # Emit signal
            self.session_changed.emit(current_session)
        else:
            self.update_stats({})
            self.session_changed.emit(None)
    
    def update_stats(self, stats):
        """Update statistic cards"""
        self.students_card.findChild(QLabel, "value").setText(str(stats.get('students', 0)))
        self.photos_card.findChild(QLabel, "value").setText(str(stats.get('photos', 0)))
        self.faces_card.findChild(QLabel, "value").setText(str(stats.get('total_faces', 0)))
        self.matched_card.findChild(QLabel, "value").setText(str(stats.get('matched_faces', 0)))
    
    def update_session_info(self, session):
        """Update session information panel"""
        self.session_name_label.setText(session.name)
        self.session_location_label.setText(session.location or "Not specified")
        self.session_date_label.setText(session.start_date.strftime('%Y-%m-%d %H:%M'))
        
        status = "🟢 Active" if session.is_active else "🔴 Closed"
        if session.is_free_trial:
            status += " (Free Trial)"
        self.session_status_label.setText(status)
    
    def on_session_selected(self, index):
        """Handle session selection change"""
        if index >= 0 and self.app_service:
            session_id = self.session_combo.itemData(index)
            if session_id:
                self.app_service.set_active_session(session_id)
                self.refresh()
    
    def create_new_session(self):
        """Open dialog to create new session"""
        dialog = NewSessionDialog(self)
        if dialog.exec():
            name, location = dialog.get_values()
            if self.app_service:
                session = self.app_service.create_session(name, location)
                self.refresh()
    
    def go_to_enrollment(self):
        """Navigate to enrollment page"""
        self.window().switch_page(1)
    
    def go_to_import(self):
        """Navigate to import page"""
        self.window().switch_page(2)
    
    def go_to_review(self):
        """Navigate to review page"""
        self.window().switch_page(3)
    
    def go_to_share(self):
        """Navigate to share page"""
        self.window().switch_page(4)


class NewSessionDialog(QDialog):
    """Dialog for creating a new session"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Session")
        self.setMinimumWidth(400)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QFormLayout(self)
        
        self.name_input = QLineEdit()
        self.location_input = QLineEdit()
        
        layout.addRow("Session Name:", self.name_input)
        layout.addRow("Location:", self.location_input)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addRow(buttons)
    
    def get_values(self):
        return self.name_input.text(), self.location_input.text()