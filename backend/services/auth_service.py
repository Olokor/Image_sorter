"""
Local Desktop App - Authentication Service
Connects to hosted backend for auth and licensing
"""

import httpx
import json
import hashlib
import platform
import uuid
import asyncio 
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
import os

# Configuration - FIX: Use environment variable with local fallback
API_BASE_URL = os.getenv("PHOTOSORTER_API_URL", "http://localhost:8001")
LOCAL_CONFIG_PATH = Path.home() / ".photosorter" / "config.json"

class AuthService:
    """Handles authentication with hosted backend and secure local login"""
    
    def __init__(self):
        self.api_url = API_BASE_URL
        self.token: Optional[str] = None
        self.user_data: Optional[Dict] = None
        self.license_data: Optional[Dict] = None
        # Track email during multi-step auth (Signup -> Verify -> Login)
        self.pending_email: Optional[str] = None 
        # CRITICAL SECURITY FIELD: Stores the one-way hash of the password for offline verification
        self.password_hash: Optional[str] = None 
        
        self.device_fingerprint = self.generate_device_fingerprint()
        
        # Load saved session
        self.load_session()
        
        print(f"🔗 AuthService initialized - API URL: {self.api_url}")
    
    def generate_device_fingerprint(self) -> str:
        """Generate unique device fingerprint based on system info"""
        system = platform.system()
        machine = platform.machine()
        node = platform.node()
        processor = platform.processor()
        
        # Combine system info
        device_string = f"{system}|{machine}|{node}|{processor}"
        
        # Hash for privacy and consistency
        fingerprint = hashlib.sha256(device_string.encode()).hexdigest()
        return fingerprint

    def hash_password(self, password: str) -> str:
        """
        One-way hash a password for secure local storage using the device 
        fingerprint as a simple salt. This allows for offline comparison.
        """
        hasher = hashlib.sha256()
        # Use a strong encoding and combine with a device-specific salt
        hasher.update(password.encode('utf-8'))
        hasher.update(self.device_fingerprint.encode('utf-8')) 
        return hasher.hexdigest()
    
    def save_session(self):
        """Save auth session locally to the configuration file"""
        try:
            LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            session_data = {
                "token": self.token,
                "user": self.user_data,
                "license": self.license_data,
                "pending_email": self.pending_email, 
                "password_hash": self.password_hash, # <-- SECURELY PERSIST HASH
                "device_fingerprint": self.device_fingerprint,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            with open(LOCAL_CONFIG_PATH, "w") as f:
                json.dump(session_data, f, indent=2)
            print("✅ Session saved successfully.")
        except Exception as e:
            print(f"❌ Error saving session: {e}")

    
    def load_session(self):
        """Load saved auth session from the configuration file"""
        if not LOCAL_CONFIG_PATH.exists():
            return
        
        try:
            with open(LOCAL_CONFIG_PATH, "r") as f:
                session_data = json.load(f)
            
            self.token = session_data.get("token")
            self.user_data = session_data.get("user")
            self.license_data = session_data.get("license")
            self.pending_email = session_data.get("pending_email")
            self.password_hash = session_data.get("password_hash") # <-- LOAD HASH
            
            # Verify device fingerprint matches
            saved_fp = session_data.get("device_fingerprint")
            if saved_fp != self.device_fingerprint:
                print("⚠️ Device fingerprint mismatch. Session cleared.")
                self.clear_session()
            elif self.is_authenticated():
                 print("✅ Session loaded and user is authenticated.")
        except Exception as e:
            print(f"❌ Error loading session: {e}")
            self.clear_session() # Clear corrupted session
    
    def clear_session(self):
        """Clear local session variables and delete the config file"""
        self.token = None
        self.user_data = None
        self.license_data = None
        self.pending_email = None 
        self.password_hash = None # <-- Clear stored hash
        
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
                    return False, f"Signup failed - Server returned {response.status_code} and non-JSON content."
        
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
                
                if data.get("access_token") and data.get("user"):
                    # NOTE: Verification often requires a subsequent explicit login to get the password hash
                    self.token = data["access_token"]
                    self.user_data = data["user"]
                    self.license_data = data.get("license_status")
                    self.pending_email = None 
                    self.save_session()
                    return True, "Email verified and session logged in successfully! Please log in to save password locally."
                
                self.pending_email = None
                self.save_session()
                
                return True, data.get("message", "Email verified!")
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
                self.license_data = data.get("license_status")
                self.pending_email = None
                
                # --- CRITICAL FIX: Save the local hash of the password for OFFLINE AUTH ---
                self.password_hash = self.hash_password(password)
                
                # Save session upon successful login
                self.save_session()
                
                return True, "Login successful"
            else:
                try:
                    error = response.json()
                    return False, error.get("detail", "Login failed")
                except:
                    return False, f"Login failed (HTTP {response.status_code})"
        
        except httpx.ConnectError:
            return False, f"Cannot connect to server at {self.api_url}. Is the backend running?"
        except httpx.TimeoutException:
            return False, "Connection timeout. Please check your internet connection."
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def local_login(self, email: str, password: str) -> Tuple[bool, str]:
        """
        Attempts to authenticate locally using stored password hash and session data. 
        Does NOT contact the server.
        """
        # 1. Check if the app has any saved session/credentials
        if not self.password_hash or not self.user_data or not self.token:
            return False, "No full session data found. Please log in online first to establish the session."
        
        # 2. Verify email matches the stored user data
        if self.user_data.get("email", "").lower() != email.lower():
            return False, "Local session mismatch: Email incorrect."
            
        # 3. Hash the provided password and compare it to the stored hash
        input_hash = self.hash_password(password)
        if input_hash != self.password_hash:
            return False, "Incorrect password for local login."

        # 4. Success - The user is authenticated locally with valid credentials
        print("✅ Local login successful. Session is active.")
        return True, "Authenticated locally."
    
    # ... (resend_otp, logout, is_authenticated, has_valid_license, etc. methods remain the same)
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
        """Check if user is authenticated (locally, based on session data)"""
        return self.token is not None and self.user_data is not None and self.password_hash is not None
    
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/license/status",
                    headers={"Authorization": f"Bearer {self.token}"}
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/license/purchase/initialize",
                    headers={"Authorization": f"Bearer {self.token}"},
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
        """Verify payment and activate license"""
        if not self.token:
            return False, {"error": "Not authenticated"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/license/verify/{reference}",
                    headers={"Authorization": f"Bearer {self.token}"}
                )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    # Update local license data
                    self.license_data = data.get("license")
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
        """Update license from server (after payment or JWT refresh)"""
        if not self.token:
            return False, "Not authenticated"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/license/check",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"device_fingerprint": self.device_fingerprint}
                )
            
            if response.status_code == 200:
                self.license_data = response.json()
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

