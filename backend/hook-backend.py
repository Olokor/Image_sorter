"""
PyInstaller hook for backend module
Helps PyInstaller find all backend submodules
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Collect all backend modules
datas, binaries, hiddenimports = collect_all('backend')

# Also explicitly collect submodules
hiddenimports += collect_submodules('backend')

# Add common backend module patterns
backend_modules = [
    'backend',
    'backend.main',
    'backend.models',,
    'backend.services',
]
hiddenimports += [
    'backend.main',
    'backend.models', 
    'backend.face_service',
    'backend.services', # <-- EXPLICITLY ADDED THE PARENT PACKAGE HERE
    'backend.services.app_service',
    'backend.services.auth_service',
    'backend.services.license_manager',
    'backend.services.local_server',
]

# Collect any dynamic data/binaries from the 'backend' package
datas, binaries, hiddenimports2 = collect_all('backend')
hiddenimports += hiddenimports2

print(f"Hook: Found {len(hiddenimports)} hidden imports for backend")
print(f"Hook: Found {len(datas)} data files")