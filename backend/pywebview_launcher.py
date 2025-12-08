"""
PyWebView Launcher for Photo Sorter App
Creates a native desktop window with your FastAPI app
"""

import webview
import threading
import time
import sys
import os
from pathlib import Path

# Fix paths for frozen executable
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(os.path.dirname(sys.executable))
else:
    BASE_DIR = Path(__file__).resolve().parent

# Add backend to path
backend_dir = BASE_DIR / 'backend' if getattr(sys, 'frozen', False) else BASE_DIR
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(BASE_DIR))

# Set environment variables
os.environ['PHOTOSORTER_BASE_DIR'] = str(BASE_DIR)

# Data directory
if sys.platform == 'win32':
    DATA_DIR = Path(os.environ.get('APPDATA', Path.home())) / 'PhotoSorter'
else:
    DATA_DIR = Path.home() / '.photosorter'

DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ['PHOTOSORTER_DATA_DIR'] = str(DATA_DIR)


class PhotoSorterApp:
    """Main application class"""
    
    def __init__(self):
        self.server = None
        self.port = 8080
        self.window = None
        self.server_error = None
        
    def start_server(self):
        """Start FastAPI server in background thread"""
        try:
            print("Starting FastAPI server...")
            
            # Change to data directory
            os.chdir(DATA_DIR)
            
            # Import FastAPI app
            from main import app
            import uvicorn
            
            # Configure uvicorn
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
                access_log=False
            )
            
            self.server = uvicorn.Server(config)
            
            print(f"Server starting on port {self.port}")
            self.server.run()
            
        except Exception as e:
            self.server_error = str(e)
            print(f"Server error: {e}")
            import traceback
            traceback.print_exc()
            
            # Log to file
            log_file = DATA_DIR / 'server_error.log'
            with open(log_file, 'w') as f:
                f.write(f"Server Error:\n{traceback.format_exc()}\n")
    
    def check_server_ready(self):
        """Wait for server to be ready"""
        import socket
        
        max_attempts = 30
        for i in range(max_attempts):
            # Check if server thread had an error
            if self.server_error:
                return False
                
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', self.port))
                sock.close()
                
                if result == 0:
                    print("Server is ready!")
                    return True
                    
            except Exception:
                pass
            
            time.sleep(0.5)
            
        print("Server failed to start in time")
        return False
    
    def create_window(self):
        """Create PyWebView window"""
        
        # Start server in background
        server_thread = threading.Thread(target=self.start_server, daemon=True)
        server_thread.start()
        
        # Wait for server to be ready
        if not self.check_server_ready():
            print(f"ERROR: Server did not start. Error: {self.server_error}")
            input("\nPress Enter to exit...")
            return
        
        # Create window
        self.window = webview.create_window(
            title='Photo Sorter - AI Photo Sorting',
            url=f'http://127.0.0.1:{self.port}/login',
            width=1280,
            height=800,
            resizable=True,
            fullscreen=False,
            min_size=(800, 600),
        )
        
        # Start GUI
        webview.start(debug=False)
    
    def run(self):
        """Run the application"""
        print("\n" + "="*70)
        print(" PHOTO SORTER APP")
        print("="*70)
        print(f"\n Base directory: {BASE_DIR}")
        print(f" Data directory: {DATA_DIR}")
        print(f" Port: {self.port}")
        print("\n Starting application...")
        print("="*70 + "\n")
        
        try:
            self.create_window()
        except KeyboardInterrupt:
            print("\n\n Shutting down...")
        except Exception as e:
            print(f"\n ERROR: {e}")
            import traceback
            traceback.print_exc()
            input("\nPress Enter to exit...")


def main():
    """Main entry point"""
    
    print("Checking dependencies...")
    
    # Check dependencies
    required = ['fastapi', 'uvicorn', 'webview', 'peewee', 'PIL', 'cv2', 'numpy']
    missing = []
    
    for module in required:
        try:
            __import__(module)
            print(f"  [OK] {module}")
        except ImportError as e:
            print(f"  [MISSING] {module}: {e}")
            missing.append(module)
    
    if missing:
        print("\nERROR: Missing dependencies:")
        for m in missing:
            print(f"  - {m}")
        print("\nPlease install required packages.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    print("\nAll dependencies OK!\n")
    
    # Run app
    app = PhotoSorterApp()
    app.run()


if __name__ == "__main__":
    main()