"""
License Client Module for Offline Image Sorter App
This module handles license activation, validation, and payment initialization
Requirements: pip install cryptography requests
"""

import requests
import json
import base64
import hashlib
import platform
import uuid
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from typing import Optional, Tuple
import webbrowser

class LicenseManager:
    """Manages license operations for offline app"""
    
    def __init__(self, api_base_url: str = "http://localhost:8001"):
        self.api_base_url = api_base_url.rstrip("/")
        self.license_file = Path("license.key")
        self.public_key = None
        self._load_public_key()
    
    def _load_public_key(self):
        """Load public key from embedded string or fetch from server"""
        # Option 1: Embed public key directly in app (more secure for offline use)
        embedded_public_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"""
        
        # Try to load embedded key first
        try:
            if embedded_public_key and "..." not in embedded_public_key:
                self.public_key = serialization.load_pem_public_key(
                    embedded_public_key.encode(),
                    backend=default_backend()
                )
                print("✓ Loaded embedded public key")
                return
        except:
            pass
        
        # Option 2: Fetch from server (requires internet connection)
        try:
            response = requests.get(f"{self.api_base_url}/public-key", timeout=5)
            if response.status_code == 200:
                key_data = response.json()
                self.public_key = serialization.load_pem_public_key(
                    key_data["public_key"].encode(),
                    backend=default_backend()
                )
                print("✓ Fetched public key from server")
                
                # Save for future offline use
                with open("public_key.pem", "w") as f:
                    f.write(key_data["public_key"])
        except Exception as e:
            print(f"⚠ Could not fetch public key: {e}")
            
            # Try loading from saved file
            if Path("public_key.pem").exists():
                with open("public_key.pem", "r") as f:
                    self.public_key = serialization.load_pem_public_key(
                        f.read().encode(),
                        backend=default_backend()
                    )
                    print("✓ Loaded cached public key")
    
    def generate_device_fingerprint(self) -> str:
        """
        Generate a unique device fingerprint
        Combines multiple hardware identifiers for robustness
        """
        try:
            # Get system info
            system = platform.system()
            machine = platform.machine()
            processor = platform.processor()
            
            # Get MAC address
            mac = uuid.getnode()
            
            # Get hostname
            hostname = platform.node()
            
            # Combine and hash
            fingerprint_data = f"{system}|{machine}|{processor}|{mac}|{hostname}"
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:32]
            
            return fingerprint
            
        except Exception as e:
            print(f"Error generating fingerprint: {e}")
            # Fallback to UUID
            return str(uuid.uuid4()).replace("-", "")[:32]
    
    def initialize_payment(self, email: str) -> Tuple[bool, dict]:
        """
        Initialize payment with Paystack
        Returns: (success, data) where data contains payment URL
        """
        try:
            device_fingerprint = self.generate_device_fingerprint()
            
            response = requests.post(
                f"{self.api_base_url}/payment/initialize",
                json={
                    "email": email,
                    "device_fingerprint": device_fingerprint
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return True, {
                    "reference": data["reference"],
                    "payment_url": data["authorization_url"],
                    "device_fingerprint": device_fingerprint
                }
            else:
                return False, {"error": response.json().get("detail", "Payment initialization failed")}
                
        except requests.exceptions.ConnectionError:
            return False, {"error": "No internet connection. Please connect to initialize payment."}
        except Exception as e:
            return False, {"error": f"Error: {str(e)}"}
    
    def open_payment_page(self, payment_url: str):
        """Open payment page in user's default browser"""
        try:
            webbrowser.open(payment_url)
            return True
        except Exception as e:
            print(f"Could not open browser: {e}")
            return False
    
    def verify_payment(self, reference: str) -> Tuple[bool, dict]:
        """
        Check if payment was successful
        User calls this after completing payment
        """
        try:
            response = requests.post(
                f"{self.api_base_url}/payment/verify/{reference}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["status"] == "success", data
            else:
                return False, {"error": "Verification failed"}
                
        except requests.exceptions.ConnectionError:
            return False, {"error": "No internet connection"}
        except Exception as e:
            return False, {"error": str(e)}
    
    def activate_license(self, license_key: str) -> Tuple[bool, str]:
        """
        Activate a license key on this device
        Verifies signature and device binding offline
        """
        if not self.public_key:
            return False, "Public key not available. Cannot verify license."
        
        device_fingerprint = self.generate_device_fingerprint()
        
        try:
            # Decode license
            decoded = base64.b64decode(license_key)
            parts = decoded.split(b"|SIGNATURE|")
            
            if len(parts) != 2:
                return False, "Invalid license format"
            
            message, signature = parts
            
            # Verify signature using public key
            self.public_key.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Parse license data
            license_data = json.loads(message.decode())
            
            # Validate device fingerprint
            if license_data["device"] != device_fingerprint:
                return False, "License is not valid for this device"
            
            # Check expiry
            expiry = datetime.fromisoformat(license_data["expires"])
            if expiry < datetime.utcnow():
                return False, f"License expired on {expiry.strftime('%Y-%m-%d')}"
            
            # Save license to file
            with open(self.license_file, "w") as f:
                f.write(license_key)
            
            days_remaining = (expiry - datetime.utcnow()).days
            return True, f"License activated! Valid for {days_remaining} days until {expiry.strftime('%Y-%m-%d')}"
            
        except Exception as e:
            return False, f"License verification failed: {str(e)}"
    
    def check_license(self) -> Tuple[bool, Optional[dict]]:
        """
        Check if a valid license exists
        Returns: (is_valid, license_info)
        """
        if not self.license_file.exists():
            return False, None
        
        try:
            with open(self.license_file, "r") as f:
                license_key = f.read().strip()
            
            if not self.public_key:
                return False, None
            
            device_fingerprint = self.generate_device_fingerprint()
            
            # Verify license
            decoded = base64.b64decode(license_key)
            parts = decoded.split(b"|SIGNATURE|")
            
            if len(parts) != 2:
                return False, None
            
            message, signature = parts
            
            # Verify signature
            self.public_key.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            license_data = json.loads(message.decode())
            
            # Validate device and expiry
            if license_data["device"] != device_fingerprint:
                return False, None
            
            expiry = datetime.fromisoformat(license_data["expires"])
            if expiry < datetime.utcnow():
                return False, {"error": "expired", "expired_on": license_data["expires"]}
            
            return True, {
                "email": license_data["email"],
                "expires": license_data["expires"],
                "days_remaining": (expiry - datetime.utcnow()).days,
                "product": license_data.get("product", "unknown")
            }
            
        except Exception as e:
            print(f"License check error: {e}")
            return False, None
    
    def remove_license(self):
        """Remove license file (for deactivation/logout)"""
        if self.license_file.exists():
            self.license_file.unlink()
            return True
        return False


# ============= EXAMPLE USAGE =============
def example_payment_flow():
    """Example: Complete payment and activation flow"""
    
    # Initialize license manager
    license_mgr = LicenseManager(api_base_url="http://localhost:8000")
    
    print("\n" + "="*60)
    print("IMAGE SORTER PRO - LICENSE ACTIVATION")
    print("="*60)
    
    # Check if already licensed
    is_valid, info = license_mgr.check_license()
    if is_valid:
        print(f"\n✓ License already active!")
        print(f"  Email: {info['email']}")
        print(f"  Expires: {info['expires']}")
        print(f"  Days remaining: {info['days_remaining']}")
        return
    
    # Payment flow
    email = input("\nEnter your email: ")
    
    print("\n🔄 Initializing payment...")
    success, data = license_mgr.initialize_payment(email)
    
    if not success:
        print(f"❌ Error: {data['error']}")
        return
    
    print(f"✓ Payment session created")
    print(f"  Reference: {data['reference']}")
    print(f"\n🌐 Opening payment page in your browser...")
    
    license_mgr.open_payment_page(data["payment_url"])
    
    print("\n⏳ Complete payment in your browser, then return here.")
    input("Press Enter after completing payment...")
    
    # Verify payment
    print("\n🔄 Verifying payment...")
    success, result = license_mgr.verify_payment(data["reference"])
    
    if success:
        print(f"✓ Payment successful!")
        print(f"\n📧 License key has been sent to: {email}")
        print("\nEnter your license key below:")
        license_key = input("> ").strip()
        
        # Activate license
        print("\n🔄 Activating license...")
        success, message = license_mgr.activate_license(license_key)
        
        if success:
            print(f"✓ {message}")
        else:
            print(f"❌ {message}")
    else:
        print(f"❌ Payment verification failed: {result.get('error', 'Unknown error')}")
        print("Please check your email for the license key and activate manually.")


def example_check_license():
    """Example: Check existing license"""
    license_mgr = LicenseManager()
    
    is_valid, info = license_mgr.check_license()
    
    if is_valid:
        print("✓ Valid license found")
        print(f"  Email: {info['email']}")
        print(f"  Expires: {info['expires']}")
        print(f"  Days remaining: {info['days_remaining']}")
    else:
        print("❌ No valid license found")
        if info and info.get("error") == "expired":
            print(f"  License expired on: {info['expired_on']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        example_check_license()
    else:
        example_payment_flow()