"""
Desktop App - Secure Authentication Service with API Key
Works with the secure hosted backend

IMPORTANT: Set these environment variables or hardcode them:
- PHOTOSORTER_API_URL (backend URL)
- DESKTOP_APP_API_KEY (from backend)
- REQUEST_SIGNING_KEY (optional, for request signing)
"""

import httpx
import json
import hashlib
import platform
import uuid
import hmac
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()
# ==================== CONFIGURATION ====================
API_BASE_URL = os.getenv("PHOTOSORTER_API_URL", "http://localhost:8001")
DESKTOP_APP_API_KEY = os.getenv("DESKTOP_APP_API_KEY")
REQUEST_SIGNING_KEY = os.getenv("REQUEST_SIGNING_KEY", "")  # Optional

LOCAL_CONFIG_PATH = Path.home() / ".photosorter" / "config.json"
LOCAL_DB_PATH = Path.home() / ".photosorter" / "auth.db"

Base = declarative_base()

class AuthToken(Base):
    """Store JWT tokens in local database"""
    __tablename__ = 'auth_tokens'
    
    id = Column(Integer, primary_key=True)
    token = Column(Text, nullable=False)
    user_email = Column(String(100), nullable=False)
    user_data = Column(Text)
    license_data = Column(Text)
    device_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    last_used = Column(DateTime, default=datetime.utcnow)
    is_valid = Column(Integer, default=1)


