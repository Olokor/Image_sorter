"""
Local FastAPI Server - Runs in background for photo sharing
Serves photos and QR sessions over local Wi-Fi
"""
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Optional
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from models import ShareSession, Student, Photo, StudentPhoto


class LocalServer:
    """Manages local FastAPI server for photo sharing"""
    
    def __init__(self, app_service, port=8000):
        self.app_service = app_service
        self.port = port
        self.server_thread = None
        self.running = False
        
        # In-memory session store (for ephemeral sessions)
        self.active_sessions = {}
        
        # Create FastAPI app
        self.app = FastAPI(title="TLP Photo Share")
        self.setup_routes()
    
    def setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/")
        async def root():
            return {"message": "TLP Photo Share Server", "status": "running"}
        
        @self.app.get("/student/{session_uuid}", response_class=HTMLResponse)
        async def student_gallery(session_uuid: str):
            """Serve photo gallery for a student"""
            # Check if session exists
            if session_uuid not in self.active_sessions:
                raise HTTPException(status_code=404, detail="Session not found or expired")
            
            session_data = self.active_sessions[session_uuid]
            
            # Check expiry
            if datetime.utcnow() > session_data['expires_at']:
                del self.active_sessions[session_uuid]
                raise HTTPException(status_code=410, detail="Session expired")
            
            # Check download limit
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            # Get student and photos
            student_id = session_data['student_id']
            student = self.app_service.db_session.query(Student).get(student_id)
            
            if not student:
                raise HTTPException(status_code=404, detail="Student not found")
            
            photos = self.app_service.get_student_photos(student)
            
            # Generate HTML gallery
            photo_cards = ""
            if photos:
                for photo in photos:
                    photo_cards += f"""
                    <div class="photo-card">
                        <img src="/photo/{photo.id}" alt="Photo">
                        <div class="photo-actions">
                            <a href="/download/{photo.id}?session={session_uuid}" download>
                                <button class="download-btn">⬇ Download</button>
                            </a>
                        </div>
                    </div>
                    """
                gallery_html = f'<div class="gallery">{photo_cards}</div>'
            else:
                gallery_html = '<div class="no-photos"><h2>No photos available yet</h2></div>'
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Photos for {student.full_name}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 1200px;
                        margin: 0 auto;
                    }}
                    .header {{
                        background: white;
                        padding: 30px;
                        border-radius: 15px;
                        margin-bottom: 30px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                        text-align: center;
                    }}
                    h1 {{
                        color: #333;
                        font-size: 28px;
                        margin-bottom: 10px;
                    }}
                    .info {{
                        color: #666;
                        font-size: 14px;
                    }}
                    .gallery {{
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                        gap: 20px;
                        margin-bottom: 30px;
                    }}
                    .photo-card {{
                        background: white;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                        transition: transform 0.3s;
                    }}
                    .photo-card:hover {{
                        transform: translateY(-5px);
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    }}
                    .photo-card img {{
                        width: 100%;
                        height: 250px;
                        object-fit: cover;
                        display: block;
                    }}
                    .photo-actions {{
                        padding: 15px;
                        text-align: center;
                    }}
                    .download-btn {{
                        background: #667eea;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 8px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 600;
                        width: 100%;
                        transition: background 0.3s;
                        text-decoration: none;
                        display: inline-block;
                    }}
                    .download-btn:hover {{
                        background: #5568d3;
                    }}
                    .footer {{
                        background: white;
                        padding: 20px;
                        border-radius: 12px;
                        text-align: center;
                        box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    }}
                    .stats {{
                        color: #666;
                        font-size: 14px;
                    }}
                    .no-photos {{
                        text-align: center;
                        padding: 60px 20px;
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                        color: #999;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📷 Your Photos</h1>
                        <p class="info">{student.full_name} ({student.state_code})</p>
                        <p class="info">{len(photos)} photo(s) available</p>
                    </div>
                    
                    {gallery_html}
                    
                    <div class="footer">
                        <p class="stats">
                            Downloads used: {session_data['downloads_used']}/{session_data['download_limit']} | 
                            Expires: {session_data['expires_at'].strftime('%Y-%m-%d %H:%M')}
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Update access stats
            session_data['access_count'] += 1
            session_data['last_accessed'] = datetime.utcnow()
            
            return HTMLResponse(content=html)
        
        @self.app.get("/photo/{photo_id}")
        async def serve_photo(photo_id: int):
            """Serve photo thumbnail"""
            photo = self.app_service.db_session.query(Photo).get(photo_id)
            
            if not photo:
                raise HTTPException(status_code=404, detail="Photo not found")
            
            path = photo.thumbnail_path or photo.original_path
            
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Photo file not found")
            
            return FileResponse(path)
        
        @self.app.get("/download/{photo_id}")
        async def download_photo(photo_id: int, session: str):
            """Download original photo"""
            # Verify session
            if session not in self.active_sessions:
                raise HTTPException(status_code=403, detail="Invalid session")
            
            session_data = self.active_sessions[session]
            
            # Check limits
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            if datetime.utcnow() > session_data['expires_at']:
                raise HTTPException(status_code=410, detail="Session expired")
            
            # Get photo
            photo = self.app_service.db_session.query(Photo).get(photo_id)
            
            if not photo:
                raise HTTPException(status_code=404, detail="Photo not found")
            
            # Verify photo belongs to student
            student_photo = self.app_service.db_session.query(StudentPhoto).filter_by(
                student_id=session_data['student_id'],
                photo_id=photo_id
            ).first()
            
            if not student_photo:
                raise HTTPException(status_code=403, detail="Photo not available for this student")
            
            # Increment download counter
            session_data['downloads_used'] += 1
            student_photo.download_count += 1
            self.app_service.db_session.commit()
            
            path = photo.original_path
            
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Photo file not found")
            
            return FileResponse(
                path,
                media_type='image/jpeg',
                filename=f"{os.path.basename(path)}"
            )
    
    def create_share_session(self, student_id: int, expiry_hours: int = 24, 
                           download_limit: int = 50) -> str:
        """Create a new ephemeral share session"""
        session_uuid = str(uuid.uuid4())
        
        self.active_sessions[session_uuid] = {
            'student_id': student_id,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=expiry_hours),
            'download_limit': download_limit,
            'downloads_used': 0,
            'access_count': 0,
            'last_accessed': None
        }
        
        return session_uuid
    
    def get_session_info(self, session_uuid: str) -> Optional[dict]:
        """Get info about a share session"""
        return self.active_sessions.get(session_uuid)
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.utcnow()
        expired = [
            uuid for uuid, data in self.active_sessions.items()
            if now > data['expires_at']
        ]
        
        for uuid in expired:
            del self.active_sessions[uuid]
        
        return len(expired)
    
    def start(self):
        """Start the server in a background thread"""
        if self.running:
            return
        
        def run_server():
            config = uvicorn.Config(
                self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="warning"
            )
            server = uvicorn.Server(config)
            server.run()
        
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.running = True
    
    def stop(self):
        """Stop the server"""
        self.running = False
    
    def is_running(self) -> bool:
        """Check if server is running"""
        return self.running
    
    def get_port(self) -> int:
        """Get server port"""
        return self.port
    
    def get_local_ip(self) -> str:
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def get_share_url(self, session_uuid: str) -> str:
        """Get full URL for sharing"""
        return f"http://{self.get_local_ip()}:{self.port}/student/{session_uuid}"