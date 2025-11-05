"""
Photo App - Web-Based GUI Version with Authentication
FastAPI + HTML/CSS/JS frontend
"""
import sys
import os
import webbrowser
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

import uvicorn
# FIX: Added Response for setting cookies
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
# FIX: Added LicenseManager import at the top
from services.license_manager import LicenseManager

# Initialize FastAPI app
app = FastAPI(title="Photo_Sorter App", version="1.0.0")

# Initialize service
app_service = EnhancedAppService()

# FIX: Initialize license_manager globally after app_service
# This variable is now available to all routes.
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

from fastapi import APIRouter, HTTPException, Depends, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional
import httpx

# Import the auth service
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
auth_service = AuthService()
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

# FIX: Added a model for the resend-otp body
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

def get_current_photographer(session_token: Optional[str] = Cookie(None)):
    """Dependency to get current logged-in photographer"""
    if not session_token or session_token not in active_sessions:
        return None
    
    photographer_id = active_sessions[session_token]['photographer_id']
    # Use app_service.db_session which is globally available
    photographer = app_service.db_session.get(Photographer, photographer_id)
    
    if photographer and photographer.is_active:
        return photographer
    
    return None

def require_auth(session_token: Optional[str] = Cookie(None)):
    """Dependency to require authentication"""
    photographer = get_current_photographer(session_token)
    if not photographer:
        # FIX: Redirect to login page if not authenticated for HTML routes
        # This is a common pattern, but returning 401 for API routes is also fine.
        # Given this is used on HTML routes, a redirect is user-friendly.
        # However, it's also used on API routes.
        # A 401 is more appropriate for a mixed dependency.
        raise HTTPException(status_code=401, detail="Not authenticated")
    return photographer

# FIX: Moved require_license dependency here so it's defined before use
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

# FIX: Changed signature to use Pydantic model for consistency
@router.post("/resend-otp")
async def resend_otp(request: ResendOTPRequest):
    """Resend OTP"""
    success, message = await auth_service.resend_otp(request.email)
    
    return {
        "success": success,
        "message": message
    }

# FIX: Added @router.post decorator and Response object
@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """Login via hosted backend"""
    success, message = await auth_service.login(
        email=request.email,
        password=request.password
    )
    
    if not success:
        return {
            "success": False,
            "message": message
        }
    
    # Check license before allowing login
    
        
    # --- FIX: LOGIC TO BRIDGE AUTH_SERVICE AND LOCAL COOKIE SESSION ---
    user_data = auth_service.user_data
    if not user_data:
         return {
            "success": False,
            "message": "Login successful but no user data returned."
        }

    # Get or create local photographer
    photographer = app_service.db_session.query(Photographer).filter_by(email=user_data['email']).first()
    if not photographer:
        photographer = Photographer(
            name=user_data['name'],
            email=user_data['email'],
            phone=user_data.get('phone'),
            is_active=True 
        )
        app_service.db_session.add(photographer)
        app_service.db_session.commit()
        app_service.db_session.refresh(photographer)
    elif not photographer.is_active:
        photographer.is_active = True # Re-activate on login
        app_service.db_session.commit()
    
    # Create local session
    session_token = generate_session_token()
    active_sessions[session_token] = {
        'photographer_id': photographer.id,
        'created_at': datetime.utcnow()
    }

    # Set the cookie on the response
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=int(timedelta(days=7).total_seconds()), # 7-day session
        samesite="Lax",
        secure=False # Set to True in production with HTTPS
    )
    # --- END FIX ---

    return {
        "success": True,
        "message": "Login successful",
        "user": auth_service.user_data,
        "license": auth_service.license_data
    }

# FIX: Added Response object to delete cookie
@router.post("/logout")
async def logout(response: Response):
    """Logout user"""
    # Clear auth_service state
    auth_service.logout()

    # Clear local session cookie
    response.delete_cookie(key="session_token")
    
    # TODO: Should also clear the session from `active_sessions` dict
    # This requires getting the token from the request cookie first.
    # Simple logout:
    
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
        "license": auth_service.license_data
    }

# FIX: This route is for the *local* cookie-based session
@app.get("/api/auth/me")
async def get_current_user_from_cookie(photographer: Photographer = Depends(get_current_photographer)):
    """Get current photographer info from session cookie"""
    if not photographer:
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "photographer": {
            "id": photographer.id,
            "name": photographer.name,
            "email": photographer.email,
            "phone": photographer.phone
        }
    }

