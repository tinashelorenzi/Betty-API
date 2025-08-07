from firebase_admin import auth
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from models.user_models import UserCreate, UserResponse, AuthToken, UserUpdate
from services.firebase_service import FirebaseService
import hashlib
import secrets
import os
from dotenv import load_dotenv
import jwt

load_dotenv()


class AuthService:
    """Service for authentication operations"""
    
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
        self.jwt_secret = secrets.token_urlsafe(32)
        self.jwt_secret = os.getenv('JWT_SECRET_KEY', 'your_super_secret_jwt_key_here')
        self.jwt_algorithm = os.getenv('JWT_ALGORITHM', 'HS256')
        self.jwt_expiry_minutes = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
    
    def create_jwt_token(self, uid: str, email: str) -> str:
        """Create JWT token for user"""
        payload = {
            'uid': uid,
            'email': email,
            'exp': datetime.now(timezone.utc) + timedelta(minutes=self.jwt_expiry_minutes),
            'iat': datetime.now(timezone.utc)
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token has expired")
        except jwt.InvalidTokenError:
            raise Exception("Invalid token")
    
    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create new user with Firebase Auth"""
        try:
            # Create user in Firebase Auth
            user_record = auth.create_user(
                email=user_data.email,
                password=user_data.password,
                display_name=f"{user_data.first_name} {user_data.last_name}",
                email_verified=False
            )
            
            # Create user profile in Firestore
            profile_data = {
                "uid": user_record.uid,
                "email": user_data.email,
                "first_name": user_data.first_name,
                "last_name": user_data.last_name,
                "location": user_data.location or "",
                "timezone": user_data.timezone or "UTC",
                "is_verified": False,
                "google_connected": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            
            await self.firebase_service.create_user_profile(user_record.uid, profile_data)
            
            return UserResponse(**profile_data)
            
        except auth.EmailAlreadyExistsError:
            raise ValueError("User with this email already exists")
        except Exception as e:
            raise Exception(f"Failed to create user: {e}")
    
    async def login_user(self, email: str, password: str) -> AuthToken:
        """Login user with email/password and return JWT token"""
        try:
            # Use Firebase Admin SDK to get user by email
            # Note: Firebase Admin SDK doesn't support password verification directly
            # We'll use the REST API for password verification but with better error handling
            
            import requests
            import json
            
            # Firebase Auth REST API endpoint for password verification
            firebase_api_key = os.getenv('FIREBASE_API_KEY')
            
            # If no API key is configured, try to get user by email using Admin SDK
            if not firebase_api_key:
                print("⚠️ FIREBASE_API_KEY not configured, attempting to get user by email...")
                try:
                    # Get user by email using Firebase Admin SDK
                    user_record = auth.get_user_by_email(email)
                    uid = user_record.uid
                    firebase_auth_data = {
                        'localId': uid,
                        'email': user_record.email,
                        'displayName': user_record.display_name,
                        'emailVerified': user_record.email_verified
                    }
                    print(f"✅ Found user by email: {uid}")
                except auth.UserNotFoundError:
                    raise ValueError("Invalid email or password")
                except Exception as e:
                    raise Exception(f"Authentication failed: {e}")
            else:
                # Use REST API for password verification
                auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
                
                # Verify credentials with Firebase
                auth_payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }
                
                print(f"Logging in user with credentials: {email} and {password}")
                auth_response = requests.post(auth_url, json=auth_payload)
                print(f"Auth response: {auth_response.json()}")
                
                if auth_response.status_code != 200:
                    auth_data = auth_response.json()
                    if "INVALID_PASSWORD" in auth_data.get("error", {}).get("message", ""):
                        raise ValueError("Invalid email or password")
                    elif "EMAIL_NOT_FOUND" in auth_data.get("error", {}).get("message", ""):
                        raise ValueError("Invalid email or password")
                    else:
                        raise ValueError("Authentication failed")
                
                # Get Firebase user record for additional info
                firebase_auth_data = auth_response.json()
                uid = firebase_auth_data['localId']
                print(f"Firebase auth successful for UID: {uid}")
            
            # Get user profile from Firestore
            print(f"FirebaseService instance: {self.firebase_service}")
            print(f"FirebaseService methods: {[method for method in dir(self.firebase_service) if not method.startswith('_')]}")
            user_profile = await self.firebase_service.get_user_profile(uid)
            
            # If profile doesn't exist, create it from Firebase auth data
            if not user_profile:
                print("Creating new profile from Firebase auth data...")
                profile_data = {
                    "uid": uid,
                    "email": email,
                    "first_name": firebase_auth_data.get('displayName', '').split()[0] if firebase_auth_data.get('displayName') else '',
                    "last_name": ' '.join(firebase_auth_data.get('displayName', '').split()[1:]) if firebase_auth_data.get('displayName') and len(firebase_auth_data.get('displayName', '').split()) > 1 else '',
                    "location": "",
                    "timezone": "UTC",
                    "is_verified": firebase_auth_data.get('emailVerified', False),
                    "google_connected": False,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "last_login": datetime.now(timezone.utc)
                }
                
                try:
                    await self.firebase_service.create_user_profile(uid, profile_data)
                    user_profile = profile_data
                except Exception as e:
                    print(f"⚠️ Warning: Could not create user profile in Firestore: {e}")
                    # Use minimal profile data
                    user_profile = {
                        "uid": uid,
                        "email": email,
                        "first_name": firebase_auth_data.get('displayName', '').split()[0] if firebase_auth_data.get('displayName') else '',
                        "last_name": ' '.join(firebase_auth_data.get('displayName', '').split()[1:]) if firebase_auth_data.get('displayName') and len(firebase_auth_data.get('displayName', '').split()) > 1 else '',
                        "location": "",
                        "timezone": "UTC",
                        "is_verified": firebase_auth_data.get('emailVerified', False),
                        "google_connected": False,
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                        "last_login": datetime.now(timezone.utc)
                    }
            else:
                # Update last login for existing profile
                await self.firebase_service.update_user_profile(
                    uid, 
                    {"last_login": datetime.now(timezone.utc)}
                )
            
            # Create JWT token for your API
            jwt_token = self.create_jwt_token(uid, email)
            
            user_response = UserResponse(**user_profile)
            
            return AuthToken(
                access_token=jwt_token,
                token_type="bearer",
                expires_in=self.jwt_expiry_minutes * 60,  # Convert to seconds
                user=user_response
            )
            
        except ValueError as ve:
            # Re-raise validation errors as-is
            raise ve
        except Exception as e:
            raise Exception(f"Login failed: {e}")
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token and return user data"""
        try:
            # Verify JWT token
            payload = self.verify_jwt_token(token)
            uid = payload['uid']
            
            # Get user profile
            user_profile = await self.firebase_service.get_user_profile(uid)
            if not user_profile:
                raise ValueError("User profile not found")
            
            return user_profile
            
        except Exception as e:
            raise Exception(f"Token verification failed: {e}")
    
    async def refresh_token(self, refresh_token: str) -> AuthToken:
        """Refresh access token"""
        # TODO: Implement refresh token logic
        # This would typically involve validating the refresh token
        # and issuing a new access token
        pass
    
    async def logout_user(self, uid: str) -> bool:
        """Logout user (revoke tokens)"""
        try:
            # Revoke all refresh tokens for the user
            auth.revoke_refresh_tokens(uid)
            
            # Update user profile
            await self.firebase_service.update_user_profile(
                uid, 
                {"last_logout": datetime.now(timezone.utc)}
            )
            
            return True
        except Exception as e:
            raise Exception(f"Logout failed: {e}")

    async def get_current_user(self, token: str) -> UserResponse:
        """Get current user from token"""
        user_data = await self.verify_token(token)
        return UserResponse(**user_data)

    async def update_user_profile(self, uid: str, update_data: Dict[str, Any]) -> UserResponse:
        """Update user profile"""
        try:
            # Update in Firestore
            await self.firebase_service.update_user_profile(uid, update_data)
            
            # Update in Firebase Auth if needed
            auth_updates = {}
            if "email" in update_data:
                auth_updates["email"] = update_data["email"]
            if "first_name" in update_data or "last_name" in update_data:
                current_profile = await self.firebase_service.get_user_profile(uid)
                first_name = update_data.get("first_name", current_profile.get("first_name"))
                last_name = update_data.get("last_name", current_profile.get("last_name"))
                auth_updates["display_name"] = f"{first_name} {last_name}"
            
            if auth_updates:
                auth.update_user(uid, **auth_updates)
            
            # Get updated profile
            updated_profile = await self.firebase_service.get_user_profile(uid)
            return UserResponse(**updated_profile)
            
        except Exception as e:
            raise Exception(f"Failed to update user profile: {e}")
    
    async def delete_user_account(self, uid: str) -> bool:
        """Delete user account"""
        try:
            # Delete from Firebase Auth
            auth.delete_user(uid)
            
            # Delete user profile and related data
            # TODO: Implement cascading delete for user documents, tasks, etc.
            
            return True
        except Exception as e:
            raise Exception(f"Failed to delete user account: {e}")
    
    async def send_password_reset(self, email: str) -> bool:
        """Send password reset email"""
        try:
            # Generate password reset link
            link = auth.generate_password_reset_link(email)
            
            # TODO: Send email with password reset link
            print(f"Password reset link: {link}")
            
            return True
        except auth.UserNotFoundError:
            # Don't reveal if user exists or not
            return True
        except Exception as e:
            raise Exception(f"Failed to send password reset: {e}")
    
    async def verify_email(self, uid: str) -> bool:
        """Mark user email as verified"""
        try:
            auth.update_user(uid, email_verified=True)
            await self.firebase_service.update_user_profile(
                uid, 
                {"is_verified": True, "verified_at": datetime.utcnow()}
            )
            return True
        except Exception as e:
            raise Exception(f"Failed to verify email: {e}")
    
    async def change_password(self, uid: str, new_password: str) -> bool:
        """Change user password"""
        try:
            auth.update_user(uid, password=new_password)
            
            # Update password changed timestamp
            await self.firebase_service.update_user_profile(
                uid, 
                {"password_changed_at": datetime.utcnow()}
            )
            
            return True
        except Exception as e:
            raise Exception(f"Failed to change password: {e}")
    
    async def connect_google_account(self, uid: str, google_data: Dict[str, Any]) -> bool:
        """Connect Google account to user profile"""
        try:
            google_profile_data = {
                "google_connected": True,
                "google_id": google_data.get("google_id"),
                "google_email": google_data.get("email"),
                "google_picture": google_data.get("picture_url"),
                "google_connected_at": datetime.utcnow()
            }
            
            await self.firebase_service.update_user_profile(uid, google_profile_data)
            return True
        except Exception as e:
            raise Exception(f"Failed to connect Google account: {e}")
    
    async def disconnect_google_account(self, uid: str) -> bool:
        """Disconnect Google account from user profile"""
        try:
            google_profile_data = {
                "google_connected": False,
                "google_id": None,
                "google_email": None,
                "google_picture": None,
                "google_disconnected_at": datetime.utcnow()
            }
            
            await self.firebase_service.update_user_profile(uid, google_profile_data)
            return True
        except Exception as e:
            raise Exception(f"Failed to disconnect Google account: {e}")
    
    # ========================================================================
    # ADMIN FUNCTIONS
    # ========================================================================
    
    async def list_users(self, page_token: Optional[str] = None, max_results: int = 1000) -> Dict[str, Any]:
        """List all users (admin function)"""
        try:
            page = auth.list_users(page_token=page_token, max_results=max_results)
            
            users = []
            for user in page.users:
                user_profile = await self.firebase_service.get_user_profile(user.uid)
                if user_profile:
                    users.append(UserResponse(**user_profile))
            
            return {
                "users": users,
                "next_page_token": page.next_page_token
            }
        except Exception as e:
            raise Exception(f"Failed to list users: {e}")
    
    async def get_user_by_email(self, email: str) -> Optional[UserResponse]:
        """Get user by email (admin function)"""
        try:
            user_record = auth.get_user_by_email(email)
            user_profile = await self.firebase_service.get_user_profile(user_record.uid)
            
            if user_profile:
                return UserResponse(**user_profile)
            return None
        except auth.UserNotFoundError:
            return None
        except Exception as e:
            raise Exception(f"Failed to get user by email: {e}")