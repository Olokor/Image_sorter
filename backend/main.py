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

import httpx
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

from app_service import EnhancedAppService
from models import Student, Photo, CampSession, Photographer, DownloadRequest
from license_manager import LicenseManager
from auth_service import auth_service

# Initialize FastAPI app
app = FastAPI(title="Photo_Sorter App", version="1.0.0")

# Initialize service
app_service = EnhancedAppService()

# Initialize license_manager globally
try:
    license_manager = LicenseManager()
    print(" License manager initialized")
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
    photographer = Photographer.get_or_none(Photographer.id == photographer_id)
    
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
    photographer = Photographer.select().where(Photographer.email == email).first()
    
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
# HELPER FUNCTIONS FOR BACKEND SYNC

async def sync_student_to_backend(state_code: str, full_name: str, enrolled_at: datetime):
    """
    Sync individual student enrollment to backend
    Returns dict with success status and updated license info
    """
    if not auth_service.is_authenticated() or not auth_service.token:
        return {"success": False, "message": "Not authenticated"}
    
    try:
        import httpx
        
        api_url = os.getenv("PHOTOSORTER_API_URL", "http://localhost:8001")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{api_url}/students/sync-enrollment",
                headers={
                    "Authorization": f"Bearer {auth_service.token}",
                    "X-API-Key": os.getenv("DESKTOP_APP_API_KEY"),
                    "Content-Type": "application/json"
                },
                json={
                    "student_state_code": state_code,
                    "student_name": full_name,
                    "enrolled_at": enrolled_at.isoformat()
                }
            )
        
        if response.status_code == 200:
            return response.json()
        else:
            error_detail = response.json().get("detail", "Unknown error")
            return {
                "success": False,
                "message": error_detail
            }
    
    except Exception as e:
        print(f"Backend sync error: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def queue_enrollment_for_sync(student_id: int, state_code: str, full_name: str):
    """
    Queue failed enrollment for later sync
    Store in local database for retry when connection is restored
    """
    try:
        from models import db
        
        # Create a simple sync queue table (add to models.py if needed)
        db.execute_sql("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                state_code TEXT,
                full_name TEXT,
                enrolled_at TEXT,
                synced INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        
        db.execute_sql("""
            INSERT INTO sync_queue (student_id, state_code, full_name, enrolled_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (student_id, state_code, full_name, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        
        print(f"OK Queued student {state_code} for sync retry")
    
    except Exception as e:
        print(f"Error queuing for sync: {e}")


# Background task to retry failed syncs
async def retry_pending_syncs():
    """
    Background task to retry failed enrollments
    Call this periodically or on app startup
    """
    try:
        from models import db
        
        cursor = db.execute_sql("""
            SELECT id, student_id, state_code, full_name, enrolled_at, retry_count
            FROM sync_queue
            WHERE synced = 0 AND retry_count < 5
            ORDER BY created_at ASC
            LIMIT 10
        """)
        
        pending = cursor.fetchall()
        
        for row in pending:
            queue_id, student_id, state_code, full_name, enrolled_at, retry_count = row
            
            result = await sync_student_to_backend(
                state_code=state_code,
                full_name=full_name,
                enrolled_at=datetime.fromisoformat(enrolled_at)
            )
            
            if result.get("success"):
                # Mark as synced
                db.execute_sql("""
                    UPDATE sync_queue SET synced = 1 WHERE id = ?
                """, (queue_id,))
                
                print(f"OK Retry successful: {state_code}")
            else:
                # Increment retry count
                db.execute_sql("""
                    UPDATE sync_queue SET retry_count = retry_count + 1 WHERE id = ?
                """, (queue_id,))
                
                print(f"WARNING Retry failed ({retry_count + 1}/5): {state_code}")
    
    except Exception as e:
        print(f"Error in retry_pending_syncs: {e}")
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
                    print(" Attempting background license refresh...")
                    try:
                        await auth_service.update_license_from_server()
                    except:
                        print(" Could not refresh license (offline mode)")
            except:
                pass
            
            # Get or create local photographer
            photographer = Photographer.select().where(Photographer.email == email).first()
            
            if photographer:
                photographer.last_login = datetime.utcnow()
                photographer.save()
                
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
    photographer = Photographer.select().where(Photographer.email == user_data['email']).first()
    
    if not photographer:
        password_hash = hash_password_local(password, email)
        
        photographer = Photographer.create(
            name=user_data['name'],
            email=user_data['email'],
            phone=user_data.get('phone'),
            password_hash=password_hash,
            is_active=True,
            last_login=datetime.utcnow(),
            current_session_student_count=0,
            total_students_registered=0
        )
    else:
        password_hash = hash_password_local(password, email)
        photographer.password_hash = password_hash
        photographer.is_active = True
        photographer.last_login = datetime.utcnow()
        photographer.save()
    
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

    print(f" JWT Token stored: {auth_service.token[:20]}...")
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


@router.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    """Request password reset OTP via hosted backend"""
    success, message = await auth_service.forgot_password(email)
    
    return {
        "success": success,
        "message": message
    }


@router.post("/verify-reset-otp")
async def verify_reset_otp(email: str = Form(...), otp_code: str = Form(...)):
    """Verify password reset OTP"""
    success, message, reset_token = await auth_service.verify_reset_otp(email, otp_code)
    
    return {
        "success": success,
        "message": message,
        "reset_token": reset_token
    }


@router.post("/reset-password")
async def reset_password(reset_token: str = Form(...), new_password: str = Form(...)):
    """Reset password with verified token"""
    success, message = await auth_service.reset_password(reset_token, new_password)
    
    return {
        "success": success,
        "message": message
    }


app.include_router(router)


@app.get("/api/sessions/{session_id}/view")
async def view_session(session_id: int, photographer: Photographer = Depends(require_auth)):
    """Set which session to VIEW (doesn't change active session)"""
    session = app_service.set_viewing_session(session_id)
    
    if not session:
        raise HTTPException(404, "Session not found")
    
    stats = app_service.get_session_stats()
    
    return {
        "success": True,
        "session": {
            "id": session.id,
            "name": session.name,
            "location": session.location,
            "is_active": session.is_active,
            "is_viewing": True
        },
        "stats": stats
    }


@app.get("/api/sessions/{session_id}/stats")
async def get_session_stats(session_id: int, photographer: Photographer = Depends(require_auth)):
    """Get statistics for a specific session"""
    stats = app_service.get_session_stats(session_id)
    
    if not stats:
        raise HTTPException(404, "Session not found")
    
    return stats


@app.get("/api/students")
async def get_students(
    session_id: Optional[int] = None,
    photographer: Photographer = Depends(require_auth)
):
    """Get students - optionally from specific session"""
    if session_id:
        # Use Peewee ORM syntax
        session = CampSession.get_or_none(CampSession.id == session_id)
        if not session:
            raise HTTPException(404, "Session not found")
    else:
        session = app_service.get_viewing_session()
    
    students = app_service.get_students(session)
    
    result = []
    for s in students:
        photos = app_service.get_student_photos(s)
        ref_photo_count = len(s.reference_photo_path.split(',')) if s.reference_photo_path else 0
        
        result.append({
            "id": s.id,
            "state_code": s.state_code,
            "full_name": s.full_name,
            "email": s.email,
            "phone": s.phone,
            "registered_at": s.registered_at.isoformat(),
            "photo_count": len(photos),
            "reference_photo_count": ref_photo_count,
            "total_downloads": s.total_downloads or 0,
            "session_id": s.session_id  # Include session info
        })
    
    return result

# ==================== LICENSE ROUTES WITH JWT ====================

license_router = APIRouter(prefix="/api/license", tags=["License"])


# ==================== AUTHENTICATION DEPENDENCY ====================

def require_auth():
    """Check if user is authenticated"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True


# ==================== LICENSE STATUS ====================

@license_router.get("/status")
async def get_license_status(_: bool = Depends(require_auth)):
    """Get current license status from auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"Using JWT token for license status: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    # Fetch latest from server using JWT
    license_data = await auth_service.get_license_status()
    return license_data


# ==================== PRICING ====================

@license_router.get("/pricing")
async def get_license_pricing():
    """Get current pricing from hosted backend (PUBLIC - no auth required)"""
    print(f"\n[PRICING] Fetching pricing from: {auth_service.api_url}/license/pricing")
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{auth_service.api_url}/license/pricing"
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"[PRICING] ✓ Fetched successfully: {data['price_per_student']} {data['currency']}")
                return data
            else:
                print(f"[PRICING] ✗ Server error: {response.status_code}")
                raise Exception(f"Server error: {response.status_code}")
                
    except Exception as e:
        print(f"[PRICING] ✗ Fetch failed: {e}")
        print(f"[PRICING] ⚠ Using fallback price: 200 NGN")
        # Fallback to default price
        return {
            "price_per_student": 200,
            "currency": "NGN",
            "validity_days": 30,
            "fallback": True
        }


# ==================== PAYMENT INITIALIZATION ====================

@license_router.post("/purchase/initialize")
async def initialize_license_purchase(
    student_count: int = Form(...),
    _: bool = Depends(require_auth)
):
    """Initialize license purchase via auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f" Using JWT token for payment init: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    success, data = await auth_service.initialize_license_purchase(student_count)
    
    if not success:
        raise HTTPException(status_code=400, detail=data.get("error", "Payment initialization failed"))
    
    # Ensure response has success field for frontend
    if "success" not in data:
        data["success"] = True
    
    # Include email in response for frontend use
    if "email" not in data and auth_service.user_data:
        data["email"] = auth_service.user_data.get("email")
    
    print(f"Payment init response: success={data.get('success')}, email={data.get('email')}, reference={data.get('reference')}")
    
    return data


# ==================== PAYMENT VERIFICATION ====================

@license_router.post("/verify-payment/{reference}")
async def verify_payment(
    reference: str,
    _: bool = Depends(require_auth)
):
    """Verify payment and activate license via auth_service with JWT"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    print(f"Using JWT token for payment verification: {auth_service.token[:20] if auth_service.token else 'None'}...")
    
    try:
        success, data = await auth_service.verify_payment(reference)
        
        if not success:
            raise HTTPException(
                status_code=400, 
                detail=data.get("error", "Verification failed")
            )
        
        # Ensure response has success field for frontend
        if "success" not in data:
            data["success"] = True
        
        return data
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Payment verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== UPDATE LICENSE FROM SERVER ====================

@license_router.post("/update-from-server")
async def update_license_from_server(_: bool = Depends(require_auth)):
    """
    Update license from hosted backend server
    Fetches latest license info and updates local data
    """
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        print("Updating license from server...")
        
        # Call auth_service method to update license
        success, message = await auth_service.update_license_from_server()
        
        if success:
            return {
                "success": True,
                "message": message,
                "license": auth_service.license_data
            }
        else:
            return {
                "success": False,
                "message": message
            }
    
    except Exception as e:
        print(f"Error updating license: {e}")
        return {
            "success": False,
            "message": f"Failed to update: {str(e)}"
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

# ==================== SHARE ROUTES ====================

@app.post("/api/share/create")
async def create_share_session(
    state_code: str = Form(...),
    expiry_hours: int = Form(24),
    download_limit: int = Form(50),
    photographer: Photographer = Depends(require_auth)
):
    """Create a share session for a student"""
    session = app_service.get_active_session()
    if not session:
        raise HTTPException(400, "No active session")

    # Search student
    student = app_service.search_student(state_code)
    if not student:
        raise HTTPException(404, "Student not found")

    # Ensure student has photos
    photos = app_service.get_student_photos(student)
    if not photos:
        raise HTTPException(400, "Student has no gallery photos")

    # Create local server for sharing if not started
    from local_server import ImprovedLocalServer
    if not hasattr(app_service, 'local_server') or app_service.local_server is None:
        app_service.local_server = ImprovedLocalServer(app_service, port=8001) # Use a diff port?
        if not app_service.local_server.is_running():
            app_service.local_server.start()
    elif not app_service.local_server.is_running():
         app_service.local_server.start()


    # Create share session
    session_uuid = app_service.local_server.create_share_session(
        student_id=student.id,
        expiry_hours=expiry_hours,
        download_limit=download_limit
    )

    share_url = app_service.local_server.get_share_url(session_uuid)

    # Generate QR Code (Base64)
    import qrcode, base64
    from io import BytesIO

    qr_img = qrcode.make(share_url)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "success": True,
        "session_uuid": session_uuid,
        "share_url": share_url,
        "qr_code": f"data:image/png;base64,{qr_base64}",
        "student": {
            "id": student.id,
            "name": student.full_name,
            "state_code": student.state_code,
            "photo_count": len(photos),
        }
    }


@app.get("/api/share/sessions")
async def get_share_sessions(photographer: Photographer = Depends(require_auth)):
    """Get all active share sessions"""
    if not hasattr(app_service, 'local_server') or app_service.local_server is None:
        return {"sessions": []}
    
    sessions_data = []
    for uuid, data in app_service.local_server.active_sessions.items():
        # Use Peewee ORM syntax
        student = Student.get_or_none(Student.id == data['student_id'])
        if student:
            sessions_data.append({
                "uuid": uuid,
                "student_name": student.full_name,
                "student_state_code": student.state_code,
                "created_at": data['created_at'].isoformat(),
                "expires_at": data['expires_at'].isoformat(),
                "downloads_used": data['downloads_used'],
                "download_limit": data['download_limit'],
                "access_count": data['access_count']
            })
    
    return {"sessions": sessions_data}


@app.delete("/api/share/sessions/{session_uuid}")
async def delete_share_session(
    session_uuid: str,
    photographer: Photographer = Depends(require_auth)
):
    """Delete a share session"""
    if hasattr(app_service, 'local_server') and app_service.local_server:
        if session_uuid in app_service.local_server.active_sessions:
            del app_service.local_server.active_sessions[session_uuid]
            return {"success": True, "message": "Share session deleted"}
    
    raise HTTPException(404, "Share session not found")




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
@app.post("/api/sessions/{session_id}/activate")
async def activate_session(session_id: int, photographer: Photographer = Depends(require_auth)):
    """Set active session"""
    app_service.set_active_session(session_id)
    return {"success": True, "message": "Session activated"}


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


@app.post("/api/enroll")
async def enroll_student(
    state_code: str = Form(...),
    full_name: str = Form(...),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    photos: List[UploadFile] = File(...),
    photographer: Photographer = Depends(require_auth)
):
    """Enroll student with backend sync"""
    
    # Verify photographer exists
    if not photographer:
        raise HTTPException(401, "Authentication required")
    
    # Check license first
    if not auth_service.has_valid_license():
        raise HTTPException(
            status_code=403,
            detail="No valid license found. Please purchase a license to enroll students."
        )
    
    if auth_service.get_students_available() <= 0:
        raise HTTPException(
            status_code=403,
            detail="Your license has 0 students available. Please purchase more students to continue."
        )
    
    session = app_service.get_active_session()
    if not session:
        raise HTTPException(400, "No active session")
    
    # Check student limit against available licenses
    available_students = auth_service.get_students_available()
    current_student_count = session.student_count
    
    if current_student_count >= available_students:
        raise HTTPException(
            status_code=403,
            detail=f"Student limit reached. You purchased license for {available_students} students. Please purchase more to enroll additional students."
        )
    
    try:
        # Save upload files temporarily
        photo_paths = []
        if not photos:
            raise HTTPException(400, "At least one reference photo is required.")

        for photo in photos:
            ext = Path(photo.filename).suffix if photo.filename else ".jpg"
            save_name = f"ref_{secrets.token_hex(8)}_{int(datetime.utcnow().timestamp())}{ext}"
            file_path = UPLOAD_DIR / save_name
            
            with open(file_path, "wb") as f:
                f.write(await photo.read())
            photo_paths.append(str(file_path))
        
        # Call the service layer
        student = app_service.enroll_student_multiple_photos(
            state_code=state_code,
            full_name=full_name,
            reference_photo_paths=photo_paths,
            email=email,
            phone=phone,
            match_existing_photos=True
        )
        
        # ==================== SYNC TO BACKEND ====================
        sync_success = False
        sync_error = None
        
        try:
            # Sync student enrollment to backend
            sync_result = await sync_student_to_backend(
                state_code=state_code,
                full_name=full_name,
                enrolled_at=datetime.utcnow()
            )
            
            if sync_result.get("success"):
                sync_success = True
                # Update local license data with new count
                auth_service.license_data = sync_result.get("license_status", {})
                auth_service.last_updated = datetime.utcnow()
                auth_service.save_session()
                
                print(f"SUCCESS Synced to backend. Students remaining: {sync_result.get('students_remaining')}")
            else:
                sync_error = sync_result.get("message", "Sync failed")
                print(f"WARNING Backend sync failed: {sync_error}")
        
        except Exception as e:
            sync_error = str(e)
            print(f"WARNING Backend sync error: {e}")
            # Don't fail enrollment if sync fails - queue for retry
            await queue_enrollment_for_sync(student.id, state_code, full_name)
        
        # Update photographer's student count tracking
        try:
            if photographer and hasattr(photographer, 'save'):
                photographer.current_session_student_count = (photographer.current_session_student_count or 0) + 1
                photographer.total_students_registered = (photographer.total_students_registered or 0) + 1
                photographer.save()
                print(f"Updated photographer count: session={photographer.current_session_student_count}, total={photographer.total_students_registered}")
        except Exception as e:
            print(f"Warning: Could not update photographer counts: {e}")
            # Don't fail enrollment if photographer update fails
        
        response_data = {
            "success": True,
            "message": f"Student '{student.full_name}' enrolled successfully.",
            "student_id": student.id,
            "synced_to_backend": sync_success
        }
        
        if not sync_success and sync_error:
            response_data["sync_warning"] = f"Enrollment successful but sync failed: {sync_error}. Will retry automatically."
        
        return response_data
        
    except Exception as e:
        print(f"Enrollment error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during enrollment: {str(e)}")



@app.get("/api/students")
async def get_students(photographer: Photographer = Depends(require_auth)):
    """Get all students in current session with actual photo counts"""
    students = app_service.get_students()
    
    result = []
    for s in students:
        # Get ACTUAL photo count from gallery (matched photos)
        photos = app_service.get_student_photos(s)
        actual_photo_count = len(photos)
        
        # Get reference photo count
        ref_photo_count = 0
        if s.reference_photo_path:
            ref_photo_count = len(s.reference_photo_path.split(','))
        
        result.append({
            "id": s.id,
            "state_code": s.state_code,
            "full_name": s.full_name,
            "email": s.email,
            "phone": s.phone,
            "registered_at": s.registered_at.isoformat(),
            "photo_count": actual_photo_count,  # Gallery photos (matched)
            "reference_photo_count": ref_photo_count,  # Enrollment photos
            "total_downloads": s.total_downloads or 0  # Total downloads
        })
    
    return result


@app.delete("/api/students/{student_id}")
async def delete_student(student_id: int, photographer: Photographer = Depends(require_auth)):
    """Delete a student"""
    # Use Peewee ORM syntax
    student = Student.get_or_none(Student.id == student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    
    if student.total_downloads > 0:
        raise HTTPException(
            403,
            "Cannot delete student who has downloaded photos. "
            "This counts toward your license usage."
        )
    success = app_service.delete_student(student_id)
    if success:
        return {"success": True, "message": "Student deleted"}
    raise HTTPException(404, "Student not found")


@app.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Photo import page"""
    session = app_service.get_active_session()
    return templates.TemplateResponse("import.html", {
        "request": request,
        "session": session,
        "photographer": photographer
    })


@app.post("/api/import")
async def import_photos(
    photos: List[UploadFile] = File(...),
    photographer: Photographer = Depends(require_auth)
):
    """Import and process photos"""
    session = app_service.get_active_session()
    if not session:
        raise HTTPException(400, "No active session")
    
    # Save photos
    photo_paths = []
    for photo in photos:
        # FIX: Ensure filename is safe
        if not photo.filename:
            continue
        safe_filename = f"import_{secrets.token_hex(8)}_{photo.filename.replace('..', '')}"
        file_path = UPLOAD_DIR / safe_filename
        try:
            with open(file_path, "wb") as f:
                f.write(await photo.read())
            photo_paths.append(str(file_path))
        except Exception as e:
            print(f"Error saving file {photo.filename}: {e}")
            
    if not photo_paths:
        raise HTTPException(400, "No valid photos were uploaded.")
    
    # Process photos
    results = app_service.import_photos(photo_paths)
    
    return {
        "success": True,
        "processed": results['processed'],
        "skipped": results['skipped'],
        "faces_detected": results['faces_detected'],
        "faces_matched": results['faces_matched']
    }


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Review matches page"""
    session = app_service.get_active_session()
    faces = app_service.get_faces_needing_review() if session else []
    students = app_service.get_students() if session else []
    
    return templates.TemplateResponse("review.html", {
        "request": request,
        "session": session,
        "faces": faces,
        "students": students,
        "photographer": photographer
    })


@app.get("/api/review/faces")
async def get_review_faces(photographer: Photographer = Depends(require_auth)):
    """Get faces needing review with reference photos"""
    faces = app_service.get_faces_needing_review()
    result = []
    
    for face in faces:
        # Use Peewee ORM syntax
        photo = Photo.get_or_none(Photo.id == face.photo_id)
        student = None
        reference_photos = []
        
        if face.student_id:
            student = Student.get_or_none(Student.id == face.student_id)
            
            # Get reference photo paths
            if student and student.reference_photo_path:
                ref_paths = student.reference_photo_path.split(',')
                # FIX: Use the API endpoint for reference photos
                reference_photos = [
                    f"/reference/{student.id}/{i}"
                    for i, path in enumerate(ref_paths) if path.strip()
                ]
        
        result.append({
            "id": face.id,
            "photo_id": face.photo_id,
            # FIX: Use the API endpoint for photos
            "photo_path": f"/photo/{photo.id}" if photo else None,
            "bbox": {
                "x": face.bbox_x,
                "y": face.bbox_y,
                "width": face.bbox_width,
                "height": face.bbox_height
            },
            "match_confidence": face.match_confidence,
            "suggested_student": {
                "id": student.id,
                "name": student.full_name,
                "state_code": student.state_code,
                "reference_photos": reference_photos
            } if student else None
        })
    
    return result


@app.get("/reference/{student_id}/{photo_index}")
async def serve_reference_photo(
    student_id: int,
    photo_index: int,
    photographer: Photographer = Depends(require_auth)
):
    """Serve student reference photo"""
    # Use Peewee ORM syntax
    student = Student.get_or_none(Student.id == student_id)
    if not student or not student.reference_photo_path:
        raise HTTPException(404, "Reference photo not found")
    
    ref_paths = student.reference_photo_path.split(',')
    ref_paths = [p.strip() for p in ref_paths if p.strip()]
    
    if photo_index >= len(ref_paths):
        raise HTTPException(404, "Photo index out of range")
    
    photo_path = ref_paths[photo_index]
    
    if not os.path.exists(photo_path):
        raise HTTPException(404, "Photo file not found")
    
    return FileResponse(photo_path)


@app.post("/api/review/{face_id}/confirm")
async def confirm_match(
    face_id: int,
    student_id: int = Form(...),
    photographer: Photographer = Depends(require_auth)
):
    """Confirm face match"""
    app_service.confirm_match(face_id, student_id)
    return {"success": True, "message": "Match confirmed"}


@app.get("/share", response_class=HTMLResponse)
async def share_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Share/QR page"""
    session = app_service.get_active_session()
    return templates.TemplateResponse("share.html", {
        "request": request,
        "session": session,
        "photographer": photographer
    })


@app.get("/photo/{photo_id}")
async def serve_photo(photo_id: int, thumbnail: bool = False, photographer: Photographer = Depends(require_auth)):
    """Serve photo file (thumbnail or original)"""
    # Use Peewee ORM syntax
    photo = Photo.get_or_none(Photo.id == photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    
    # Prioritize thumbnail if requested and available
    path = photo.thumbnail_path if thumbnail and photo.thumbnail_path else photo.original_path
    
    if not path or not os.path.exists(path):
         # Fallback to original if thumbnail is missing
        path = photo.original_path
        if not path or not os.path.exists(path):
            raise HTTPException(404, "Photo file not found")
    
    return FileResponse(path)



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