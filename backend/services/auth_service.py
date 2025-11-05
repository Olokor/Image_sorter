"""
Local Desktop App - Enhanced Authentication Service with JWT Management
Properly stores and manages JWT tokens for authenticated requests
UPDATED: Added local database storage for JWT tokens and auto-refresh
"""

import httpx
import json
import hashlib
import platform
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configuration
API_BASE_URL = os.getenv("PHOTOSORTER_API_URL", "http://localhost:8001")
LOCAL_CONFIG_PATH = Path.home() / ".photosorter" / "config.json"
LOCAL_DB_PATH = Path.home() / ".photosorter" / "auth.db"

Base = declarative_base()

class AuthToken(Base):
    """Store JWT tokens in local database"""
    __tablename__ = 'auth_tokens'
    
    id = Column(Integer, primary_key=True)
    token = Column(Text, nullable=False)
    user_email = Column(String(100), nullable=False)
    user_data = Column(Text)  # JSON string
    license_data = Column(Text)  # JSON string
    device_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    last_used = Column(DateTime, default=datetime.utcnow)
    is_valid = Column(Integer, default=1)  # SQLite doesn't have boolean


class AuthService:
    """Handles authentication with hosted backend and secure local token storage"""
    
    def __init__(self):
        self.api_url = API_BASE_URL
        self.token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.license_data: Optional[Dict] = None
        self.pending_email: Optional[str] = None 
        self.password_hash: Optional[str] = None 
        self.last_updated: Optional[datetime] = None
        
        self.device_fingerprint = self.generate_device_fingerprint()
        
        # Initialize local database
        self._init_db()
        
        # Load saved session from database
        self.load_session()
        
        print(f"🔗 AuthService initialized - API URL: {self.api_url}")
        print(f"💾 Local DB: {LOCAL_DB_PATH}")
    
    def _init_db(self):
        """Initialize local SQLite database for storing auth tokens"""
        LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        engine = create_engine(f'sqlite:///{LOCAL_DB_PATH}', echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()
    
    def generate_device_fingerprint(self) -> str:
        """Generate unique device fingerprint based on system info"""
        system = platform.system()
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()
        
        device_string = f"{system}|{machine}|{node}|{processor}"
        fingerprint = hashlib.sha256(device_string.encode()).hexdigest()
        return fingerprint

    def hash_password(self, password: str) -> str:
        """One-way hash a password for secure local storage"""
        hasher = hashlib.sha256()
        hasher.update(password.encode('utf-8'))
        hasher.update(self.device_fingerprint.encode('utf-8')) 
        return hasher.hexdigest()
    
    def _save_token_to_db(self, token: str, user_data: Dict, license_data: Dict):
        """Save JWT token to local database"""
        try:
            # Invalidate old tokens for this device
            self.db_session.query(AuthToken).filter(
                AuthToken.device_fingerprint == self.device_fingerprint,
                AuthToken.is_valid == 1
            ).update({"is_valid": 0})
            
            # Calculate token expiry (30 days from now as per backend config)
            expires_at = datetime.utcnow() + timedelta(days=30)
            
            # Create new token record
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
            print(f"❌ Error saving token to database: {e}")
            self.db_session.rollback()
    
    def _load_token_from_db(self) -> Optional[AuthToken]:
        """Load valid JWT token from local database"""
        try:
            # Get most recent valid token for this device
            auth_token = self.db_session.query(AuthToken).filter(
                AuthToken.device_fingerprint == self.device_fingerprint,
                AuthToken.is_valid == 1,
                AuthToken.expires_at > datetime.utcnow()
            ).order_by(AuthToken.created_at.desc()).first()
            
            if auth_token:
                # Update last used timestamp
                auth_token.last_used = datetime.utcnow()
                self.db_session.commit()
                print("✅ Loaded valid token from database")
                return auth_token
            
            return None
        except Exception as e:
            print(f"❌ Error loading token from database: {e}")
            return None
    
    def _invalidate_token(self):
        """Invalidate current token in database"""
        try:
            if self.token:
                self.db_session.query(AuthToken).filter(
                    AuthToken.token == self.token,
                    AuthToken.device_fingerprint == self.device_fingerprint
                ).update({"is_valid": 0})
                self.db_session.commit()
                print("🗑️ Token invalidated in database")
        except Exception as e:
            print(f"❌ Error invalidating token: {e}")
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers with JWT token"""
        if not self.token:
            return {}
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def get_last_updated(self) -> Optional[datetime]:
        """Get the last time data was updated from server"""
        return self.last_updated
    
    def save_session(self):
        """Save auth session locally (legacy JSON file for backward compatibility)"""
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
            print("✅ Session saved to JSON file")
        except Exception as e:
            print(f"❌ Error saving session: {e}")
    
    def load_session(self):
        """Load saved auth session from database (primary) or JSON file (fallback)"""
        # Try loading from database first
        auth_token = self._load_token_from_db()
        
        if auth_token:
            self.token = auth_token.token
            self.user_data = json.loads(auth_token.user_data) if auth_token.user_data else None
            self.license_data = json.loads(auth_token.license_data) if auth_token.license_data else None
            self.last_updated = auth_token.last_used
            
            print("✅ Session loaded from database")
            
            # Calculate days since last update
            days_since_update = (datetime.utcnow() - self.last_updated).days if self.last_updated else 999
            print(f"📅 Last updated: {days_since_update} days ago")
            return
        
        # Fallback to JSON file (for migration from old system)
        if not LOCAL_CONFIG_PATH.exists():
            return
        
        try:
            with open(LOCAL_CONFIG_PATH, "r") as f:
                session_data = json.load(f)
            
            token = session_data.get("token")
            user_data = session_data.get("user")
            license_data = session_data.get("license")
            
            if token and user_data:
                # Migrate to database
                self._save_token_to_db(token, user_data, license_data or {})
                
                self.token = token
                self.user_data = user_data
                self.license_data = license_data
                self.pending_email = session_data.get("pending_email")
                self.password_hash = session_data.get("password_hash")
                
                last_updated_str = session_data.get("last_updated")
                if last_updated_str:
                    try:
                        self.last_updated = datetime.fromisoformat(last_updated_str)
                    except:
                        self.last_updated = None
                
                print("✅ Session migrated from JSON to database")
                
        except Exception as e:
            print(f"❌ Error loading session from JSON: {e}")
    
    def clear_session(self):
        """Clear local session variables and invalidate token"""
        self._invalidate_token()
        
        self.token = None
        self.user_data = None
        self.license_data = None
        self.pending_email = None 
        self.password_hash = None
        self.last_updated = None
        
        if LOCAL_CONFIG_PATH.exists():
            try:
                LOCAL_CONFIG_PATH.unlink()
                print("🧹 Local config file deleted.")
            except Exception as e:
                print(f"❌ Could not delete config file: {e}")
    
    async def signup(self, name: str, email: str, password: str, phone: Optional[str] = None) -> Tuple[bool, str]:
        """Register new user (contacts backend)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/auth/signup",
                    json={
                        "name": name,
                        "email": email,
                        "password": password,
                        "phone": phone
                    }
                )
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.pending_email = email
                self.save_session()
                return True, data.get("message", "OTP sent to your email")
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", f"Signup failed (HTTP {response.status_code})")
                except:
                    return False, f"Signup failed - Server returned {response.status_code}"
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server at {self.api_url}. Is the backend running?"
        except httpx.TimeoutException:
            return False, "Connection timeout. Please check your internet connection."
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def verify_email(self, email: str, otp_code: str) -> Tuple[bool, str]:
        """Verify email with OTP (contacts backend)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/auth/verify-email",
                    json={
                        "email": email,
                        "otp_code": otp_code
                    }
                )
            
            if response.status_code == 200:
                data = response.json()
                self.pending_email = None
                self.save_session()
                return True, data.get("message", "Email verified! Please login.")
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", "Verification failed")
                except:
                    return False, f"Verification failed (HTTP {response.status_code})"
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server at {self.api_url}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Login and get JWT token (contacts backend)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/auth/login",
                    json={
                        "email": email,
                        "password": password,
                        "device_fingerprint": self.device_fingerprint
                    }
                )
            
            if response.status_code == 200:
                data = response.json()
                
                self.token = data["access_token"]
                self.user_data = data["user"]
                self.license_data = data.get("license_status", {})
                self.pending_email = None
                self.last_updated = datetime.utcnow()
                
                # Save the local hash of the password for OFFLINE AUTH
                self.password_hash = self.hash_password(password)
                
                # Save to database AND JSON file
                self._save_token_to_db(self.token, self.user_data, self.license_data)
                self.save_session()
                
                print(f"✅ Login successful - Token saved")
                return True, "Login successful"
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", "Login failed")
                except:
                    return False, f"Login failed (HTTP {response.status_code})"
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server at {self.api_url}. Trying offline mode..."
        except httpx.TimeoutException:
            return False, "Connection timeout. Trying offline mode..."
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def local_login(self, email: str, password: str) -> Tuple[bool, str]:
        """Authenticate locally using stored password hash"""
        if not self.password_hash or not self.user_data or not self.token:
            return False, "No saved session found. Please log in online first."
        
        if self.user_data.get("email", "").lower() != email.lower():
            return False, "Email does not match saved session."
            
        input_hash = self.hash_password(password)
        if input_hash != self.password_hash:
            return False, "Incorrect password."

        print("✅ Local login successful. Operating in offline mode.")
        return True, "Authenticated locally (offline mode)"
    
    async def resend_otp(self, email: str) -> Tuple[bool, str]:
        """Resend OTP"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/auth/resend-otp",
                    json={"email": email}
                )
            
            if response.status_code == 200:
                return True, "OTP sent to your email"
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", "Failed to send OTP")
                except:
                    return False, f"Failed (HTTP {response.status_code})"
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server at {self.api_url}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def logout(self):
        """Logout and clear session"""
        self.clear_session()
        print("👤 Logged out successfully.")
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.token is not None and self.user_data is not None
    
    def has_valid_license(self) -> bool:
        """Check if user has valid license"""
        if not self.license_data:
            return False
        return self.license_data.get("valid", False)
    
    def get_students_available(self) -> int:
        """Get number of students user can enroll"""
        if not self.license_data:
            return 0
        return self.license_data.get("students_available", 0)
    
    async def get_license_status(self) -> Dict:
        """Get current license status from server with JWT auth"""
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
                
                # Update license data in database
                if self.user_data:
                    self._save_token_to_db(self.token, self.user_data, self.license_data)
                
                self.save_session()
                return self.license_data
            else:
                return {"valid": False, "message": "Failed to fetch license"}
        
        except Exception as e:
            # Return cached data if available
            if self.license_data:
                return {**self.license_data, "cached": True, "message": "Using cached license data (offline)"}
            return {"valid": False, "message": f"Connection error: {str(e)}"}
    
    async def initialize_license_purchase(self, student_count: int) -> Tuple[bool, Dict]:
        """Initialize license purchase with JWT auth"""
        if not self.token or not self.user_data:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/license/purchase/initialize",
                    headers=self.get_auth_headers(),
                    json={
                        "student_count": student_count,
                        "email": self.user_data["email"]
                    }
                )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                try:
                    error = response.json()
                    return False, {"error": error.get("detail", "Payment initialization failed")}
                except:
                    return False, {"error": f"Failed (HTTP {response.status_code})"}
        
        except Exception as e:
            return False, {"error": f"Connection error: {str(e)}"}
    
    async def verify_payment(self, reference: str) -> Tuple[bool, Dict]:
        """Verify payment and activate license with JWT auth"""
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
                    
                    # Update in database
                    if self.user_data:
                        self._save_token_to_db(self.token, self.user_data, self.license_data)
                    
                    self.save_session()
                
                return True, data
            else:
                try:
                    error = response.json()
                    return False, {"error": error.get("detail", "Verification failed")}
                except:
                    return False, {"error": f"Failed (HTTP {response.status_code})"}
        
        except Exception as e:
            return False, {"error": f"Connection error: {str(e)}"}
    
    async def update_license_from_server(self) -> Tuple[bool, str]:
        """Update license from server with JWT auth"""
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
                
                # Update in database
                if self.user_data:
                    self._save_token_to_db(self.token, self.user_data, self.license_data)
                
                self.save_session()
                
                if self.license_data.get("valid"):
                    return True, f"License updated! {self.license_data['students_available']} students available"
                else:
                    return False, "No valid license found"
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", "Failed to update license")
                except:
                    return False, f"Failed (HTTP {response.status_code})"
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"


# Global instance
auth_service = AuthService()