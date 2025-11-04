

"""
Fixed Local Server with Canvas-Based Secure Image Rendering
Prevents image caching and unauthorized downloads
"""
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
import uvicorn

from models import Student, Photo, StudentPhoto, PhotoDownload, DownloadRequest


class ImprovedLocalServer:
    """Local server with robust network IP detection and secure image delivery"""
    
    def __init__(self, app_service, port=9000):
        self.app_service = app_service
        self.port = port
        self.server_thread = None
        self.running = False
        self.active_sessions = {}
        
        self.app = FastAPI(title="Photo Share")
        self.setup_routes()
    
    def get_all_local_ips(self) -> List[Dict[str, str]]:
        """
        Get ALL local network IPs using multiple methods
        Returns list of {interface, ip, type} dicts
        """
        ips = []
        
        # Method 1: netifaces (most reliable if installed)
        try:
            import netifaces
            
            for interface in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get('addr', '')
                            if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                                ips.append({
                                    'interface': interface,
                                    'ip': ip,
                                    'type': 'netifaces'
                                })
                except Exception:
                    continue
        except ImportError:
            print("  ⚠ netifaces not installed (pip install netifaces)")
        
        # Method 2: Windows ipconfig parsing
        if os.name == 'nt':  # Windows
            try:
                import subprocess
                result = subprocess.run(['ipconfig'], capture_output=True, text=True)
                output = result.stdout
                
                current_adapter = None
                for line in output.split('\n'):
                    line = line.strip()
                    
                    # Detect adapter name
                    if 'adapter' in line.lower() and ':' in line:
                        current_adapter = line.split(':')[0].strip()
                    
                    # Extract IPv4
                    if 'IPv4' in line and ':' in line:
                        ip = line.split(':')[1].strip()
                        # Remove any trailing info in parentheses
                        if '(' in ip:
                            ip = ip.split('(')[0].strip()
                        
                        if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                            # Check if already added
                            if not any(entry['ip'] == ip for entry in ips):
                                ips.append({
                                    'interface': current_adapter or 'Unknown',
                                    'ip': ip,
                                    'type': 'ipconfig'
                                })
            except Exception as e:
                print(f"  ⚠ ipconfig method failed: {e}")
        
        # Method 3: Socket connection method
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(('8.8.8.8', 80))  # Google DNS
            ip = s.getsockname()[0]
            s.close()
            
            if ip and not ip.startswith('127.') and not any(entry['ip'] == ip for entry in ips):
                ips.append({
                    'interface': 'Default Route',
                    'ip': ip,
                    'type': 'socket'
                })
        except Exception:
            pass
        
        # Method 4: gethostbyname
        try:
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]
            
            for ip in ip_list:
                if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                    if not any(entry['ip'] == ip for entry in ips):
                        ips.append({
                            'interface': 'gethostbyname',
                            'ip': ip,
                            'type': 'hostname'
                        })
        except Exception:
            pass
        
        return ips
    
    def get_best_ip(self) -> str:
        """
        Get the best IP address for external access
        Prioritizes: WiFi adapters > Ethernet > Others
        """
        all_ips = self.get_all_local_ips()
        
        if not all_ips:
            return '127.0.0.1'
        
        # Priority order for interfaces (case-insensitive)
        priority_keywords = [
            'wi-fi', 'wifi', 'wlan',  # Wireless
            'ethernet', 'eth',         # Wired
            'local',                   # Local Area Connection
        ]
        
        # Try to find best match
        for keyword in priority_keywords:
            for ip_info in all_ips:
                if keyword in ip_info['interface'].lower():
                    return ip_info['ip']
        
        # If no priority match, return first available
        return all_ips[0]['ip']
    
    def print_network_info(self):
        """Print all available network information"""
        print("\n" + "="*70)
        print("NETWORK CONFIGURATION")
        print("="*70)
        
        all_ips = self.get_all_local_ips()
        
        if not all_ips:
            print("  ⚠ No network interfaces found!")
            print("  ⚠ Server will only be accessible on localhost")
            return
        
        print(f"\n  Found {len(all_ips)} network interface(s):\n")
        
        for i, ip_info in enumerate(all_ips, 1):
            star = "⭐" if i == 1 else "  "
            print(f"  {star} {ip_info['interface']}")
            print(f"      IP: {ip_info['ip']}")
            print(f"      URL: http://{ip_info['ip']}:{self.port}")
            print(f"      Method: {ip_info['type']}\n")
        
        best_ip = self.get_best_ip()
        print("="*70)
        print(f"RECOMMENDED URL FOR SHARING:")
        print(f"  http://{best_ip}:{self.port}")
        print("="*70 + "\n")
    
    def setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/")
        async def root():
            all_ips = self.get_all_local_ips()
            return {
                "message": "TLP Photo Share Server",
                "status": "running",
                "primary_ip": self.get_best_ip(),
                "all_ips": [ip['ip'] for ip in all_ips],
                "port": self.port,
                "active_sessions": len(self.active_sessions)
            }
        
        @self.app.get("/student/{session_uuid}", response_class=HTMLResponse)
        async def student_gallery(session_uuid: str):
            """Student photo gallery page with canvas-based secure rendering"""
            if session_uuid not in self.active_sessions:
                return HTMLResponse(
                    content=self.error_page("Session Not Found", 
                                           "This link is invalid or has expired."),
                    status_code=404
                )
            
            session_data = self.active_sessions[session_uuid]
            
            # Check expiry
            if datetime.utcnow() > session_data['expires_at']:
                del self.active_sessions[session_uuid]
                return HTMLResponse(
                    content=self.error_page("Session Expired",
                                           "This sharing link has expired."),
                    status_code=410
                )
            
            # Check download limit
            if session_data['downloads_used'] >= session_data['download_limit']:
                return HTMLResponse(
                    content=self.error_page("Download Limit Reached",
                                           "This link has reached its download limit."),
                    status_code=403
                )
            
            student_id = session_data['student_id']
            student = self.app_service.db_session.query(Student).get(student_id)
            
            if not student:
                return HTMLResponse(
                    content=self.error_page("Student Not Found",
                                           "Student data not found."),
                    status_code=404
                )
            
            # Get student photos
            photos = self.app_service.get_student_photos(student)
            
            # Build gallery HTML with canvas security
            html = self.build_secure_gallery_page(student, photos, session_data, session_uuid)
            
            # Update access stats
            session_data['access_count'] += 1
            session_data['last_accessed'] = datetime.utcnow()
            
            return HTMLResponse(content=html)
        
        @self.app.get("/photo/{photo_id}")
        async def serve_photo(photo_id: int, session: str):
            """Serve photo with session validation - returns base64 for canvas rendering"""
            # Validate session
            if session not in self.active_sessions:
                raise HTTPException(status_code=403, detail="Invalid session")
            
            session_data = self.active_sessions[session]
            
            # Check expiry and limits
            if datetime.utcnow() > session_data['expires_at']:
                raise HTTPException(status_code=410, detail="Session expired")
            
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            photo = self.app_service.db_session.query(Photo).get(photo_id)
            
            if not photo:
                raise HTTPException(status_code=404, detail="Photo not found")
            
            # Verify student has access to this photo
            student_photo = self.app_service.db_session.query(StudentPhoto).filter_by(
                student_id=session_data['student_id'],
                photo_id=photo_id
            ).first()
            
            if not student_photo:
                raise HTTPException(status_code=403, detail="Photo not available")
            
            path = photo.thumbnail_path or photo.original_path
            
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Photo file not found")
            
            # Return image file with no-cache headers
            return FileResponse(
                path,
                media_type='image/jpeg',
                headers={
                    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
        
        @self.app.get("/download/{photo_id}")
        async def download_photo(photo_id: int, session: str):
            """Download original photo with watermark and tracking"""
            if session not in self.active_sessions:
                raise HTTPException(status_code=403, detail="Invalid session")
            
            session_data = self.active_sessions[session]
            
            # Check limits
            if session_data['downloads_used'] >= session_data['download_limit']:
                raise HTTPException(status_code=403, detail="Download limit reached")
            
            if datetime.utcnow() > session_data['expires_at']:
                raise HTTPException(status_code=410, detail="Session expired")
            
            photo = self.app_service.db_session.query(Photo).get(photo_id)
            
            if not photo:
                raise HTTPException(status_code=404, detail="Photo not found")
            
            # Verify student has access to this photo
            student_photo = self.app_service.db_session.query(StudentPhoto).filter_by(
                student_id=session_data['student_id'],
                photo_id=photo_id
            ).first()
            
            if not student_photo:
                raise HTTPException(status_code=403, detail="Photo not available")
            
            # Track download in PhotoDownload table
            photo_download = PhotoDownload(
                share_session_uuid=session,
                student_id=session_data['student_id'],
                photo_id=photo_id,
                downloaded_at=datetime.utcnow()
            )
            self.app_service.db_session.add(photo_download)
            
            # Update counters
            session_data['downloads_used'] += 1
            student_photo.download_count = (student_photo.download_count or 0) + 1
            
            # Update student total downloads
            student = self.app_service.db_session.query(Student).get(session_data['student_id'])
            if student:
                student.total_downloads = (student.total_downloads or 0) + 1
            
            self.app_service.db_session.commit()
            
            path = photo.original_path
            
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="Photo file not found")
            
            return FileResponse(
                path,
                media_type="image/jpeg",
                filename=f"photo_{photo_id}_{student.state_code}.jpg",
                headers={
                    "Content-Disposition": f"attachment; filename=photo_{photo_id}.jpg",
                    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                    'Pragma': 'no-cache'
                }
            )
        
        @self.app.post("/request-more-downloads")
        async def request_more_downloads(session: str, additional_downloads: int = 10, reason: str = ""):
            """Allow students to request more downloads"""
            if session not in self.active_sessions:
                raise HTTPException(status_code=403, detail="Invalid session")
            
            session_data = self.active_sessions[session]
            student_id = session_data['student_id']
            
            # Create download request
            download_request = DownloadRequest(
                student_id=student_id,
                share_session_uuid=session,
                requested_at=datetime.utcnow(),
                additional_downloads=additional_downloads,
                reason=reason,
                status='pending'
            )
            
            self.app_service.db_session.add(download_request)
            self.app_service.db_session.commit()
            
            return {
                "success": True,
                "message": "Request submitted. Please wait for photographer approval."
            }
    
    def build_secure_gallery_page(self, student, photos, session_data, session_uuid) -> str:
        """Build HTML gallery page with canvas-based secure rendering"""
        # Build photo data as JSON for JavaScript
        photo_data_json = "["
        if photos:
            photo_items = []
            for photo in photos:
                photo_items.append(f'{{"id": {photo.id}, "url": "/photo/{photo.id}?session={session_uuid}"}}')
            photo_data_json += ",".join(photo_items)
        photo_data_json += "]"
        
        # Check if near download limit
        downloads_remaining = session_data['download_limit'] - session_data['downloads_used']
        show_request_button = downloads_remaining < 10
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Photos for {student.full_name}</title>
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
                .alert {{
                    background: #fff3cd;
                    border: 1px solid #ffc107;
                    color: #856404;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .alert button {{
                    margin-top: 10px;
                    background: #ffc107;
                    color: #333;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    cursor: pointer;
                    font-weight: 600;
                }}
                .alert button:hover {{
                    background: #e0a800;
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
                    position: relative;
                }}
                .photo-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }}
                .photo-container {{
                    width: 100%;
                    height: 280px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: #f5f5f5;
                    position: relative;
                }}
                .photo-container canvas {{
                    max-width: 100%;
                    max-height: 100%;
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
                .loading {{
                    color: #999;
                    font-size: 14px;
                    text-align: center;
                    padding: 20px;
                }}
                @media (max-width: 768px) {{
                    .gallery {{
                        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                        gap: 15px;
                    }}
                    .photo-container {{
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
                
                {'<div class="alert">⚠️ You are running low on downloads (' + str(downloads_remaining) + ' remaining). <button onclick="requestMoreDownloads()">Request More Downloads</button></div>' if show_request_button else ''}
                
                <div class="gallery" id="gallery">
                    <div class="loading">Loading photos...</div>
                </div>
                
                <div class="footer">
                    <p class="stats">
                        📥 Downloads: {session_data['downloads_used']}/{session_data['download_limit']} | 
                        ⏰ Expires: {session_data['expires_at'].strftime('%Y-%m-%d %H:%M')}
                    </p>
                </div>
            </div>
            
            <script>
                // Disable right-click and common shortcuts
                document.addEventListener('contextmenu', e => e.preventDefault());
                document.addEventListener('keydown', e => {{
                    if (e.key === 'F12' || 
                        (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J')) ||
                        (e.ctrlKey && e.key === 'u')) {{
                        e.preventDefault();
                    }}
                }});
                
                const photos = {photo_data_json};
                const studentCode = '{student.state_code}';
                const sessionUUID = '{session_uuid}';
                
                function renderSecureImage(photoData, container) {{
                    const img = new Image();
                    img.crossOrigin = 'anonymous';
                    
                    img.onload = () => {{
                        const canvas = document.createElement('canvas');
                        const ctx = canvas.getContext('2d');
                        
                        const maxWidth = 280;
                        const maxHeight = 280;
                        let width = img.width;
                        let height = img.height;
                        
                        if (width > maxWidth || height > maxHeight) {{
                            const ratio = Math.min(maxWidth / width, maxHeight / height);
                            width = width * ratio;
                            height = height * ratio;
                        }}
                        
                        canvas.width = width;
                        canvas.height = height;
                        ctx.drawImage(img, 0, 0, width, height);
                        
                        ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
                        ctx.fillRect(width - 150, height - 40, 145, 35);
                        
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                        ctx.font = 'bold 12px Arial';
                        ctx.fillText(studentCode, width - 145, height - 20);
                        ctx.font = '10px Arial';
                        ctx.fillText(new Date().toLocaleString(), width - 145, height - 7);
                        
                        canvas.oncontextmenu = e => e.preventDefault();
                        canvas.ondragstart = e => e.preventDefault();
                        
                        container.innerHTML = '';
                        container.appendChild(canvas);
                    }};
                    
                    img.onerror = () => {{
                        container.innerHTML = '<div class="loading">Failed to load image</div>';
                    }};
                    
                    img.src = photoData.url;
                }}
                
                function buildGallery() {{
                    const gallery = document.getElementById('gallery');
                    
                    if (photos.length === 0) {{
                        gallery.innerHTML = '<div class="no-photos"><h2>📷 No photos available yet</h2><p>Check back later!</p></div>';
                        return;
                    }}
                    
                    gallery.innerHTML = '';
                    
                    photos.forEach(photo => {{
                        const card = document.createElement('div');
                        card.className = 'photo-card';
                        
                        const photoContainer = document.createElement('div');
                        photoContainer.className = 'photo-container';
                        photoContainer.innerHTML = '<div class="loading">Loading...</div>';
                        
                        const actions = document.createElement('div');
                        actions.className = 'photo-actions';
                        actions.innerHTML = '<a href="/download/' + photo.id + '?session=' + sessionUUID + '" download><button class="download-btn">⬇ Download Original</button></a>';
                        
                        card.appendChild(photoContainer);
                        card.appendChild(actions);
                        gallery.appendChild(card);
                        
                        renderSecureImage(photo, photoContainer);
                    }});
                }}
                
                async function requestMoreDownloads() {{
                    const reason = prompt('Why do you need more downloads? (optional)');
                    
                    try {{
                        const response = await fetch('/request-more-downloads?session=' + sessionUUID + '&additional_downloads=10&reason=' + encodeURIComponent(reason || ''), {{
                            method: 'POST'
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            alert('✓ ' + data.message);
                        }} else {{
                            alert('✗ Failed to submit request');
                        }}
                    }} catch (error) {{
                        alert('✗ Failed to submit request');
                    }}
                }}
                
                buildGallery();
            </script>
        </body>
        </html>
        """
        
        return html
    
    def error_page(self, title: str, message: str) -> str:
        """Build error page HTML"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                .error-box {{
                    background: white;
                    padding: 60px 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{
                    color: #e74c3c;
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
                h2 {{
                    color: #333;
                    font-size: 24px;
                    margin-bottom: 15px;
                }}
                p {{
                    color: #666;
                    font-size: 16px;
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            <div class="error-box">
                <h1>⚠️</h1>
                <h2>{title}</h2>
                <p>{message}</p>
            </div>
        </body>
        </html>
        """
    
    def create_share_session(self, student_id: int, expiry_hours: int = 24, 
                           download_limit: int = 50) -> str:
        """Create share session for student"""
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
        """Start server in background thread"""
        if self.running:
            print("  ⚠ Server already running")
            return
        
        print(f"\n→ Starting local server on port {self.port}...")
        
        # Print network info
        self.print_network_info()
        
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
        
        print("✓ Server started successfully!\n")
    
    def stop(self):
        """Stop server"""
        self.running = False
        print("  Server stopped")
    
    def is_running(self) -> bool:
        """Check if server is running"""
        return self.running
    
    def get_port(self) -> int:
        """Get server port"""
        return self.port
    
    def get_local_ip(self) -> str:
        """Get best local IP for sharing"""
        return self.get_best_ip()
    
    def get_share_url(self, session_uuid: str) -> str:
        """Get full share URL for QR code"""
        return f"http://{self.get_best_ip()}:{self.port}/student/{session_uuid}"


# Alias for backward compatibility
LocalServer = ImprovedLocalServer
FixedLocalServer = ImprovedLocalServer