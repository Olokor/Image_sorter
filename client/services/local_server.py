"""
Fixed Local FastAPI Server with Correct IP Detection
Works on local network for external device access
"""
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Optional
from threading import Thread
import netifaces  # pip install netifaces

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from models import ShareSession, Student, Photo, StudentPhoto


class FixedLocalServer:
    """Local server with correct network IP detection"""
    
    def __init__(self, app_service, port=8000):
        self.app_service = app_service
        self.port = port
        self.server_thread = None
        self.running = False
        self.active_sessions = {}
        
        self.app = FastAPI(title="TLP Photo Share")
        self.setup_routes()
    
    def get_local_ip(self) -> str:
        """Get the correct local network IP address"""
        try:
            # Method 1: Try netifaces (most reliable)
            try:
                import netifaces
                
                # Get all network interfaces
                interfaces = netifaces.interfaces()
                
                # Priority order: Wi-Fi adapters, then Ethernet
                priority_prefixes = ['wlan', 'Wi-Fi', 'en', 'eth', 'Ethernet']
                
                for prefix in priority_prefixes:
                    for interface in interfaces:
                        if interface.lower().startswith(prefix.lower()):
                            try:
                                addrs = netifaces.ifaddresses(interface)
                                if netifaces.AF_INET in addrs:
                                    for addr_info in addrs[netifaces.AF_INET]:
                                        ip = addr_info.get('addr')
                                        if ip and not ip.startswith('127.'):
                                            print(f"  ✓ Found IP on {interface}: {ip}")
                                            return ip
                            except:
                                continue
            except ImportError:
                pass
            
            # Method 2: Socket method (fallback)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            try:
                # Connect to external address (doesn't actually send data)
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = '127.0.0.1'
            finally:
                s.close()
            
            if ip and not ip.startswith('127.'):
                return ip
            
            # Method 3: Get all IPs and filter
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]
            
            for ip in ip_list:
                if not ip.startswith('127.'):
                    return ip
            
            return '127.0.0.1'
            
        except Exception as e:
            print(f"  ⚠ IP detection error: {e}")
            return '127.0.0.1'
    
    def get_all_network_ips(self) -> list:
        """Get all available network IPs for display"""
        ips = []
        
        try:
            import netifaces
            
            for interface in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get('addr')
                            if ip and not ip.startswith('127.'):
                                ips.append({
                                    'interface': interface,
                                    'ip': ip
                                })
                except:
                    continue
        except ImportError:
            # Fallback
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]
            for ip in ip_list:
                if not ip.startswith('127.'):
                    ips.append({'interface': 'default', 'ip': ip})
        
        return ips
    
    def setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "TLP Photo Share Server",
                "status": "running",
                "server_ip": self.get_local_ip(),
                "port": self.port,
                "active_sessions": len(self.active_sessions)
            }
        
        @self.app.get("/student/{session_uuid}", response_class=HTMLResponse)
        async def student_gallery(session_uuid: str):
            """Student photo gallery"""
            if session_uuid not in self.active_sessions:
                raise HTTPException(status_code=404, detail="Session not found or expired")
            
            session_data = self.active_sessions[session_uuid]
            
            if datetime.utcnow() > session_data['expires_at']:
                del self.active_sessions[session_uuid]
                raise HTTPException(status_code=410, detail="Session expired")
            
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            student_id = session_data['student_id']
            student = self.app_service.db_session.query(Student).get(student_id)
            
            if not student:
                raise HTTPException(status_code=404, detail="Student not found")
            
            photos = self.app_service.get_student_photos(student)
            
            photo_cards = ""
            if photos:
                for photo in photos:
                    photo_cards += f"""
                    <div class="photo-card">
                        <img src="/photo/{photo.id}" alt="Photo" loading="lazy">
                        <div class="photo-actions">
                            <a href="/download/{photo.id}?session={session_uuid}" download>
                                <button class="download-btn">⬇ Download</button>
                            </a>
                        </div>
                    </div>
                    """
                gallery_html = f'<div class="gallery">{photo_cards}</div>'
            else:
                gallery_html = '<div class="no-photos"><h2>📷 No photos available yet</h2><p>Check back later!</p></div>'
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Photos for {student.full_name}</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta charset="UTF-8">
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
                        margin: 5px 0;
                    }}
                    .gallery {{
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                        gap: 20px;
                        margin-bottom: 30px;
                    }}
                    .photo-card {{
                        background: white;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                        transition: transform 0.3s, box-shadow 0.3s;
                    }}
                    .photo-card:hover {{
                        transform: translateY(-5px);
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    }}
                    .photo-card img {{
                        width: 100%;
                        height: 280px;
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
                    .download-btn:active {{
                        transform: scale(0.95);
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
                        padding: 80px 20px;
                        background: white;
                        border-radius: 15px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    }}
                    .no-photos h2 {{
                        color: #999;
                        margin-bottom: 10px;
                    }}
                    .no-photos p {{
                        color: #bbb;
                    }}
                    @media (max-width: 768px) {{
                        .gallery {{
                            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                            gap: 15px;
                        }}
                        .photo-card img {{
                            height: 220px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📷 Your Photos</h1>
                        <p class="info"><strong>{student.full_name}</strong></p>
                        <p class="info">State Code: {student.state_code}</p>
                        <p class="info">{len(photos)} photo(s) available</p>
                    </div>
                    
                    {gallery_html}
                    
                    <div class="footer">
                        <p class="stats">
                            📥 Downloads: {session_data['downloads_used']}/{session_data['download_limit']} | 
                            ⏰ Expires: {session_data['expires_at'].strftime('%Y-%m-%d %H:%M')}
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
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
            
            return FileResponse(path, media_type='image/jpeg')
        
        @self.app.get("/download/{photo_id}")
        async def download_photo(photo_id: int, session: str):
            """Download original photo"""
            if session not in self.active_sessions:
                raise HTTPException(status_code=403, detail="Invalid session")
            
            session_data = self.active_sessions[session]
            
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            if datetime.utcnow() > session_data['expires_at']:
                raise HTTPException(status_code=410, detail="Session expired")
            
            photo = self.app_service.db_session.query(Photo).get(photo_id)
            
            if not photo:
                raise HTTPException(status_code=404, detail="Photo not found")
            
            student_photo = self.app_service.db_session.query(StudentPhoto).filter_by(
                student_id=session_data['student_id'],
                photo_id=photo_id
            ).first()
            
            if not student_photo:
                raise HTTPException(status_code=403, detail="Photo not available")
            
            session_data['downloads_used'] += 1
            student_photo.download_count += 1
            self.app_service.db_session.commit()
            
            path = photo.original_path
            
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Photo file not found")
            
            return FileResponse(
                path,
                media_type='image/jpeg',
                filename=f"photo_{photo_id}.jpg"
            )
    
    def create_share_session(self, student_id: int, expiry_hours: int = 24, 
                           download_limit: int = 50) -> str:
        """Create share session"""
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
    
    def start(self):
        """Start server"""
        if self.running:
            return
        
        print(f"\n→ Starting local server on port {self.port}...")
        print(f"  Detecting network IP addresses...")
        
        all_ips = self.get_all_network_ips()
        if all_ips:
            print(f"\n  Available on:")
            for ip_info in all_ips:
                print(f"    • http://{ip_info['ip']}:{self.port} ({ip_info['interface']})")
        else:
            print(f"    • http://127.0.0.1:{self.port} (localhost only)")
        
        def run_server():
            config = uvicorn.Config(
                self.app,
                host="0.0.0.0",  # Listen on all interfaces
                port=self.port,
                log_level="warning",
                access_log=False
            )
            server = uvicorn.Server(config)
            server.run()
        
        self.server_thread = Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.running = True
    
    def stop(self):
        """Stop server"""
        self.running = False
    
    def is_running(self) -> bool:
        """Check if running"""
        return self.running
    
    def get_port(self) -> int:
        """Get port"""
        return self.port
    
    def get_share_url(self, session_uuid: str) -> str:
        """Get share URL"""
        return f"http://{self.get_local_ip()}:{self.port}/student/{session_uuid}"


# Alias
LocalServer = FixedLocalServer