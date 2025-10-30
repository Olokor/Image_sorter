"""
TLP Photo App - Web-Based GUI Version with Authentication
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
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends, Cookie
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

# Initialize FastAPI app
app = FastAPI(title="Photo_Sorter App", version="1.0.0")

# Initialize service
app_service = EnhancedAppService()

# Setup directories
STATIC_DIR = CLIENT_DIR / "static"
TEMPLATES_DIR = CLIENT_DIR / "templates"
UPLOAD_DIR = CLIENT_DIR / "uploads"

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

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
    photographer = app_service.db_session.query(Photographer).get(photographer_id)
    
    if photographer and photographer.is_active:
        return photographer
    
    return None

def require_auth(session_token: Optional[str] = Cookie(None)):
    """Dependency to require authentication"""
    photographer = get_current_photographer(session_token)
    if not photographer:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return photographer


# ==================== AUTHENTICATION ROUTES ====================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login/Signup page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/api/auth/signup")
async def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: Optional[str] = Form(None)
):
    """Register new photographer"""
    # Check if email exists
    existing = app_service.db_session.query(Photographer).filter(
        Photographer.email == email
    ).first()
    
    if existing:
        return {"success": False, "message": "Email already registered"}
    
    # Create photographer
    photographer = Photographer(
        name=name,
        email=email,
        phone=phone,
        license_valid_until=datetime.utcnow() + timedelta(days=30)
    )
    photographer.set_password(password)
    
    app_service.db_session.add(photographer)
    app_service.db_session.commit()
    
    # Create session
    session_token = generate_session_token()
    active_sessions[session_token] = {
        'photographer_id': photographer.id,
        'created_at': datetime.utcnow(),
        'last_activity': datetime.utcnow()
    }
    
    # Update app_service
    app_service.current_photographer = photographer
    
    response = JSONResponse({
        "success": True,
        "message": "Account created successfully"
    })
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=30*24*60*60  # 30 days
    )
    
    return response

@app.post("/api/auth/login")
async def login(
    email: str = Form(...),
    password: str = Form(...)
):
    """Login photographer"""
    photographer = app_service.db_session.query(Photographer).filter(
        Photographer.email == email
    ).first()
    
    if not photographer or not photographer.check_password(password):
        return {"success": False, "message": "Invalid email or password"}
    
    if not photographer.is_active:
        return {"success": False, "message": "Account is deactivated"}
    
    # Update last login
    photographer.last_login = datetime.utcnow()
    app_service.db_session.commit()
    
    # Create session
    session_token = generate_session_token()
    active_sessions[session_token] = {
        'photographer_id': photographer.id,
        'created_at': datetime.utcnow(),
        'last_activity': datetime.utcnow()
    }
    
    # Update app_service
    app_service.current_photographer = photographer
    
    response = JSONResponse({
        "success": True,
        "message": "Login successful"
    })
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=30*24*60*60  # 30 days
    )
    
    return response

@app.post("/api/auth/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    """Logout photographer"""
    if session_token and session_token in active_sessions:
        del active_sessions[session_token]
    
    response = JSONResponse({"success": True, "message": "Logged out"})
    response.delete_cookie("session_token")
    return response

@app.get("/api/auth/me")
async def get_current_user(photographer: Photographer = Depends(get_current_photographer)):
    """Get current photographer info"""
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
        "sessions": sessions
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
    photographer: Photographer = Depends(require_auth)
):
    """Create new session"""
    session = app_service.create_session(name, location)
    return {
        "success": True,
        "session_id": session.id,
        "message": f"Session '{name}' created successfully"
    }


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
        "students": students
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
    """Enroll student with multiple photos"""
    session = app_service.get_active_session()
    if not session:
        raise HTTPException(400, "No active session")
    
    # Save uploaded photos
    photo_paths = []
    for photo in photos:
        safe_state_code = state_code.replace("/", "_").replace("\\", "_")
        safe_filename = photo.filename.replace("/", "_").replace("\\", "_")
        file_path = UPLOAD_DIR / f"{safe_state_code}_{safe_filename}"
        with open(file_path, "wb") as f:
            f.write(await photo.read())
        photo_paths.append(str(file_path))
    
    try:
        student = app_service.enroll_student_multiple_photos(
            state_code=state_code,
            full_name=full_name,
            reference_photo_paths=photo_paths,
            email=email or None,
            phone=phone or None,
            match_existing_photos=True
        )
        
        if not student:
            return {"success": False, "message": "Student already enrolled"}
        
        return {
            "success": True,
            "message": f"{full_name} enrolled successfully!",
            "student_id": student.id
        }
    except Exception as e:
        raise HTTPException(500, str(e))


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
        "session": session
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
        file_path = UPLOAD_DIR / photo.filename
        with open(file_path, "wb") as f:
            f.write(await photo.read())
        photo_paths.append(str(file_path))
    
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
        "students": students
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
            student = app_service.db_session.query(Student).get(face.student_id)
            
            # Get reference photo paths
            if student and student.reference_photo_path:
                ref_paths = student.reference_photo_path.split(',')
                reference_photos = [path.strip() for path in ref_paths if path.strip()]
        
        result.append({
            "id": face.id,
            "photo_id": face.photo_id,
            "photo_path": photo.thumbnail_path or photo.original_path if photo else None,
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
    student = app_service.db_session.query(Student).get(student_id)
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
        "session": session
    })


@app.get("/photo/{photo_id}")
async def serve_photo(photo_id: int, photographer: Photographer = Depends(require_auth)):
    """Serve photo file"""
    photo = app_service.db_session.query(Photo).get(photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    
    path = photo.thumbnail_path or photo.original_path
    if not os.path.exists(path):
        raise HTTPException(404, "Photo file not found")
    
    return FileResponse(path)


@app.get("/license", response_class=HTMLResponse)
async def license_page(request: Request, photographer: Photographer = Depends(require_auth)):
    """License page with proper session handling"""
    try:
        license_info = app_service.check_license()
        session = app_service.get_active_session()
        
        # Get photographer info
        photographer_data = photographer
        
        # If there's a session, calculate billing info
        billing_info = None
        if session:
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
            "license": license_info,
            "session": session,
            "billing": billing_info,
            "photographer": photographer_data
        })
    except Exception as e:
        print(f"License page error: {e}")
        # Return minimal page on error
        return templates.TemplateResponse("license.html", {
            "request": request,
            "license": {'valid': False, 'expires': 'Unknown', 'days_remaining': 0},
            "session": None,
            "billing": None,
            "photographer": photographer
        })


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
        "pending_requests": pending_requests
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
    if not hasattr(app_service, 'local_server'):
        app_service.local_server = ImprovedLocalServer(app_service, port=8000)
        if not app_service.local_server.is_running():
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
    if not hasattr(app_service, 'local_server'):
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
    if hasattr(app_service, 'local_server'):
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
    start_app(port=8080, open_browser_flag=True)