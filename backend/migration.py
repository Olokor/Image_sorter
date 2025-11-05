"""
Migration Script: Transition to JWT Database Storage
Run this once to set up the new authentication system
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add the backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from services.auth_service import AuthService
from services.auth_service import AuthToken, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

LOCAL_CONFIG_PATH = Path.home() / ".photosorter" / "config.json"
LOCAL_DB_PATH = Path.home() / ".photosorter" / "auth.db"


def migrate_to_jwt_db():
    """Migrate existing JSON config to new JWT database"""
    
    print("\n" + "="*70)
    print("JWT DATABASE MIGRATION SCRIPT")
    print("="*70)
    
    # Check if old config exists
    if not LOCAL_CONFIG_PATH.exists():
        print("\n✅ No existing config found. Fresh installation detected.")
        print("✅ New JWT database will be created on first login.")
        return
    
    print(f"\n📁 Found existing config: {LOCAL_CONFIG_PATH}")
    
    # Load old config
    try:
        with open(LOCAL_CONFIG_PATH, "r") as f:
            old_config = json.load(f)
        
        print("✅ Loaded old configuration")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    # Initialize new database
    print(f"\n📊 Initializing JWT database: {LOCAL_DB_PATH}")
    
    try:
        LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        engine = create_engine(f'sqlite:///{LOCAL_DB_PATH}', echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db_session = Session()
        
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return
    
    # Migrate data
    token = old_config.get("token")
    user_data = old_config.get("user")
    license_data = old_config.get("license")
    device_fingerprint = old_config.get("device_fingerprint")
    
    if not token or not user_data:
        print("⚠️ No valid session data found in old config")
        return
    
    print("\n📦 Migrating session data...")
    print(f"   User: {user_data.get('email')}")
    print(f"   License Valid: {license_data.get('valid', False) if license_data else False}")
    
    try:
        # Calculate expiry (30 days from now)
        expires_at = datetime.utcnow() + timedelta(days=30)
        
        # Create auth token record
        auth_token = AuthToken(
            token=token,
            user_email=user_data.get('email', ''),
            user_data=json.dumps(user_data),
            license_data=json.dumps(license_data) if license_data else None,
            device_fingerprint=device_fingerprint or '',
            expires_at=expires_at,
            last_used=datetime.utcnow(),
            is_valid=1
        )
        
        db_session.add(auth_token)
        db_session.commit()
        
        print("✅ Session data migrated successfully!")
        
        # Keep old config as backup
        backup_path = LOCAL_CONFIG_PATH.with_suffix('.json.backup')
        LOCAL_CONFIG_PATH.rename(backup_path)
        print(f"✅ Old config backed up to: {backup_path}")
        
    except Exception as e:
        print(f"❌ Error migrating data: {e}")
        db_session.rollback()
        return
    finally:
        db_session.close()
    
    print("\n" + "="*70)
    print("✅ MIGRATION COMPLETED SUCCESSFULLY")
    print("="*70)
    print("\nNext steps:")
    print("1. Restart your application")
    print("2. JWT tokens will now be loaded from the database")
    print("3. All authenticated requests will use stored JWT")
    print("\nYour authentication session has been preserved!")
    print("="*70 + "\n")


def check_jwt_storage():
    """Check current JWT storage status"""
    
    print("\n" + "="*70)
    print("JWT STORAGE STATUS CHECK")
    print("="*70)
    
    # Check database
    if LOCAL_DB_PATH.exists():
        print(f"\n✅ JWT Database found: {LOCAL_DB_PATH}")
        
        try:
            engine = create_engine(f'sqlite:///{LOCAL_DB_PATH}', echo=False)
            Session = sessionmaker(bind=engine)
            db_session = Session()
            
            # Count tokens
            total_tokens = db_session.query(AuthToken).count()
            valid_tokens = db_session.query(AuthToken).filter(
                AuthToken.is_valid == 1,
                AuthToken.expires_at > datetime.utcnow()
            ).count()
            
            print(f"   Total tokens: {total_tokens}")
            print(f"   Valid tokens: {valid_tokens}")
            
            # Show latest token
            latest = db_session.query(AuthToken).filter(
                AuthToken.is_valid == 1
            ).order_by(AuthToken.created_at.desc()).first()
            
            if latest:
                print(f"\n📧 Current User: {latest.user_email}")
                print(f"   Token Created: {latest.created_at}")
                print(f"   Last Used: {latest.last_used}")
                print(f"   Expires: {latest.expires_at}")
                
                days_until_expiry = (latest.expires_at - datetime.utcnow()).days
                print(f"   Days Remaining: {days_until_expiry}")
                
                if latest.license_data:
                    license = json.loads(latest.license_data)
                    print(f"\n💳 License Status:")
                    print(f"   Valid: {license.get('valid', False)}")
                    print(f"   Students Available: {license.get('students_available', 0)}")
            
            db_session.close()
            
        except Exception as e:
            print(f"❌ Error reading database: {e}")
    else:
        print(f"\n⚠️ JWT Database not found: {LOCAL_DB_PATH}")
        print("   Run migration or login to create it")
    
    # Check old config
    if LOCAL_CONFIG_PATH.exists():
        print(f"\n⚠️ Old config still exists: {LOCAL_CONFIG_PATH}")
        print("   Run migration to convert to JWT database")
    
    print("\n" + "="*70 + "\n")


def main():
    """Main menu"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "migrate":
            migrate_to_jwt_db()
        elif command == "check":
            check_jwt_storage()
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python migrate_jwt.py migrate  - Migrate from old system")
            print("  python migrate_jwt.py check    - Check JWT storage status")
    else:
        print("\nJWT Database Management")
        print("="*40)
        print("1. Migrate from old system")
        print("2. Check JWT storage status")
        print("3. Exit")
        print("="*40)
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            migrate_to_jwt_db()
        elif choice == "2":
            check_jwt_storage()
        elif choice == "3":
            print("Goodbye!")
        else:
            print("Invalid choice")


if __name__ == "__main__":
    main()