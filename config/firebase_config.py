import os
import firebase_admin
from firebase_admin import credentials, auth
from typing import Optional

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
                
                if service_account_path and os.path.exists(service_account_path):
                    # Initialize with service account file
                    cred = credentials.Certificate(service_account_path)
                    self.app = firebase_admin.initialize_app(cred)
                else:
                    # Initialize with default credentials (for Google Cloud)
                    self.app = firebase_admin.initialize_app()
                    
                print("Firebase Admin SDK initialized successfully")
            else:
                self.app = firebase_admin.get_app()
                print("Firebase Admin SDK already initialized")
                
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            print("Please ensure you have set up Firebase credentials properly")
    
    def verify_token(self, id_token: str) -> Optional[dict]:
        """
        Verify Firebase ID token and return user info
        
        Args:
            id_token: Firebase ID token from client
            
        Returns:
            dict: User information if token is valid, None otherwise
        """
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            print(f"Token verification failed: {e}")
            return None
    
    def get_user_by_uid(self, uid: str) -> Optional[dict]:
        """
        Get user information by Firebase UID
        
        Args:
            uid: Firebase user UID
            
        Returns:
            dict: User information if found, None otherwise
        """
        try:
            user_record = auth.get_user(uid)
            return {
                'uid': user_record.uid,
                'email': user_record.email,
                'email_verified': user_record.email_verified,
                'display_name': user_record.display_name,
                'phone_number': user_record.phone_number,
                'photo_url': user_record.photo_url,
                'disabled': user_record.disabled
            }
        except Exception as e:
            print(f"Error getting user by UID: {e}")
            return None
    
    def create_custom_token(self, uid: str, additional_claims: dict = None) -> Optional[str]:
        """
        Create a custom token for a user
        
        Args:
            uid: Firebase user UID
            additional_claims: Additional claims to include in the token
            
        Returns:
            str: Custom token if successful, None otherwise
        """
        try:
            token = auth.create_custom_token(uid, additional_claims or {})
            return token.decode('utf-8')
        except Exception as e:
            print(f"Error creating custom token: {e}")
            return None

# Global Firebase configuration instance
firebase_config = FirebaseConfig() 