import sys
import os
import warnings
warnings.filterwarnings('ignore')

# Fix InsightFace import when frozen
if getattr(sys, 'frozen', False):
    # Add site-packages style path
    base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    sys.path.insert(0, base)
