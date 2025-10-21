"""
Fixed Main Entry Point - Prevents Recursion Errors
Proper initialization order with minimal imports
"""
import sys
import os

# CRITICAL: Set recursion limit BEFORE any imports
sys.setrecursionlimit(3000)  # Increase from default 1000

# Add client directory to path
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

# Disable regex caching that causes recursion
import re
re._cache = {}
re._cache_repl = {}


def main():
    """Initialize and run with proper error handling"""
    print("\n" + "="*70)
    print("TLP PHOTO APP - STARTING")
    print("="*70 + "\n")
    
    try:
        # Step 1: Check dependencies (minimal imports)
        print("Step 1: Checking dependencies...")
        from dependencies import DependencyChecker, PYSIDE6_AVAILABLE
        
        missing = DependencyChecker.check_all()
        if missing:
            print("\n⚠ Missing dependencies!")
            for dep in missing:
                print(f"  - {dep}")
            print("\nInstall and try again.\n")
            return 1
        
        print("✓ All dependencies available\n")
        
        # Step 2: Initialize Qt (before any GUI imports)
        print("Step 2: Initializing Qt...")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        
        # High DPI settings
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        # Create QApplication FIRST
        app = QApplication(sys.argv)
        app.setApplicationName("TLP Photo App")
        app.setOrganizationName("TLP Photography")
        app.setStyle('Fusion')
        
        print("✓ Qt initialized\n")
        
        # Step 3: Initialize backend services (NO GUI IMPORTS)
        print("Step 3: Initializing backend services...")
        
        # Import models and services (not GUI)
        from services.app_service import EnhancedAppService
        from services.local_server import FixedLocalServer
        
        # Create services
        app_service = EnhancedAppService()
        local_server = FixedLocalServer(app_service=app_service)
        
        print("✓ Backend services ready\n")
        
        # Step 4: NOW import and create GUI
        print("Step 4: Creating main window...")
        
        # Import MainWindow ONLY after services are ready
        from gui.main_window import MainWindow
        
        # Create window with dependency injection
        window = MainWindow(
            app_service=app_service,
            local_server=local_server
        )
        
        print("✓ Main window created\n")
        
        # Step 5: Show and run
        print("="*70)
        print("✓ APP READY!")
        print("="*70 + "\n")
        
        window.show()
        return app.exec()
        
    except RecursionError as e:
        print(f"\n\n{'='*70}")
        print("RECURSION ERROR DETECTED!")
        print('='*70)
        print(f"\nError: {e}")
        print("\nThis usually means:")
        print("1. Circular import between modules")
        print("2. Infinite loop in __repr__ or property")
        print("3. SQLAlchemy relationship issue")
        print("\nTry running: python diagnose_app.py")
        return 1
        
    except Exception as e:
        print(f"\n\n{'='*70}")
        print("FATAL ERROR")
        print('='*70)
        print(f"\nError: {e}")
        
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        
        return 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nUNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)