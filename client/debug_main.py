"""Debug version to find exact failure point"""
import sys
import traceback

print("\n" + "="*70)
print("DEBUG MODE - Finding recursion source")
print("="*70 + "\n")

# Set recursion limit lower to fail faster
import sys
original_limit = sys.getrecursionlimit()
sys.setrecursionlimit(150)  # Much lower to catch it early
print(f"Recursion limit set to 150 (was {original_limit})")

try:
    print("\n1. Importing PySide6...")
    from PySide6.QtWidgets import QApplication
    print("   ✓ PySide6 imported")
    
    print("\n2. Creating QApplication...")
    app = QApplication(sys.argv)
    print("   ✓ QApplication created")
    
    print("\n3. Importing MainWindow...")
    from gui.main_window import MainWindow
    print("   ✓ MainWindow imported")
    
    print("\n4. Creating MainWindow instance...")
    window = MainWindow()
    print("   ✓ MainWindow created")
    
    print("\n5. Showing window...")
    window.show()
    print("   ✓ Window shown")
    
    print("\n✓ SUCCESS! App is running.\n")
    sys.exit(app.exec())
    
except RecursionError as e:
    print(f"\n\n{'='*70}")
    print("RECURSION ERROR CAUGHT!")
    print('='*70)
    
    # Get the traceback
    tb = traceback.format_exc()
    
    # Find the repeating pattern in the stack
    lines = tb.split('\n')
    
    print("\nFirst 20 lines of traceback:")
    print('\n'.join(lines[:20]))
    
    print("\n" + "="*70)
    print("ANALYSIS:")
    print("="*70)
    
    # Find which file/function is repeating
    file_counts = {}
    for line in lines:
        if 'File "' in line:
            # Extract filename
            start = line.find('File "') + 6
            end = line.find('"', start)
            if end > start:
                filename = line[start:end]
                file_counts[filename] = file_counts.get(filename, 0) + 1
    
    print("\nFiles appearing most in stack trace:")
    sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
    for filename, count in sorted_files[:5]:
        print(f"  {count:4d}x  {filename}")
    
    print("\n" + "="*70)
    
except Exception as e:
    print(f"\n\nOTHER ERROR: {e}\n")
    traceback.print_exc()