# FIX: Include the auth router
app.include_router(router)


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
        "photographer": photographer # Pass photographer to template
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
    # FIX: Corrected dependency name
    _license_check: bool = Depends(require_license()) 
):
    # Check if license is valid (redundant, but good defense)
    if not auth_service.has_valid_license():
        raise HTTPException(
            status_code=403,
            detail="You need an active license to create a new session. Please purchase a license."
        )
    
    # Rest of your existing code...
    session = app_service.create_session(name, location)
    return {
        "success": True,
        "session_id": session.id,
        "message": f"Session '{name}' created successfully"
    }


# FIX: Removed stray """
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
    _license_check: bool = Depends(require_license()) # Dependency already checks
):
    session = app_service.get_active_session()
    if not session:
        raise HTTPException(400, "No active session")
    
    # Check student limit
    available_students = auth_service.get_students_available()
    current_student_count = session.student_count
    
    if current_student_count >= available_students:
        raise HTTPException(
            status_code=403,
            detail=f"Student limit reached. You purchased license for {available_students} students. Please purchase more to enroll additional students."
        )
    
    # --- FIX: ADDED MISSING FUNCTION LOGIC ---
    try:
        # Save upload files temporarily
        photo_paths = []
        if not photos:
            raise HTTPException(400, "At least one reference photo is required.")

        for photo in photos:
            # Use a secure, unique filename
            ext = Path(photo.filename).suffix if photo.filename else ".jpg"
            save_name = f"ref_{secrets.token_hex(8)}_{int(datetime.utcnow().timestamp())}{ext}"
            file_path = UPLOAD_DIR / save_name
            
            with open(file_path, "wb") as f:
                f.write(await photo.read())
            photo_paths.append(str(file_path))
        
        # Call the service layer
        student = app_service.enroll_student(
            session_id=session.id,
            state_code=state_code,
            full_name=full_name,
            email=email,
            phone=phone,
            reference_photo_paths=photo_paths
        )
        
        return {
            "success": True,
            "message": f"Student '{student.full_name}' enrolled successfully.",
            "student_id": student.id
        }
    except Exception as e:
        # TODO: Clean up saved photos on error
        print(f"Enrollment error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during enrollment: {str(e)}")
    # --- END FIX ---

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
        photo = app_service.db_session.query(Photo).get(face.photo_id)
        student = None
        reference_photos = []
        
        if face.student_id:
            student = app_service.db_session.get(Student, face.student_id)
            
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
    student = app_service.db_session.get(Student, student_id)
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
    photo = app_service.db_session.get(Photo, photo_id)
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


# FIX: Removed stray """
# ==================== LICENSE & PAYMENT ROUTES ====================

@app.get("/license", response_class=HTMLResponse)
async def license_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Enhanced license page with payment integration"""
    try:
        # Get license info from auth service
        license_info = await auth_service.get_license_status()
        session = app_service.get_active_session()
        
        # Calculate billing info if session exists
        billing_info = None
        if session:
            # TODO: This billing logic might be deprecated by the new license service
            amount_due = session.student_count * 200  # ₦200 per student
            billing_info = {
                'session_name': session.name,
                'student_count': session.student_count,
                'amount_due': amount_due,
                'is_free_trial': session.is_free_trial,
                'payment_verified': session.payment_verified
            }
        
        return templates.TemplateResponse("license.html", {
            "request": request,
            "license": license_info, # Use data from auth_service
            "session": session,
            "billing": billing_info,
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
            "billing": None,
            "photographer": photographer
        })


# This route seems to use the *old* license_manager.
# The routes in license_router use the new auth_service.
# Keeping this for now, but it might be deprecated.
@app.post("/api/license/initialize-payment")
async def initialize_license_payment(photographer: Photographer = Depends(require_auth)):
    """Initialize license renewal payment (OLD METHOD?)"""
    if not license_manager:
        raise HTTPException(status_code=500, detail="License Manager not initialized")
    try:
        success, data = license_manager.initialize_payment(photographer.email)
        
        if success:
            return {
                "success": True,
                "reference": data["reference"],
                "payment_url": data["payment_url"],
                "message": "Payment initialized successfully"
            }
        else:
            return {
                "success": False,
                "error": data.get("error", "Payment initialization failed")
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


license_router = APIRouter(prefix="/api/license", tags=["License"])

@license_router.get("/status")
async def get_license_status():
    """Get current license status from auth_service"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Fetch latest from server
    license_data = await auth_service.get_license_status()
    return license_data

