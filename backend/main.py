"""
Photo App - Web-Based GUI Version with JWT Authentication
Fixed JWT token management between frontend and backend
"""
import sys
import os, hashlib
import webbrowser
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional
import secrets

# Add client directory to path
CLIENT_DIR = Path(__file__).parent
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from services.app_service import EnhancedAppService
from models import Student, Photo, CampSession, Photographer, DownloadRequest
from services.license_manager import LicenseManager
from services.auth_service import auth_service

# Initialize FastAPI app
app = FastAPI(title="Photo_Sorter App", version="1.0.0")

# Initialize service
app_service = EnhancedAppService()

# Initialize license_manager globally
try:
    license_manager = LicenseManager()
    print("✓ License manager initialized")
except Exception as e:
    print(f"⚠ License manager initialization failed: {e}")
    license_manager = None

# Setup directories
STATIC_DIR = CLIENT_DIR / "static"
TEMPLATES_DIR = CLIENT_DIR / "templates"
UPLOAD_DIR = CLIENT_DIR / "uploads"

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ==================== MODELS ====================
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp_code: str

class ResendOTPRequest(BaseModel):
    email: EmailStr


# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Setup templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Session storage (in production, use Redis or database)
active_sessions = {}

def generate_session_token():
    """Generate secure session token"""
    return secrets.token_urlsafe(32)

def hash_password_local(password: str, salt: str = "") -> str:
    """Hash password for local storage (not sent to server)"""
    hasher = hashlib.sha256()
    hasher.update(password.encode('utf-8'))
    hasher.update(salt.encode('utf-8'))
    return hasher.hexdigest()

def get_current_photographer(session_token: Optional[str] = Cookie(None)):
    """Dependency to get current logged-in photographer"""
    if not session_token or session_token not in active_sessions:
        return None
    
    photographer_id = active_sessions[session_token]['photographer_id']
    photographer = app_service.db_session.get(Photographer, photographer_id)
    
    if photographer and photographer.is_active:
        return photographer
    
    return None

def require_auth(session_token: Optional[str] = Cookie(None)):
    """Dependency to require authentication"""
    # Check local cookie session first
    photographer = get_current_photographer(session_token)
    if photographer:
        return photographer
    
    # Check if auth_service has valid session
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # If auth_service is authenticated but no local session, create one
    email = auth_service.user_data.get('email')
    photographer = app_service.db_session.query(Photographer).filter_by(email=email).first()
    
    if not photographer:
        raise HTTPException(status_code=401, detail="Local photographer not found")
    
    return photographer

def require_license(min_students: int = 0):
    """Dependency to check if user has valid license"""
    def check():
        if not auth_service.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        if not auth_service.has_valid_license():
            raise HTTPException(
                status_code=403, 
                detail="Your license has expired. Please renew to continue."
            )
        
        available_students = auth_service.get_students_available()
        if min_students > 0 and available_students < min_students:
            raise HTTPException(
                status_code=403,
                detail=f"You need to purchase license for at least {min_students} students. Currently available: {available_students}"
            )
        
        return True
    
    return check

# ==================== AUTHENTICATION ROUTES ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login/Signup page"""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/signup")
async def signup(request: SignupRequest):
    """Register new user via hosted backend"""
    success, message = await auth_service.signup(
        name=request.name,
        email=request.email,
        password=request.password,
        phone=request.phone
    )
    
    return {
        "success": success,
        "message": message
    }

@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest):
    """Verify email with OTP"""
    success, message = await auth_service.verify_email(
        email=request.email,
        otp_code=request.otp_code
    )
    
    return {
        "success": success,
        "message": message
    }

@router.post("/resend-otp")
async def resend_otp(request: ResendOTPRequest):
    """Resend OTP"""
    success, message = await auth_service.resend_otp(request.email)
    
    return {
        "success": success,
        "message": message
    }

