"""
TLP Photo App - Main Entry Point (FIXED)
Proper initialization order to prevent circular imports
"""
import sys
import os

# Add client directory to path
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

def main():
    """Initialize and run the application"""
    print("\n" + "="*70)
    print("TLP PHOTO APP - STARTING")
    print("="*70 + "\n")
    
    # Step 1: Check dependencies
    print("Step 1: Checking dependencies...")
    from dependencies import DependencyChecker, PYSIDE6_AVAILABLE
    
    missing = DependencyChecker.check_all()
    if missing:
        print("\n⚠ Some dependencies are missing!")
        DependencyChecker.print_status()
        print("\nMissing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall missing dependencies and try again.\n")
        return
    
    print("✓ All dependencies available\n")
    
    # Step 2: Import Qt after dependency check
    print("Step 2: Initializing Qt...")
    from dependencies import QApplication, Qt
    
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("TLP Photo App")
    app.setOrganizationName("TLP Photography")
    app.setApplicationVersion("1.0.0")
    app.setStyle('Fusion')
    
    print("✓ Qt initialized\n")
    
    # Step 3: Initialize services (BEFORE GUI)
    print("Step 3: Initializing services...")
    try:
        from services.app_service import AppService
        from services.local_server import LocalServer
        
        app_service = AppService()
        local_server = LocalServer(app_service=app_service)
        
        print("✓ Services initialized\n")
    except Exception as e:
        print(f"✗ Service initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 4: Create GUI (AFTER services)
    print("Step 4: Creating main window...")
    try:
        from gui.main_window import MainWindow
        
        # Inject dependencies instead of creating them inside
        window = MainWindow(
            app_service=app_service,
            local_server=local_server
        )
        
        print("✓ Main window created\n")
    except Exception as e:
        print(f"✗ Window creation failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Show and run
    print("Step 5: Launching application...\n")
    print("="*70)
    print("✓ APP READY!")
    print("="*70 + "\n")
    
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)