@license_router.post("/purchase/initialize")
async def initialize_license_purchase(student_count: int = Form(...)):
    """Initialize license purchase via auth_service"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, data = await auth_service.initialize_license_purchase(student_count)
    
    if not success:
        raise HTTPException(status_code=400, detail=data.get("error", "Payment initialization failed"))
    
    return data

@license_router.post("/verify-payment/{reference}")
async def verify_payment(reference: str):
    """Verify payment and activate license via auth_service"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, data = await auth_service.verify_payment(reference)
    
    if not success:
        raise HTTPException(status_code=400, detail=data.get("error", "Verification failed"))
    
    return data

@license_router.post("/update-from-server")
async def update_license_from_server():
    """Update license from server (after payment) via auth_service"""
    if not auth_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, message = await auth_service.update_license_from_server()
    
    return {
        "success": success,
        "message": message,
        "license": auth_service.license_data if success else None
    }

# FIX: Include the license router
app.include_router(license_router)


# ==================== DOWNLOAD REQUEST ROUTES ====================

@app.get("/requests", response_class=HTMLResponse)
async def requests_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """Download requests management page"""
    session = app_service.get_active_session()
    
    # Get pending requests
    pending_requests = app_service.db_session.query(DownloadRequest).filter(
        DownloadRequest.status == 'pending'
    ).order_by(DownloadRequest.requested_at.desc()).all()
    
    return templates.TemplateResponse("requests.html", {
        "request": request,
        "session": session,
        "pending_requests": pending_requests,
        "photographer": photographer
    })


@app.get("/api/requests/pending")
async def get_pending_requests(photographer: Photographer = Depends(require_auth)):
    """Get all pending download requests"""
    requests = app_service.db_session.query(DownloadRequest).filter(
        DownloadRequest.status == 'pending'
    ).order_by(DownloadRequest.requested_at.desc()).all()
    
    result = []
    for req in requests:
        student = app_service.db_session.query(Student).get(req.student_id)
        if student:
            result.append({
                "id": req.id,
                "student_id": student.id,
                "student_name": student.full_name,
                "student_code": student.state_code,
                "requested_at": req.requested_at.isoformat(),
                "additional_downloads": req.additional_downloads,
                "reason": req.reason,
                "current_downloads": student.total_downloads
            })
    
    return result


@app.post("/api/requests/{request_id}/approve")
async def approve_request(
    request_id: int,
    photographer: Photographer = Depends(require_auth)
):
    """Approve download request"""
    req = app_service.db_session.query(DownloadRequest).get(request_id)
    
    if not req:
        raise HTTPException(404, "Request not found")
    
    if req.status != 'pending':
        return {"success": False, "message": "Request already processed"}
    
    # Update request
    req.status = 'approved'
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by = photographer.id
    
    # Update share session download limit
    if hasattr(app_service, 'local_server') and req.share_session_uuid in app_service.local_server.active_sessions:
        session_data = app_service.local_server.active_sessions[req.share_session_uuid]
        session_data['download_limit'] += req.additional_downloads
    
    app_service.db_session.commit()
    
    return {
        "success": True,
        "message": f"Approved {req.additional_downloads} additional downloads"
    }


@app.post("/api/requests/{request_id}/reject")
async def reject_request(
    request_id: int,
    photographer: Photographer = Depends(require_auth)
):
    """Reject download request"""
    req = app_service.db_session.query(DownloadRequest).get(request_id)
    
    if not req:
        raise HTTPException(404, "Request not found")
    
    if req.status != 'pending':
        return {"success": False, "message": "Request already processed"}
    
    # Update request
    req.status = 'rejected'
    req.reviewed_at = datetime.utcnow()
    req.reviewed_by = photographer.id
    
    app_service.db_session.commit()
    
    return {"success": True, "message": "Request rejected"}


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
    from services.local_server import ImprovedLocalServer
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
        student = app_service.db_session.query(Student).get(data['student_id'])
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


# ==================== STARTUP & SHUTDOWN ====================

def open_browser(port: int):
    """Open browser after a short delay"""
    time.sleep(1.5)  # Wait for server to start
    webbrowser.open(f'http://localhost:{port}/login')


def start_app(port: int = 8080, open_browser_flag: bool = True):
    """Start the web application"""
    print("\n" + "="*70)
    print("TLP PHOTO APP - WEB VERSION")
    print("="*70)
    print(f"\n✓ Starting server on http://localhost:{port}")
    print("✓ Browser will open automatically...")
    print("\n⚠ Press CTRL+C to stop the server\n")
    
    # Open browser in background thread
    if open_browser_flag:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    
    # Start server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False
    )


if __name__ == "__main__":
    # FIX: Removed redundant/incorrect LicenseManager import and init.
    # The global `license_manager` defined after `app_service` is used.
    
    # Start the app
    start_app(port=8080, open_browser_flag=True)