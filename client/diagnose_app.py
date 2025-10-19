"""
Diagnostic script to find what's failing in the main app
"""
import sys
import traceback

print("="*70)
print("DIAGNOSTIC TEST - Finding the issue")
print("="*70 + "\n")

# Test 1: Python environment
print("1. Testing Python environment...")
print(f"   Python version: {sys.version}")
print(f"   Python executable: {sys.executable}")
print("   ✓ Python OK\n")

# Test 2: Basic imports
print("2. Testing basic imports...")
try:
    import numpy as np
    print("   ✓ numpy")
except Exception as e:
    print(f"   ✗ numpy: {e}")

try:
    import cv2
    print("   ✓ opencv-python")
except Exception as e:
    print(f"   ✗ opencv-python: {e}")

try:
    from PIL import Image
    print("   ✓ Pillow")
except Exception as e:
    print(f"   ✗ Pillow: {e}")

try:
    from sqlalchemy import create_engine
    print("   ✓ SQLAlchemy")
except Exception as e:
    print(f"   ✗ SQLAlchemy: {e}")

print()

# Test 3: InsightFace
print("3. Testing InsightFace...")
try:
    from insightface.app import FaceAnalysis
    print("   ✓ InsightFace imports OK")
except Exception as e:
    print(f"   ✗ InsightFace import failed: {e}")
    sys.exit(1)

print()

# Test 4: FaceService
print("4. Testing FaceService initialization...")
try:
    from face_service import FaceService
    print("   ✓ FaceService module imported")
    
    service = FaceService()
    print("   ✓ FaceService initialized successfully!")
except Exception as e:
    print(f"   ✗ FaceService failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Test 5: Database models
print("5. Testing database models...")
try:
    from models import init_db, Photographer, Student, Photo
    print("   ✓ Models imported")
    
    engine, Session = init_db('sqlite:///test_diagnostic.db')
    print("   ✓ Database initialized")
except Exception as e:
    print(f"   ✗ Models failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print()

# Test 6: AppService
print("6. Testing AppService...")
try:
    import os
    import sys
    
    # Add client directory to path if needed
    client_dir = os.path.dirname(os.path.abspath(__file__))
    if client_dir not in sys.path:
        sys.path.insert(0, client_dir)
    
    from services.app_service import AppService
    print("   ✓ AppService module imported")
    
    print("   → Creating AppService instance...")
    app_service = AppService('sqlite:///test_diagnostic.db')
    print("   ✓ AppService initialized successfully!")
    
except Exception as e:
    print(f"   ✗ AppService failed: {e}")
    print("\n   Full traceback:")
    traceback.print_exc()
    sys.exit(1)

print()

# Test 7: PySide6 (GUI)
print("7. Testing PySide6...")
try:
    from PySide6.QtWidgets import QApplication
    print("   ✓ PySide6 imports OK")
except Exception as e:
    print(f"   ✗ PySide6: {e}")
    sys.exit(1)

print()

# Test 8: Try creating the main window
print("8. Testing MainWindow creation...")
try:
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    
    print("   ✓ MainWindow module imported")
    
    # Don't actually show the window, just try to create it
    print("   → Creating QApplication...")
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    print("   ✓ QApplication created")
    
    print("   → Creating MainWindow...")
    window = MainWindow()
    print("   ✓ MainWindow created successfully!")
    
    # Clean up
    window.close()
    
except Exception as e:
    print(f"   ✗ MainWindow creation failed: {e}")
    print("\n   Full traceback:")
    traceback.print_exc()
    sys.exit(1)

print()
print("="*70)
print("✓ ALL TESTS PASSED!")
print("="*70)
print("\nYour app should work now. Try running:")
print("  python main.py")
print()