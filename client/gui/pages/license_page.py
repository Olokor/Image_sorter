"""License Page - View license status and handle payments"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGroupBox, QFormLayout, QTextEdit, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt


class LicensePage(QWidget):
    """License management and payment page"""
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("License & Payment")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # License status card
        status_card = self.create_license_status()
        layout.addWidget(status_card)
        
        # Current session billing
        billing_card = self.create_billing_info()
        layout.addWidget(billing_card)
        
        # Actions
        action_layout = QHBoxLayout()
        
        renew_btn = QPushButton("💳 Renew License")
        renew_btn.setMinimumHeight(60)
        renew_btn.setStyleSheet("""
            QPushButton {
                background-color: #E67E22;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #D35400;
            }
        """)
        renew_btn.clicked.connect(self.renew_license)
        action_layout.addWidget(renew_btn)
        
        pay_session_btn = QPushButton("💰 Pay for Current Session")
        pay_session_btn.setMinimumHeight(60)
        pay_session_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        pay_session_btn.clicked.connect(self.pay_session)
        action_layout.addWidget(pay_session_btn)
        
        layout.addLayout(action_layout)
        
        # Info text
        info_group = QGroupBox("Payment Information")
        info_layout = QVBoxLayout(info_group)
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(150)
        info_text.setHtml("""
            <h3>Billing Details</h3>
            <ul>
                <li><b>First session:</b> Free trial</li>
                <li><b>Subsequent sessions:</b> ₦200 per enrolled student</li>
                <li><b>License validity:</b> 30 days from activation</li>
                <li><b>Payment method:</b> Paystack (online)</li>
            </ul>
            <p><i>Note: Payment integration requires cloud backend deployment.</i></p>
        """)
        info_layout.addWidget(info_text)
        
        layout.addWidget(info_group)
        
        layout.addStretch()
        
        # Initial refresh
        self.refresh()
    
    def create_license_status(self):
        """Create license status display"""
        group = QGroupBox("License Status")
        layout = QFormLayout(group)
        
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.expiry_label = QLabel()
        self.remaining_label = QLabel()
        self.photographer_label = QLabel()
        
        layout.addRow("Status:", self.status_label)
        layout.addRow("Photographer:", self.photographer_label)
        layout.addRow("Valid Until:", self.expiry_label)
        layout.addRow("Days Remaining:", self.remaining_label)
        
        return group
    
    def create_billing_info(self):
        """Create current session billing info"""
        group = QGroupBox("Current Session Billing")
        layout = QFormLayout(group)
        
        self.session_name_label = QLabel("-")
        self.student_count_label = QLabel("0")
        self.amount_due_label = QLabel("₦0.00")
        self.payment_status_label = QLabel("-")
        
        layout.addRow("Session:", self.session_name_label)
        layout.addRow("Students Enrolled:", self.student_count_label)
        layout.addRow("Amount Due:", self.amount_due_label)
        layout.addRow("Payment Status:", self.payment_status_label)
        
        return group
    
    def refresh(self):
        """Refresh license and billing information"""
        # Update license info
        license_info = self.app_service.check_license()
        
        if license_info['valid']:
            self.status_label.setText("✓ Active")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("✗ Expired")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.expiry_label.setText(license_info.get('expires', 'Unknown'))
        
        days_remaining = license_info.get('days_remaining', 0)
        self.remaining_label.setText(str(days_remaining))
        
        if days_remaining < 7:
            self.remaining_label.setStyleSheet("color: red; font-weight: bold;")
        elif days_remaining < 14:
            self.remaining_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.remaining_label.setStyleSheet("color: green;")
        
        # Update photographer info
        if self.app_service.current_photographer:
            self.photographer_label.setText(
                f"{self.app_service.current_photographer.name} "
                f"({self.app_service.current_photographer.email})"
            )
        
        # Update session billing
        session = self.app_service.get_active_session()
        if session:
            self.session_name_label.setText(session.name)
            self.student_count_label.setText(str(session.student_count))
            
            if session.is_free_trial:
                self.amount_due_label.setText("₦0.00 (Free Trial)")
                self.amount_due_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                amount = session.student_count * 200
                self.amount_due_label.setText(f"₦{amount:,.2f}")
                
                if amount > 0:
                    self.amount_due_label.setStyleSheet("color: red; font-weight: bold;")
            
            if session.payment_verified:
                self.payment_status_label.setText("✓ Paid")
                self.payment_status_label.setStyleSheet("color: green; font-weight: bold;")
            elif session.is_free_trial:
                self.payment_status_label.setText("Free Trial")
                self.payment_status_label.setStyleSheet("color: blue;")
            else:
                self.payment_status_label.setText("⚠ Pending Payment")
                self.payment_status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.session_name_label.setText("-")
            self.student_count_label.setText("0")
            self.amount_due_label.setText("₦0.00")
            self.payment_status_label.setText("-")
    
    def renew_license(self):
        """Initiate license renewal"""
        QMessageBox.information(
            self,
            "License Renewal",
            "License renewal feature coming soon!\n\n"
            "This will connect to the cloud backend and initiate\n"
            "a Paystack payment for license extension.\n\n"
            "For now, your license is valid for 30 days from activation."
        )
        
        # TODO: Implement when cloud backend is ready
        # 1. Close current session if needed
        # 2. Call cloud API to initiate payment
        # 3. Open Paystack payment URL in browser
        # 4. Wait for webhook confirmation
        # 5. Update local license file
    
    def pay_session(self):
        """Pay for current session"""
        session = self.app_service.get_active_session()
        
        if not session:
            QMessageBox.warning(
                self,
                "No Active Session",
                "No active session to pay for!"
            )
            return
        
        if session.is_free_trial:
            QMessageBox.information(
                self,
                "Free Trial",
                "This session is a free trial - no payment required!"
            )
            return
        
        if session.payment_verified:
            QMessageBox.information(
                self,
                "Already Paid",
                "This session has already been paid for!"
            )
            return
        
        amount = session.student_count * 200
        
        if amount == 0:
            QMessageBox.warning(
                self,
                "No Students",
                "No students enrolled - nothing to pay!"
            )
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Payment",
            f"Session: {session.name}\n"
            f"Students: {session.student_count}\n"
            f"Amount: ₦{amount:,.2f}\n\n"
            f"Proceed to payment?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            QMessageBox.information(
                self,
                "Payment Integration",
                "Paystack payment integration coming soon!\n\n"
                "This will:\n"
                "1. Close the session\n"
                "2. Generate payment link\n"
                "3. Open Paystack checkout\n"
                "4. Verify payment via webhook\n"
                "5. Update license for next session\n\n"
                "For now, sessions can be used without payment."
            )
            
            # TODO: Implement when cloud backend is ready
            # 1. Close session
            # 2. Calculate final amount
            # 3. Call cloud API to initiate payment
            # 4. Open Paystack URL
            # 5. Poll for payment confirmation

