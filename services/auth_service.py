from firebase_admin import auth
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from models.user_models import UserCreate, UserResponse, AuthToken
from services.firebase_service import FirebaseService
import hashlib
import secrets

class AuthService:
    """Service for authentication operations"""
    
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
        self.jwt_secret = secrets.token_urlsafe(32)
    
    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create a new user account"""
        try:
            # Validate password confirmation
            if not user_data.passwords_match():
                raise ValueError("Passwords do not match")
            
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
                "location": user_data.location,
                "timezone": user_data.timezone,
                "is_verified": False,
                "google_connected": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await self.firebase_service.create_user_profile(user_record.uid, profile_data)
            
            # Send email verification
            link = auth.generate_email_verification_link(user_data.email)
            # TODO: Send email with verification link
            
            return UserResponse(**profile_data)
            
        except auth.EmailAlreadyExistsError:
            raise ValueError("User with this email already exists")
        except Exception as e:
            raise Exception(f"Failed to create user: {e}")
    
    async def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Login user - Return instructions for client-side Firebase Auth"""
        try:
            # Verify user exists in Firebase Auth
            user_record = auth.get_user_by_email(email)
            
            # Get user profile from Firestore
            user_profile = await self.firebase_service.get_user_profile(user_record.uid)
            if not user_profile:
                raise ValueError("User profile not found")
            
            # Update last login
            await self.firebase_service.update_user_profile(
                user_record.uid, 
                {"last_login": datetime.utcnow()}
            )
            
            # Return success - client should handle Firebase Auth
            return {
                "message": "User verified - complete login on client",
                "uid": user_record.uid,
                "email": user_record.email,
                "user": UserResponse(**user_profile)
            }
            
        except auth.UserNotFoundError:
            raise ValueError("User not found")
        except Exception as e:
            raise Exception(f"Login failed: {e}")
    
    async def verify_token(self, id_token: str) -> Dict[str, Any]:
        """Verify Firebase ID token and return user data"""
        try:
            # Verify ID token (not custom token!)
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
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
                {"last_logout": datetime.utcnow()}
            )
            
            return True
        except Exception as e:
            raise Exception(f"Logout failed: {e}")
    
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