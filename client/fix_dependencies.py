"""
Dependency Fix Script - Pure Python
Run this AFTER activating your virtual environment

USAGE:
1. Activate venv: .venv\Scripts\Activate.ps1
2. Run: python fix_dependencies.py
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    print(f"Running: {cmd}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print("Warnings:", result.stderr)
        print(f"✓ {description} - SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} - FAILED")
        print(f"Error: {e.stderr}")
        return False
    except Exception as e:
        print(f"✗ {description} - FAILED")
        print(f"Error: {e}")
        return False

def check_venv():
    """Check if we're in a virtual environment"""
    in_venv = (
        hasattr(sys, 'real_prefix') or 
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )
    return in_venv

def main():
    print("\n" + "="*70)
    print("TLP PHOTO APP - DEPENDENCY FIX")
    print("="*70 + "\n")
    
    # Check if in venv
    if not check_venv():
        print("⚠ WARNING: You don't appear to be in a virtual environment!")
        print("\nPlease activate your virtual environment first:")
        print("  PowerShell: .venv\\Scripts\\Activate.ps1")
        print("  CMD:        .venv\\Scripts\\activate.bat")
        print("\nThen run this script again.")
        input("\nPress Enter to exit...")
        return
    
    print("✓ Virtual environment detected")
    print(f"Python: {sys.version}")
    print(f"Location: {sys.prefix}\n")
    
    # Step 1: Check current NumPy
    print("Checking current NumPy version...")
    try:
        import numpy
        print(f"Current NumPy: {numpy.__version__}")
        if numpy.__version__.startswith("2."):
            print("⚠ NumPy 2.x detected - needs downgrade")
        else:
            print("✓ NumPy 1.x - good version")
    except ImportError:
        print("NumPy not installed")
    
    # Step 2: Uninstall problematic packages
    packages_to_remove = ["numpy", "insightface", "onnxruntime"]
    for pkg in packages_to_remove:
        run_command(
            f"{sys.executable} -m pip uninstall {pkg} -y",
            f"Uninstalling {pkg}"
        )
    
    # Step 3: Install correct versions
    packages_to_install = [
        ("numpy<2.0", "NumPy 1.x"),
        ("insightface==0.7.3", "InsightFace"),
        ("onnxruntime==1.16.0", "ONNX Runtime"),
        ("opencv-python", "OpenCV"),
        ("pillow", "Pillow"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pyside6", "PySide6"),
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("qrcode[pil]", "QRCode"),
    ]
    
    failed = []
    for package, name in packages_to_install:
        success = run_command(
            f"{sys.executable} -m pip install {package}",
            f"Installing {name}"
        )
        if not success:
            failed.append(name)
    
    # Step 4: Verify installation
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70 + "\n")
    
    tests = [
        ("import numpy; print(f'NumPy: {numpy.__version__}')", "NumPy"),
        ("import cv2; print(f'OpenCV: {cv2.__version__}')", "OpenCV"),
        ("from PIL import Image; print('Pillow: OK')", "Pillow"),
        ("import sqlalchemy; print('SQLAlchemy: OK')", "SQLAlchemy"),
        ("from insightface.app import FaceAnalysis; print('InsightFace: OK')", "InsightFace"),
        ("from PySide6.QtWidgets import QApplication; print('PySide6: OK')", "PySide6"),
        ("import fastapi; print('FastAPI: OK')", "FastAPI"),
        ("import qrcode; print('QRCode: OK')", "QRCode"),
    ]
    
    all_ok = True
    for code, name in tests:
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"✓ {name:20} {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"✗ {name:20} FAILED")
            all_ok = False
    
    # Summary
    print("\n" + "="*70)
    if all_ok and not failed:
        print("✓ ALL DEPENDENCIES FIXED!")
        print("="*70 + "\n")
        print("Next steps:")
        print("1. Update your code files with the new versions from the guide")
        print("2. Run: python main.py")
    else:
        print("⚠ SOME ISSUES REMAIN")
        print("="*70 + "\n")
        if failed:
            print("Failed to install:")
            for pkg in failed:
                print(f"  - {pkg}")
        print("\nTry manually installing the failed packages:")
        print(f"  {sys.executable} -m pip install --no-cache-dir <package>")
    
    print("\n")
    input("Press Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstallation interrupted by user\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)