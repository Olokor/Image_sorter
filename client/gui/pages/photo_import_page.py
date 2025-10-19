"""Photo Import Page - Batch import and process photos"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QProgressBar, QTextEdit, QGroupBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
import os


class PhotoImportWorker(QThread):
    """Worker thread for photo processing"""
    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(dict)  # results
    error = Signal(str)  # error message
    
    def __init__(self, app_service, photo_paths):
        super().__init__()
        self.app_service = app_service
        self.photo_paths = photo_paths
    
    def run(self):
        try:
            def progress_callback(current, total, filename):
                self.progress.emit(current, total, filename)
            
            results = self.app_service.import_photos(self.photo_paths, progress_callback)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PhotoImportPage(QWidget):
    """Photo import and batch processing page"""
    
    photos_imported = Signal()
    
    def __init__(self, app_service):
        super().__init__()
        self.app_service = app_service
        self.worker = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Import & Process Photos")
        header.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(header)
        
        # Instructions
        info_box = QGroupBox("Instructions")
        info_layout = QVBoxLayout(info_box)
        instructions = QLabel(
            "1. Ensure students are enrolled before importing photos\n"
            "2. Select a folder containing event photos\n"
            "3. Wait for processing to complete\n"
            "4. Review matches in the Review page if needed"
        )
        instructions.setStyleSheet("padding: 10px; font-size: 13px;")
        info_layout.addWidget(instructions)
        layout.addWidget(info_box)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        select_folder_btn = QPushButton("📁 Select Photo Folder")
        select_folder_btn.setMinimumHeight(60)
        select_folder_btn.setStyleSheet("""
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
        select_folder_btn.clicked.connect(self.select_folder)
        button_layout.addWidget(select_folder_btn)
        
        select_files_btn = QPushButton("📷 Select Individual Photos")
        select_files_btn.setMinimumHeight(60)
        select_files_btn.clicked.connect(self.select_files)
        button_layout.addWidget(select_files_btn)
        
        layout.addLayout(button_layout)
        
        # Progress section
        progress_group = QGroupBox("Processing Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready to import photos")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Arial", 12))
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # Processing log
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_log_btn)
        
        layout.addWidget(log_group)
    
    def select_folder(self):
        """Select folder containing photos"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Photo Folder",
            "",
            QFileDialog.ShowDirsOnly
        )
        
        if folder:
            valid_ext = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
            photo_paths = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if os.path.splitext(f)[1] in valid_ext
            ]
            
            if photo_paths:
                self.import_photos(photo_paths)
            else:
                QMessageBox.warning(
                    self,
                    "No Photos Found",
                    "No valid photos found in selected folder!"
                )
    
    def select_files(self):
        """Select individual photo files"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Photos",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if files:
            self.import_photos(files)
    
    def import_photos(self, photo_paths):
        """Start importing photos"""
        # Check for active session
        if not self.app_service.get_active_session():
            QMessageBox.warning(
                self,
                "No Active Session",
                "Please create or select an active session first!"
            )
            return
        
        # Check if students are enrolled
        students = self.app_service.get_students()
        if not students:
            reply = QMessageBox.question(
                self,
                "No Students Enrolled",
                "No students have been enrolled yet.\n"
                "Photos will be processed but not matched to anyone.\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.log_text.append(f"\n{'='*60}")
        self.log_text.append(f"Starting import: {len(photo_paths)} photo(s)")
        self.log_text.append(f"{'='*60}\n")
        
        self.progress_bar.setMaximum(len(photo_paths))
        self.progress_bar.setValue(0)
        
        # Start worker thread
        self.worker = PhotoImportWorker(self.app_service, photo_paths)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def on_progress(self, current, total, filename):
        """Handle progress update"""
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processing {current}/{total}: {filename}")
        self.log_text.append(f"[{current}/{total}] {filename}")
        
        # Auto-scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def on_finished(self, results):
        """Handle import completion"""
        self.log_text.append(f"\n{'='*60}")
        self.log_text.append("IMPORT COMPLETED")
        self.log_text.append(f"{'='*60}")
        self.log_text.append(f"✓ Processed: {results['processed']}")
        self.log_text.append(f"⊘ Skipped (duplicates): {results['skipped']}")
        self.log_text.append(f"👤 Faces detected: {results['faces_detected']}")
        self.log_text.append(f"✓ Faces matched: {results['faces_matched']}")
        
        unmatched = results['faces_detected'] - results['faces_matched']
        if unmatched > 0:
            self.log_text.append(f"⚠ Unmatched faces: {unmatched}")
            self.log_text.append("   → Check Review page for manual matching")
        
        self.log_text.append(f"{'='*60}\n")
        
        self.status_label.setText("✓ Import complete!")
        
        # Emit signal
        self.photos_imported.emit()
        
        # Show summary
        QMessageBox.information(
            self,
            "Import Complete",
            f"✓ Successfully processed {results['processed']} photos!\n\n"
            f"Faces detected: {results['faces_detected']}\n"
            f"Faces matched: {results['faces_matched']}\n"
            f"Unmatched faces: {unmatched}\n\n"
            f"Check the Review page for any unmatched faces."
        )
    
    def on_error(self, error_msg):
        """Handle import error"""
        self.log_text.append(f"\n✗ ERROR: {error_msg}\n")
        self.status_label.setText("✗ Import failed")
        
        QMessageBox.critical(
            self,
            "Import Error",
            f"An error occurred during import:\n\n{error_msg}"
        )
    
    def refresh(self):
        """Refresh page (called when navigating here)"""
        pass

