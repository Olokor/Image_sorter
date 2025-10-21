"""
Centralized Dependency Manager
All imports happen here to prevent circular dependencies
"""
import sys
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any

# ==================== THIRD PARTY IMPORTS ====================
# These are imported first as they have no internal dependencies

# Database
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, LargeBinary, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session as DBSession

# Image processing
import numpy as np
import cv2
from PIL import Image
import hashlib

# Face recognition
try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    FaceAnalysis = None
    INSIGHTFACE_AVAILABLE = False

# GUI (PySide6)
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QStackedWidget, QLabel, QFrame, QMessageBox,
        QLineEdit, QFormLayout, QGroupBox, QGridLayout, QComboBox,
        QDialog, QDialogButtonBox, QFileDialog, QProgressBar,
        QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
        QScrollArea, QSpinBox
    )
    from PySide6.QtCore import Qt, QTimer, Signal, QThread
    from PySide6.QtGui import QFont, QPixmap, QImage, QGuiApplication
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

# Server
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# QR Code
try:
    import qrcode
    from io import BytesIO
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

# Utilities
import socket
import uuid
from threading import Thread

# ==================== CONFIGURATION CONSTANTS ====================
SIMILARITY_THRESHOLD = 0.77
REVIEW_THRESHOLD = 0.55
THUMBNAIL_MAX = 1080
COMPRESSION_QUALITY = 85

# ==================== DEPENDENCY CHECKER ====================
class DependencyChecker:
    """Check and report missing dependencies"""
    
    @staticmethod
    def check_all():
        """Check all required dependencies"""
        missing = []
        
        if not INSIGHTFACE_AVAILABLE:
            missing.append("insightface")
        
        if not PYSIDE6_AVAILABLE:
            missing.append("PySide6")
        
        if not FASTAPI_AVAILABLE:
            missing.append("fastapi + uvicorn")
        
        if not QRCODE_AVAILABLE:
            missing.append("qrcode")
        
        return missing
    
    @staticmethod
    def print_status():
        """Print dependency status"""
        print("\n" + "="*70)
        print("DEPENDENCY STATUS")
        print("="*70)
        
        deps = [
            ("NumPy", True, np.__version__),
            ("OpenCV", True, cv2.__version__),
            ("Pillow", True, Image.__version__),
            ("SQLAlchemy", True, "installed"),
            ("InsightFace", INSIGHTFACE_AVAILABLE, "available" if INSIGHTFACE_AVAILABLE else "MISSING"),
            ("PySide6", PYSIDE6_AVAILABLE, "available" if PYSIDE6_AVAILABLE else "MISSING"),
            ("FastAPI", FASTAPI_AVAILABLE, "available" if FASTAPI_AVAILABLE else "MISSING"),
            ("QRCode", QRCODE_AVAILABLE, "available" if QRCODE_AVAILABLE else "MISSING"),
        ]
        
        all_ok = True
        for name, available, version in deps:
            status = "✓" if available else "✗"
            print(f"  {status} {name:20} {version}")
            if not available:
                all_ok = False
        
        print("="*70 + "\n")
        
        if not all_ok:
            missing = DependencyChecker.check_all()
            print("Missing dependencies:")
            for dep in missing:
                print(f"  pip install {dep}")
            print()
        
        return all_ok


# ==================== EXPORT ALL ====================
__all__ = [
    # Core Python
    'datetime', 'timedelta', 'Optional', 'List', 'Dict', 'Tuple', 'Any',
    'sys', 'os', 'hashlib', 'socket', 'uuid', 'Thread',
    
    # Database
    'create_engine', 'Column', 'Integer', 'String', 'Float', 'DateTime',
    'ForeignKey', 'Boolean', 'LargeBinary', 'text',
    'declarative_base', 'relationship', 'sessionmaker', 'DBSession',
    
    # Image processing
    'np', 'cv2', 'Image',
    
    # Face recognition
    'FaceAnalysis', 'INSIGHTFACE_AVAILABLE',
    
    # GUI
    'QApplication', 'QMainWindow', 'QWidget', 'QVBoxLayout', 'QHBoxLayout',
    'QPushButton', 'QStackedWidget', 'QLabel', 'QFrame', 'QMessageBox',
    'QLineEdit', 'QFormLayout', 'QGroupBox', 'QGridLayout', 'QComboBox',
    'QDialog', 'QDialogButtonBox', 'QFileDialog', 'QProgressBar',
    'QTextEdit', 'QTableWidget', 'QTableWidgetItem', 'QHeaderView',
    'QScrollArea', 'QSpinBox',
    'Qt', 'QTimer', 'Signal', 'QThread',
    'QFont', 'QPixmap', 'QImage', 'QGuiApplication',
    'PYSIDE6_AVAILABLE',
    
    # Server
    'FastAPI', 'HTTPException', 'FileResponse', 'HTMLResponse',
    'StaticFiles', 'uvicorn', 'FASTAPI_AVAILABLE',
    
    # QR Code
    'qrcode', 'BytesIO', 'QRCODE_AVAILABLE',
    
    # Config
    'SIMILARITY_THRESHOLD', 'REVIEW_THRESHOLD', 'THUMBNAIL_MAX', 'COMPRESSION_QUALITY',
    
    # Checker
    'DependencyChecker'
]