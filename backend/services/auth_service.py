"""
Local Desktop App - Authentication Service
Connects to hosted backend for auth and licensing
"""

import httpx
import json
import hashlib
import platform
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

# Configuration
API_BASE_URL = "https://api.photosorter.com"  # Your hosted backend URL
LOCAL_CONFIG_PATH = Path.home() / ".photosorter" / "config.json"

class AuthService:
    """Handles authentication with hosted backend"""
    
    def __init__(self):
        self.api_url = API_BASE_URL
        self.token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.license_data: Optional[Dict] = None
        self.device_fingerprint = self.generate_device_fingerprint()
        
        # Load saved session
        self.load_session()
    
    def generate_device_fingerprint(self) -> str:
        """Generate unique device fingerprint"""
        system = platform.system()
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()
        
        # Combine system info
        device_string = f"{system}|{machine}|{node}|{processor}"
        
        # Hash for privacy
        fingerprint = hashlib.sha256(device_string.encode()).hexdigest()
        return fingerprint
    
    def save_session(self):
        """Save auth session locally"""
        LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        session_data = {
            "token": self.token,
            "user": self.user_data,
            "license": self.license_data,
            "device_fingerprint": self.device_fingerprint,
            "last_updated": datetime.utcnow().isoformat()
        }
        
        with open(LOCAL_CONFIG_PATH, "w") as f:
            json.dump(session_data, f, indent=2)
    
    def load_session(self):
        """Load saved auth session"""
        if not LOCAL_CONFIG_PATH.exists():
            return
        
        try:
            with open(LOCAL_CONFIG_PATH, "r") as f:
                session_data = json.load(f)
            
            self.token = session_data.get("token")
            self.user_data = session_data.get("user")
            self.license_data = session_data.get("license")
            
            # Verify device fingerprint matches
            saved_fp = session_data.get("device_fingerprint")
            if saved_fp != self.device_fingerprint:
                print("⚠️ Device fingerprint mismatch. Please login again.")
                self.clear_session()
        except Exception as e:
            print(f"Error loading session: {e}")
    
    def clear_session(self):
        """Clear local session"""
        self.token = None
        self.user_data = None
        self.license_data = None
        
        if LOCAL_CONFIG_PATH.exists():
            LOCAL_CONFIG_PATH.unlink()
    
    async def signup(self, name: str, email: str, password: str, phone: Optional[str] = None) -> Tuple[bool, str]:
        """Register new user"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/auth/signup",
                    json={
                        "name": name,
                        "email": email,
                        "password": password,
                        "phone": phone
                    },
                    timeout=30.0
                )
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "OTP sent to your email")
            else:
                error = response.json()
                return False, error.get("detail", "Signup failed")
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def verify_email(self, email: str, otp_code: str) -> Tuple[bool, str]:
        """Verify email with OTP"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/auth/verify-email",
                    json={
                        "email": email,
                        "otp_code": otp_code
                    },
                    timeout=30.0
                )
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "Email verified!")
            else:
                error = response.json()
                return False, error.get("detail", "Verification failed")
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def resend_otp(self, email: str) -> Tuple[bool, str]:
        """Resend OTP"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/auth/resend-otp",
                    params={"email": email},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                return True, "OTP sent to your email"
            else:
                error = response.json()
                return False, error.get("detail", "Failed to send OTP")
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Login and get JWT token"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/auth/login",
                    json={
                        "email": email,
                        "password": password,
                        "device_fingerprint": self.device_fingerprint
                    },
                    timeout=30.0
                )
            
            if response.status_code == 200:
                data = response.json()
                
                self.token = data["access_token"]
                self.user_data = data["user"]
                self.license_data = data["license_status"]
                
                # Save session
                self.save_session()
                
                return True, "Login successful"
            else:
                error = response.json()
                return False, error.get("detail", "Login failed")
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def logout(self):
        """Logout and clear session"""
        self.clear_session()
    
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
        """Get current license status from server"""
        if not self.token:
            return {"valid": False, "message": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/license/status",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                self.license_data = response.json()
                self.save_session()
                return self.license_data
            else:
                return {"valid": False, "message": "Failed to fetch license"}
        
        except Exception as e:
            return {"valid": False, "message": f"Connection error: {str(e)}"}
    
    async def initialize_license_purchase(self, student_count: int) -> Tuple[bool, Dict]:
        """Initialize license purchase"""
        if not self.token or not self.user_data:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/license/purchase/initialize",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={
                        "student_count": student_count,
                        "email": self.user_data["email"]
                    },
                    timeout=30.0
                )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                error = response.json()
                return False, {"error": error.get("detail", "Payment initialization failed")}
        
        except Exception as e:
            return False, {"error": f"Connection error: {str(e)}"}
    
    async def verify_payment(self, reference: str) -> Tuple[bool, Dict]:
        """Verify payment and activate license"""
        if not self.token:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/license/verify/{reference}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    # Update local license data
                    self.license_data = data.get("license")
                    self.save_session()
                
                return True, data
            else:
                error = response.json()
                return False, {"error": error.get("detail", "Verification failed")}
        
        except Exception as e:
            return False, {"error": f"Connection error: {str(e)}"}
    
    async def update_license_from_server(self) -> Tuple[bool, str]:
        """Update license from server (after payment)"""
        if not self.token:
            return False, "Not authenticated"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/license/check",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"device_fingerprint": self.device_fingerprint},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                self.license_data = response.json()
                self.save_session()
                
                if self.license_data.get("valid"):
                    return True, f"License updated! {self.license_data['students_available']} students available"
                else:
                    return False, "No valid license found"
            else:
                error = response.json()
                return False, error.get("detail", "Failed to update license")
        
        except Exception as e:
            return False, f"Connection error: {str(e)}"


# Global instance
auth_service = AuthService()