@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """Login via hosted backend OR local offline authentication"""
    email = request.email
    password = request.password
    
    # Try LOCAL authentication first (offline)
    if auth_service.is_authenticated() and auth_service.user_data.get('email', '').lower() == email.lower():
        success, message = auth_service.local_login(email, password)
        
        if success:
            # Local auth successful, try to refresh from server if needed
            try:
                last_updated = auth_service.get_last_updated()
                days_since_update = (datetime.utcnow() - last_updated).days if last_updated else 999
                
                if days_since_update > 7:
                    print("📡 Attempting background license refresh...")
                    try:
                        await auth_service.update_license_from_server()
                    except:
                        print("⚠️ Could not refresh license (offline mode)")
            except:
                pass
            
            # Get or create local photographer
            photographer = app_service.db_session.query(Photographer).filter_by(email=email).first()
            
            if photographer:
                photographer.last_login = datetime.utcnow()
                app_service.db_session.commit()
                
                # Create/update session cookie
                session_token = generate_session_token()
                active_sessions[session_token] = {
                    'photographer_id': photographer.id,
                    'created_at': datetime.utcnow(),
                    'students_at_login': photographer.current_session_student_count or 0
                }
                
                response.set_cookie(
                    key="session_token",
                    value=session_token,
                    httponly=True,
                    max_age=int(timedelta(days=30).total_seconds()),
                    samesite="Lax",
                    secure=False
                )
                
                return {
                    "success": True,
                    "message": "Login successful (offline mode)",
                    "user": auth_service.user_data,
                    "license": auth_service.license_data,
                    "offline_mode": True
                }
    
    # ONLINE authentication (backend)
    success, message = await auth_service.login(email=email, password=password)
    
    if not success:
        return {
            "success": False,
            "message": message
        }
    
    # Online login successful
    user_data = auth_service.user_data
    if not user_data:
        return {
            "success": False,
            "message": "Login successful but no user data returned."
        }

    # Get or create local photographer
    photographer = app_service.db_session.query(Photographer).filter_by(email=user_data['email']).first()
    
    if not photographer:
        password_hash = hash_password_local(password, email)
        
        photographer = Photographer(
            name=user_data['name'],
            email=user_data['email'],
            phone=user_data.get('phone'),
            password_hash=password_hash,
            is_active=True,
            last_login=datetime.utcnow(),
            current_session_student_count=0,
            total_students_registered=0
        )
        app_service.db_session.add(photographer)
        app_service.db_session.commit()
        app_service.db_session.refresh(photographer)
    else:
        password_hash = hash_password_local(password, email)
        photographer.password_hash = password_hash
        photographer.is_active = True
        photographer.last_login = datetime.utcnow()
        app_service.db_session.commit()
    
    # Create local session
    session_token = generate_session_token()
    active_sessions[session_token] = {
        'photographer_id': photographer.id,
        'created_at': datetime.utcnow(),
        'students_at_login': photographer.current_session_student_count or 0
    }

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=int(timedelta(days=30).total_seconds()),
        samesite="Lax",
        secure=False
    )

    print(f"✅ JWT Token stored: {auth_service.token[:20]}...")
    return {
        "success": True,
        "message": "Login successful",
        "user": auth_service.user_data,
        "license": auth_service.license_data,
        "offline_mode": False
    }

@router.post("/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout user"""
    auth_service.logout()
    response.delete_cookie(key="session_token")
    
    if session_token and session_token in active_sessions:
        del active_sessions[session_token]
    
    return {
        "success": True,
        "message": "Logged out successfully"
    }

@router.get("/me")
async def get_current_user_from_auth_service():
    """Get current logged-in user from auth_service"""
    if not auth_service.is_authenticated():
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "user": auth_service.user_data,
        "license": auth_service.license_data,
        "has_jwt": bool(auth_service.token)
    }

app.include_router(router)


# ==================== LICENSE ROUTES WITH JWT ====================

license_router = APIRouter(prefix="/api/license", tags=["License"])

@license_router.get("/status")
async def get_license_status(_: bool = Depends(require_auth)):
    """Get current license status from auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"🔑 Using JWT token for license status: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    # Fetch latest from server using JWT
    license_data = await auth_service.get_license_status()
    return license_data

@license_router.post("/purchase/initialize")
async def initialize_license_purchase(
    student_count: int = Form(...),
    _: bool = Depends(require_auth)
):
    """Initialize license purchase via auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"🔑 Using JWT token for payment init: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    success, data = await auth_service.initialize_license_purchase(student_count)
    
    if not success:
        raise HTTPException(status_code=400, detail=data.get("error", "Payment initialization failed"))
    
    return data