# --- Example Usage (Demonstrates how the service is intended to be called) ---

async def main_app_flow():
    """Simulated application startup and authentication flow."""
    print("\n--- Starting Auth Service Demo ---")
    
    TEST_EMAIL = "test_user@example.com"
    TEST_PASSWORD = "Password123"
    
    # 1. Check existing session
    if auth_service.is_authenticated():
        # Attempt to log in locally without network connection
        print("\n--- Attempting Local Login (Offline) ---")
        success, message = auth_service.local_login(TEST_EMAIL, TEST_PASSWORD)
        print(f"Local Login Result: {success}, {message}")
        
        if success:
            # If local login succeeds, perform an online check in the background
            print("\n--- Performing License Check (Online) ---")
            status, msg = await auth_service.update_license_from_server()
            print(f"License Status: {msg}")
        return

    # If no session, proceed with initial online login
    print("\n--- Initial Online Login Required ---")
    success, message = await auth_service.login(TEST_EMAIL, TEST_PASSWORD)
    print(f"Online Login Result: {success}, {message}")
    
    # 2. Final state check
    print("\n--- Final Service Status ---")
    if auth_service.is_authenticated():
        print(f"Status: LOGGED IN. Email: {auth_service.user_data.get('email')}")
        print(f"Password Hash Stored: {auth_service.password_hash is not None}")
    else:
        print("Status: NOT AUTHENTICATED.")
    
if __name__ == "__main__":
    try:
        asyncio.run(main_app_flow())
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