class SecureAuthService:
    """Enhanced authentication service with API key security"""
    
    def __init__(self):
        self.api_url = API_BASE_URL.rstrip("/")
        self.api_key = DESKTOP_APP_API_KEY
        self.signing_key = REQUEST_SIGNING_KEY
        
        self.token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.license_data: Optional[Dict] = None
        self.pending_email: Optional[str] = None
        self.password_hash: Optional[str] = None
        self.last_updated: Optional[datetime] = None
    
        self.device_fingerprint = self.generate_device_fingerprint()
        
        # Validate API key
        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            print("⚠️  WARNING: DESKTOP_APP_API_KEY not configured!")
            print("   Get the API key from your backend server")
            print("   Set it in environment variable: DESKTOP_APP_API_KEY")
        
        self._init_db()
        self.load_session()
        
        print(f"🔗 SecureAuthService initialized")
        print(f"   API: {self.api_url}")
        print(f"   API Key: {self.api_key[:10]}...{self.api_key[-4:]}")
        print(f"   Device: {self.device_fingerprint[:16]}...")
    
    def _init_db(self):
        """Initialize local SQLite database"""
        LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f'sqlite:///{LOCAL_DB_PATH}', echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()
    
    def generate_device_fingerprint(self) -> str:
        """Generate unique device fingerprint"""
        system = platform.system()
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()
        
        device_string = f"{system}|{machine}|{node}|{processor}"
        fingerprint = hashlib.sha256(device_string.encode()).hexdigest()
        return fingerprint
    
    def hash_password(self, password: str) -> str:
        """Hash password for local storage"""
        hasher = hashlib.sha256()
        hasher.update(password.encode('utf-8'))
        hasher.update(self.device_fingerprint.encode('utf-8'))
        return hasher.hexdigest()
    
    # In your auth_service.py
    def get_auth_headers(self, include_signature: bool = False, body: str = "") -> Dict[str, str]:
        """Get authentication headers with API key"""
        headers = {
            "X-API-Key": self.api_key,  # ← Make sure this is here
            "Content-Type": "application/json"
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def _save_token_to_db(self, token: str, user_data: Dict, license_data: Dict):
        """Save JWT token to local database"""
        try:
            # Invalidate old tokens
            self.db_session.query(AuthToken).filter(
                AuthToken.device_fingerprint == self.device_fingerprint,
                AuthToken.is_valid == 1
            ).update({"is_valid": 0})
            
            expires_at = datetime.utcnow() + timedelta(days=30)
            
            auth_token = AuthToken(
                token=token,
                user_email=user_data.get('email', ''),
                user_data=json.dumps(user_data),
                license_data=json.dumps(license_data) if license_data else None,
                device_fingerprint=self.device_fingerprint,
                expires_at=expires_at,
                last_used=datetime.utcnow()
            )
            
            self.db_session.add(auth_token)
            self.db_session.commit()
            
            print("✅ Token saved to local database")
        except Exception as e:
            print(f"❌ Error saving token: {e}")
            self.db_session.rollback()
    
    def _load_token_from_db(self) -> Optional[AuthToken]:
        """Load valid JWT token from local database"""
        try:
            auth_token = self.db_session.query(AuthToken).filter(
                AuthToken.device_fingerprint == self.device_fingerprint,
                AuthToken.is_valid == 1,
                AuthToken.expires_at > datetime.utcnow()
            ).order_by(AuthToken.created_at.desc()).first()
            
            if auth_token:
                auth_token.last_used = datetime.utcnow()
                self.db_session.commit()
                print("✅ Loaded valid token from database")
                return auth_token
            
            return None
        except Exception as e:
            print(f"❌ Error loading token: {e}")
            return None
    
    def _invalidate_token(self):
        """Invalidate current token"""
        try:
            if self.token:
                self.db_session.query(AuthToken).filter(
                    AuthToken.token == self.token,
                    AuthToken.device_fingerprint == self.device_fingerprint
                ).update({"is_valid": 0})
                self.db_session.commit()
                print("🗑️ Token invalidated")
        except Exception as e:
            print(f"❌ Error invalidating token: {e}")
    
    def get_last_updated(self) -> Optional[datetime]:
        """Get last update time"""
        return self.last_updated
    
    def save_session(self):
        """Save session to JSON (backward compatibility)"""
        try:
            LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            session_data = {
                "token": self.token,
                "user": self.user_data,
                "license": self.license_data,
                "pending_email": self.pending_email,
                "password_hash": self.password_hash,
                "device_fingerprint": self.device_fingerprint,
                "last_updated": self.last_updated.isoformat() if self.last_updated else None
            }
            
            with open(LOCAL_CONFIG_PATH, "w") as f:
                json.dump(session_data, f, indent=2)
            
            print("✅ Session saved to JSON")
        except Exception as e:
            print(f"❌ Error saving session: {e}")
    
    def load_session(self):
        """Load session from database or JSON"""
        # Try database first
        auth_token = self._load_token_from_db()
        
        if auth_token:
            self.token = auth_token.token
            self.user_data = json.loads(auth_token.user_data) if auth_token.user_data else None
            self.license_data = json.loads(auth_token.license_data) if auth_token.license_data else None
            self.last_updated = auth_token.last_used
            
            days_since = (datetime.utcnow() - self.last_updated).days if self.last_updated else 999
            print(f"📅 Last updated: {days_since} days ago")
            return
        
        # Fallback to JSON
        if LOCAL_CONFIG_PATH.exists():
            try:
                with open(LOCAL_CONFIG_PATH, "r") as f:
                    session_data = json.load(f)
                
                token = session_data.get("token")
                user_data = session_data.get("user")
                license_data = session_data.get("license")
                
                if token and user_data:
                    self._save_token_to_db(token, user_data, license_data or {})
                    self.token = token
                    self.user_data = user_data
                    self.license_data = license_data
                    self.pending_email = session_data.get("pending_email")
                    self.password_hash = session_data.get("password_hash")
                    
                    print("✅ Session migrated from JSON")
            except Exception as e:
                print(f"❌ Error loading JSON: {e}")
    
    def clear_session(self):
        """Clear session"""
        self._invalidate_token()
        
        self.token = None
        self.user_data = None
        self.license_data = None
        self.pending_email = None
        self.password_hash = None
        self.last_updated = None
        
        if LOCAL_CONFIG_PATH.exists():
            LOCAL_CONFIG_PATH.unlink()
    
    async def signup(self, name: str, email: str, password: str, phone: Optional[str] = None) -> Tuple[bool, str]:
        """Register new user"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "name": name,
                    "email": email,
                    "password": password,
                    "phone": phone
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/signup",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.pending_email = email
                self.save_session()
                return True, data.get("message", "OTP sent to your email")
            else:
                error = response.json()
                return False, error.get("detail", f"Signup failed ({response.status_code})")
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server. Is it running?"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def verify_email(self, email: str, otp_code: str) -> Tuple[bool, str]:
        """Verify email with OTP"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "email": email,
                    "otp_code": otp_code
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/verify-email",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                data = response.json()
                self.pending_email = None
                self.save_session()
                return True, data.get("message", "Email verified")
            else:
                error = response.json()
                return False, error.get("detail", "Verification failed")
        
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    async def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Login and get JWT token"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "email": email,
                    "password": password,
                    "device_fingerprint": self.device_fingerprint
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/login",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                data = response.json()
                
                self.token = data["access_token"]
                self.user_data = data["user"]
                self.license_data = data.get("license_status", {})
                self.pending_email = None
                self.last_updated = datetime.utcnow()
                
                # Save password hash for offline auth
                self.password_hash = self.hash_password(password)
                
                self._save_token_to_db(self.token, self.user_data, self.license_data)
                self.save_session()
                
                print(f"✅ Login successful")
                return True, "Login successful"
            else:
                error = response.json()
                return False, error.get("detail", "Login failed")
        
        except httpx.ConnectError:
            return False, "Cannot connect. Trying offline mode..."
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def local_login(self, email: str, password: str) -> Tuple[bool, str]:
        """Offline authentication"""
        if not self.password_hash or not self.user_data or not self.token:
            return False, "No saved session. Please login online first."
        
        if self.user_data.get("email", "").lower() != email.lower():
            return False, "Email doesn't match saved session."
        
        input_hash = self.hash_password(password)
        if input_hash != self.password_hash:
            return False, "Incorrect password."
        
        print("✅ Local login successful (offline mode)")
        return True, "Authenticated locally"
    
    async def resend_otp(self, email: str) -> Tuple[bool, str]:
        """Resend OTP"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({"email": email})
                
                response = await client.post(
                    f"{self.api_url}/auth/resend-otp",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                return True, "OTP sent"
            else:
                error = response.json()
                return False, error.get("detail", "Failed")
        
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def logout(self):
        """Logout"""
        self.clear_session()
        print("👤 Logged out")
    
    async def logout_remote(self) -> Tuple[bool, str]:
        """Logout from remote server (optional, notifies server)"""
        if not self.token:
            self.logout()
            return True, "Logged out locally"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/auth/logout",
                    headers=self.get_auth_headers()
                )
            
            if response.status_code == 200:
                self.logout()
                return True, "Logged out successfully"
            else:
                self.logout()
                return True, "Logged out locally"
        
        except Exception as e:
            self.logout()
            return True, "Logged out locally"
    
    

    async def forgot_password(self, email: str) -> Tuple[bool, str]:
        """Request password reset OTP"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "email": email
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/forgot-password",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "Password reset code sent to your email")
            else:
                error = response.json()
                return False, error.get("detail", f"Failed to send reset code ({response.status_code})")
        
        except httpx.ConnectError:
            return False, "Cannot connect to server. Is it running?"
        except Exception as e:
            return False, f"Connection error: {str(e)}"


    async def verify_reset_otp(self, email: str, otp_code: str) -> Tuple[bool, str, Optional[str]]:
        """
        Verify password reset OTP
        Returns: (success, message, reset_token)
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "email": email,
                    "otp_code": otp_code
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/verify-reset-otp",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                data = response.json()
                reset_token = data.get("reset_token")
                return True, data.get("message", "OTP verified successfully"), reset_token
            else:
                error = response.json()
                return False, error.get("detail", f"Verification failed ({response.status_code})"), None
        
        except httpx.ConnectError:
            return False, "Cannot connect to server. Is it running?", None
        except Exception as e:
            return False, f"Connection error: {str(e)}", None


    async def reset_password(self, reset_token: str, new_password: str) -> Tuple[bool, str]:
        """Reset password with verified token"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "reset_token": reset_token,
                    "new_password": new_password
                })
                
                response = await client.post(
                    f"{self.api_url}/auth/reset-password",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "Password reset successful")
            else:
                error = response.json()
                return False, error.get("detail", f"Password reset failed ({response.status_code})")
        
        except httpx.ConnectError:
            return False, "Cannot connect to server. Is it running?"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
        
    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return self.token is not None and self.user_data is not None
    
    def has_valid_license(self) -> bool:
        """Check if has valid license"""
        if not self.license_data:
            return False
        return self.license_data.get("valid", False)
    
    def get_students_available(self) -> int:
        """Get available students"""
        if not self.license_data:
            return 0
        return self.license_data.get("students_available", 0)
    
    async def get_license_status(self) -> Dict:
        """Get license status from server"""
        if not self.token:
            return {"valid": False, "message": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/license/status",
                    headers=self.get_auth_headers()
                )
            
            if response.status_code == 200:
                self.license_data = response.json()
                self.last_updated = datetime.utcnow()
                
                if self.user_data:
                    self._save_token_to_db(self.token, self.user_data, self.license_data)
                
                self.save_session()
                return self.license_data
            else:
                return {"valid": False, "message": "Failed to fetch"}
        
        except Exception as e:
            # Return cached data
            if self.license_data:
                return {**self.license_data, "cached": True, "message": "Cached (offline)"}
            return {"valid": False, "message": str(e)}
    
    async def initialize_license_purchase(self, student_count: int) -> Tuple[bool, Dict]:
        """Initialize license purchase"""
        if not self.token or not self.user_data:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = json.dumps({
                    "student_count": student_count,
                    "email": self.user_data["email"]
                })
                
                response = await client.post(
                    f"{self.api_url}/license/purchase/initialize",
                    headers=self.get_auth_headers(include_signature=True, body=body),
                    content=body
                )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                error = response.json()
                return False, {"error": error.get("detail", "Failed")}
        
        except Exception as e:
            return False, {"error": str(e)}
    
    async def verify_payment(self, reference: str) -> Tuple[bool, Dict]:
        """Verify payment"""
        if not self.token:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/license/verify/{reference}",
                    headers=self.get_auth_headers()
                )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    self.license_data = data.get("license")
                    self.last_updated = datetime.utcnow()
                    
                    if self.user_data:
                        self._save_token_to_db(self.token, self.user_data, self.license_data)
                    
                    self.save_session()
                
                return True, data
            else:
                error = response.json()
                return False, {"error": error.get("detail", "Failed")}
        
        except Exception as e:
            return False, {"error": str(e)}
    
    async def update_license_from_server(self) -> Tuple[bool, str]:
        """Update license from server"""
        if not self.token:
            return False, "Not authenticated"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/license/check",
                    headers=self.get_auth_headers(),
                    params={"device_fingerprint": self.device_fingerprint}
                )
            
            if response.status_code == 200:
                self.license_data = response.json()
                self.last_updated = datetime.utcnow()
                
                if self.user_data:
                    self._save_token_to_db(self.token, self.user_data, self.license_data)
                
                self.save_session()
                
                if self.license_data.get("valid"):
                    return True, f"License updated! {self.license_data['students_available']} students available"
                else:
                    return False, "No valid license"
            else:
                error = response.json()
                return False, error.get("detail", "Failed")
        
        except Exception as e:
            return False, str(e)


# Global instance
auth_service = SecureAuthService()