@license_router.post("/verify-payment/{reference}")
async def verify_payment(
    reference: str,
    _: bool = Depends(require_auth)
):
    """Verify payment and activate license via auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"🔑 Using JWT token for payment verification: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    success, data = await auth_service.verify_payment(reference)
    
    if not success:
        raise HTTPException(status_code=400, detail=data.get("error", "Verification failed"))
    
    return data

@license_router.post("/update-from-server")
async def update_license_from_server(_: bool = Depends(require_auth)):
    """Update license from server (after payment) via auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"🔑 Using JWT token for license update: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    success, message = await auth_service.update_license_from_server()
    
    return {
        "success": success,
        "message": message,
        "license": auth_service.license_data if success else None
    }

app.include_router(license_router)


# ==================== PROTECTED ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, photographer: Photographer = Depends(require_auth)):
    """Main dashboard page"""
    session = app_service.get_active_session()
    stats = app_service.get_session_stats() if session else {}
    sessions = app_service.get_all_sessions()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "session": session,
        "stats": stats,
        "sessions": sessions,
        "photographer": photographer
    })


@app.get("/api/sessions")
async def get_sessions(photographer: Photographer = Depends(require_auth)):
    """Get all sessions"""
    sessions = app_service.get_all_sessions()
    return [{
        "id": s.id,
        "name": s.name,
        "location": s.location,
        "start_date": s.start_date.isoformat(),
        "student_count": s.student_count,
        "is_active": s.is_active,
        "is_free_trial": s.is_free_trial
    } for s in sessions]


@app.post("/api/sessions")
async def create_session(
    name: str = Form(...),
    location: str = Form(""),
    photographer: Photographer = Depends(require_auth),
    _license_check: bool = Depends(require_license())
):
    """Create new session (requires valid license)"""
    if not auth_service.has_valid_license():
        raise HTTPException(
            status_code=403,
            detail="You need an active license to create a new session. Please purchase a license."
        )
    
    session = app_service.create_session(name, location)
    return {
        "success": True,
        "session_id": session.id,
        "message": f"Session '{name}' created successfully"
    }


@app.get("/license", response_class=HTMLResponse)
async def license_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Enhanced license page with payment integration"""
    try:
        # Get license info from auth service (will use JWT token)
        license_info = await auth_service.get_license_status()
        session = app_service.get_active_session()
        
        return templates.TemplateResponse("license.html", {
            "request": request,
            "license": license_info,
            "session": session,
            "photographer": photographer
        })
    except Exception as e:
        print(f"License page error: {e}")
        return templates.TemplateResponse("license.html", {
            "request": request,
            "license": {
                'authenticated': True,
                'license_valid': False,
                'message': str(e)
            },
            "session": None,
            "photographer": photographer
        })


# ==================== OTHER PROTECTED ROUTES ====================
# (enroll, import, review, share, etc. - all use require_auth dependency)

@app.get("/enroll", response_class=HTMLResponse)
async def enroll_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Student enrollment page"""
    session = app_service.get_active_session()
    students = app_service.get_students() if session else []
    
    return templates.TemplateResponse("enroll.html", {
        "request": request,
        "session": session,
        "students": students,
        "photographer": photographer
    })


# ==================== STARTUP & SHUTDOWN ====================

def open_browser(port: int):
    """Open browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{port}/login')


def start_app(port: int = 8080, open_browser_flag: bool = True):
    """Start the web application"""
    print("\n" + "="*70)
    print("TLP PHOTO APP - WEB VERSION WITH JWT AUTH")
    print("="*70)
    print(f"\n✓ Starting server on http://localhost:{port}")
    print(f"✓ JWT tokens stored in: {Path.home() / '.photosorter' / 'auth.db'}")
    print("✓ Browser will open automatically...")
    print("\n⚠ Press CTRL+C to stop the server\n")
    
    if open_browser_flag:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False
    )


if __name__ == "__main__":
    start_app(port=8080, open_browser_flag=True)