"""
TLP Photo App - Web-Based GUI Version
FastAPI + HTML/CSS/JS frontend
Can be bundled to .exe with PyInstaller
"""
import sys
import os
import webbrowser
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional

# Add client directory to path
CLIENT_DIR = Path(__file__).parent
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from services.app_service import EnhancedAppService
from models import Student, Photo, CampSession


# Initialize FastAPI app
app = FastAPI(title="TLP Photo App", version="1.0.0")

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


# ==================== API ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
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
async def get_sessions():
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
async def create_session(name: str = Form(...), location: str = Form("")):
    """Create new session"""
    session = app_service.create_session(name, location)
    return {
        "success": True,
        "session_id": session.id,
        "message": f"Session '{name}' created successfully"
    }


@app.post("/api/sessions/{session_id}/activate")
async def activate_session(session_id: int):
    """Set active session"""
    app_service.set_active_session(session_id)
    return {"success": True, "message": "Session activated"}


@app.get("/enroll", response_class=HTMLResponse)
async def enroll_page(request: Request):
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
    photos: List[UploadFile] = File(...)
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
async def get_students():
    """Get all students in current session"""
    students = app_service.get_students()
    return [{
        "id": s.id,
        "state_code": s.state_code,
        "full_name": s.full_name,
        "email": s.email,
        "phone": s.phone,
        "registered_at": s.registered_at.isoformat(),
        "photo_count": len(s.reference_photo_path.split(',')) if s.reference_photo_path else 0
    } for s in students]


@app.delete("/api/students/{student_id}")
async def delete_student(student_id: int):
    """Delete a student"""
    success = app_service.delete_student(student_id)
    if success:
        return {"success": True, "message": "Student deleted"}
    raise HTTPException(404, "Student not found")


@app.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    """Photo import page"""
    session = app_service.get_active_session()
    return templates.TemplateResponse("import.html", {
        "request": request,
        "session": session
    })


@app.post("/api/import")
async def import_photos(photos: List[UploadFile] = File(...)):
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
async def review_page(request: Request):
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
async def get_review_faces():
    """Get faces needing review"""
    faces = app_service.get_faces_needing_review()
    result = []
    
    for face in faces:
        photo = app_service.db_session.query(Photo).get(face.photo_id)
        student = None
        if face.student_id:
            student = app_service.db_session.query(Student).get(face.student_id)
        
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
                "state_code": student.state_code
            } if student else None
        })
    
    return result


@app.post("/api/review/{face_id}/confirm")
async def confirm_match(face_id: int, student_id: int = Form(...)):
    """Confirm face match"""
    app_service.confirm_match(face_id, student_id)
    return {"success": True, "message": "Match confirmed"}


@app.get("/share", response_class=HTMLResponse)
async def share_page(request: Request):
    """Share/QR page"""
    session = app_service.get_active_session()
    return templates.TemplateResponse("share.html", {
        "request": request,
        "session": session
    })


@app.get("/photo/{photo_id}")
async def serve_photo(photo_id: int):
    """Serve photo file"""
    photo = app_service.db_session.query(Photo).get(photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    
    path = photo.thumbnail_path or photo.original_path
    if not os.path.exists(path):
        raise HTTPException(404, "Photo file not found")
    
    return FileResponse(path)


@app.get("/license", response_class=HTMLResponse)
async def license_page(request: Request):
    """License page"""
    license_info = app_service.check_license()
    session = app_service.get_active_session()
    
    return templates.TemplateResponse("license.html", {
        "request": request,
        "license": license_info,
        "session": session,
        "photographer": app_service.current_photographer
    })


# ==================== STARTUP & SHUTDOWN ====================

def open_browser(port: int):
    """Open browser after a short delay"""
    time.sleep(1.5)  # Wait for server to start
    webbrowser.open(f'http://localhost:{port}')


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