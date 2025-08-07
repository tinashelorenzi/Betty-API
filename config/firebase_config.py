import os
import firebase_admin
from firebase_admin import credentials, auth
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class FirebaseConfig:
    """Firebase configuration and authentication utilities"""
    
    def __init__(self):
        self.app = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase is already initialized
            if not firebase_admin._apps:
                # Try to load service account key from environment variable
                service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
                
                if service_account_path:
                    # Convert relative path to absolute
                    if not os.path.isabs(service_account_path):
                        service_account_path = os.path.abspath(service_account_path)
                    
                    print(f"🔍 Looking for Firebase credentials at: {service_account_path}")
                    
                    if os.path.exists(service_account_path):
                        # Initialize with service account file
                        cred = credentials.Certificate(service_account_path)
                        self.app = firebase_admin.initialize_app(cred)
                        print("✅ Firebase Admin SDK initialized successfully with service account")
                    else:
                        print(f"❌ Firebase service account file not found at: {service_account_path}")
                        print("📋 Available files in credentials directory:")
                        credentials_dir = os.path.dirname(service_account_path)
                        if os.path.exists(credentials_dir):
                            for file in os.listdir(credentials_dir):
                                print(f"   - {file}")
                        raise FileNotFoundError(f"Firebase service account file not found: {service_account_path}")
                else:
                    print("⚠️  FIREBASE_SERVICE_ACCOUNT_PATH not set, trying default credentials")
                    # Initialize with default credentials (for Google Cloud)
                    self.app = firebase_admin.initialize_app()
                    print("✅ Firebase Admin SDK initialized with default credentials")
                    
            else:
                self.app = firebase_admin.get_app()
                print("✅ Firebase Admin SDK already initialized")
                
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            print("Please ensure you have set up Firebase credentials properly")
            # Don't raise the exception to allow the app to continue
            print("⚠️  Firebase features may not work properly")
    
    def verify_token(self, id_token: str) -> Optional[dict]:
        """Verify Firebase ID token and return user info"""
        try:
            if not self.app:
                raise ValueError("Firebase not properly initialized")
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            print(f"Token verification failed: {e}")
            return None
    
    def get_user_by_uid(self, uid: str) -> Optional[dict]:
        """Get user information by Firebase UID"""
        try:
            if not self.app:
                raise ValueError("Firebase not properly initialized")
            user_record = auth.get_user(uid)
            return {
                'uid': user_record.uid,
                'email': user_record.email,
                'display_name': user_record.display_name,
                'photo_url': user_record.photo_url,
                'email_verified': user_record.email_verified,
                'disabled': user_record.disabled,
            }
        except Exception as e:
            print(f"Failed to get user by UID: {e}")
            return None

# Global instance
firebase_config = FirebaseConfig()