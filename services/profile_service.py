# services/profile_service.py - COMPLETE LOCAL STORAGE VERSION
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import uuid
import os
import shutil
from fastapi import UploadFile
from models.user_models import UserUpdate, UserResponse, ProfileStats, NotificationSettings, UserPreferences
from services.firebase_service import FirebaseService
from services.auth_service import AuthService

class ProfileService:
    """Service for user profile operations with local file storage"""
    
    def __init__(self, firebase_service: FirebaseService, auth_service: AuthService):
        self.firebase_service = firebase_service
        self.auth_service = auth_service
        self.upload_dir = "uploads"
        self.avatar_dir = os.path.join(self.upload_dir, "avatars")
        
        # Ensure directories exist
        os.makedirs(self.avatar_dir, exist_ok=True)
    
    def get_server_url(self) -> str:
        """Get the server base URL for file serving"""
        return os.getenv("SERVER_BASE_URL", "http://localhost:8000")
    
    async def update_profile(self, uid: str, profile_update: UserUpdate) -> UserResponse:
        """Update user profile information"""
        try:
            # Get current user profile
            current_profile = await self.firebase_service.get_user_profile(uid)
            if not current_profile:
                raise ValueError("User profile not found")
            
            # Prepare update data (only include non-None values)
            update_data = {}
            for field, value in profile_update.dict(exclude_unset=True).items():
                if value is not None:
                    update_data[field] = value
            
            update_data['updated_at'] = datetime.now(timezone.utc)
            
            # Update in Firestore
            await self.firebase_service.update_user_profile(uid, update_data)
            
            # Get updated profile
            updated_profile = await self.firebase_service.get_user_profile(uid)
            return UserResponse(**updated_profile)
            
        except Exception as e:
            raise Exception(f"Failed to update profile: {e}")
    
    async def upload_avatar(self, uid: str, file: UploadFile) -> str:
        """Upload user avatar to local storage"""
        try:
            # Clean up old avatar files for this user
            try:
                existing_files = [f for f in os.listdir(self.avatar_dir) if f.startswith(f"{uid}_")]
                for old_file in existing_files:
                    old_path = os.path.join(self.avatar_dir, old_file)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                        print(f"Cleaned up old avatar: {old_file}")
            except Exception as cleanup_error:
                print(f"Warning: Could not clean up old avatar files: {cleanup_error}")
            
            # Generate unique filename
            file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
            filename = f"{uid}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = os.path.join(self.avatar_dir, filename)
            
            # Save file to local storage
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Generate public URL
            avatar_url = f"{self.get_server_url()}/uploads/avatars/{filename}"
            
            # Update user profile with new avatar URL
            await self.firebase_service.update_user_profile(
                uid, 
                {
                    "avatar_url": avatar_url,
                    "updated_at": datetime.now(timezone.utc)
                }
            )
            
            print(f"Avatar uploaded successfully: {avatar_url}")
            return avatar_url
            
        except Exception as e:
            raise Exception(f"Failed to upload avatar: {e}")
    
    async def get_user_stats(self, uid: str) -> ProfileStats:
        """Get user activity statistics"""
        try:
            # For now, return mock data since we don't have task/document collections yet
            # In a real app, you'd query your Firestore collections
            
            # Mock data based on user account age
            user_profile = await self.firebase_service.get_user_profile(uid)
            if not user_profile:
                return ProfileStats(uid=uid)
            
            # Calculate days since account creation
            created_at = user_profile.get('created_at')
            days_active = 1
            
            if created_at:
                if isinstance(created_at, str):
                    try:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        days_active = max(1, (datetime.now(timezone.utc) - created_date).days)
                    except ValueError:
                        days_active = 1
                elif isinstance(created_at, datetime):
                    # Ensure both datetimes are timezone-aware
                    now = datetime.now(timezone.utc)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    days_active = max(1, (now - created_at).days)
            
            # Generate reasonable mock stats based on account age
            base_multiplier = min(days_active, 30) / 30  # Cap at 30 days for realism
            
            tasks_completed = int(5 * base_multiplier + (days_active * 0.5))
            documents_created = int(3 * base_multiplier + (days_active * 0.2))
            ai_chats = int(10 * base_multiplier + (days_active * 1.5))
            hours_saved = round((tasks_completed * 0.25) + (documents_created * 0.5) + (ai_chats * 0.17), 1)
            
            # Simple streak calculation
            last_login = user_profile.get('last_login')
            streak_days = 0
            if last_login:
                try:
                    if isinstance(last_login, str):
                        last_login_date = datetime.fromisoformat(last_login.replace('Z', '+00:00'))
                    else:
                        last_login_date = last_login
                    
                    # Ensure both datetimes are timezone-aware
                    now = datetime.now(timezone.utc)
                    if last_login_date.tzinfo is None:
                        last_login_date = last_login_date.replace(tzinfo=timezone.utc)
                    
                    days_since_login = (now - last_login_date).days
                    if days_since_login <= 1:
                        streak_days = min(7, days_active)  # Show streak for recent users
                except:
                    streak_days = 1
            
            return ProfileStats(
                uid=uid,
                tasks_completed=tasks_completed,
                documents_created=documents_created,
                hours_saved=hours_saved,
                ai_chats=ai_chats,
                last_activity=datetime.now(timezone.utc) if user_profile.get('last_login') else None,
                streak_days=streak_days,
                total_login_days=min(days_active, 30)
            )
            
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return ProfileStats(uid=uid)
    
    async def get_notification_settings(self, uid: str) -> NotificationSettings:
        """Get user's notification preferences from Firestore"""
        try:
            # Try to get existing settings from user's subcollection
            settings_doc = self.firebase_service.db.document(f"users/{uid}").get()
            
            if settings_doc.exists:
                settings_data = settings_doc.to_dict()
                notification_settings = settings_data.get('notification_settings')
                
                if notification_settings:
                    notification_settings['uid'] = uid
                    return NotificationSettings(**notification_settings)
            
            # Return default settings if none exist
            default_settings = NotificationSettings(uid=uid)
            
            # Save default settings to Firestore
            try:
                user_doc_ref = self.firebase_service.db.document(f"users/{uid}")
                user_doc_ref.update({
                    "notification_settings": default_settings.dict(),
                    "updated_at": datetime.now(timezone.utc)
                })
            except Exception as save_error:
                print(f"Warning: Could not save default notification settings: {save_error}")
            
            return default_settings
            
        except Exception as e:
            print(f"Error getting notification settings: {e}")
            return NotificationSettings(uid=uid)
    
    async def update_notification_settings(
        self, 
        uid: str, 
        settings: NotificationSettings
    ) -> NotificationSettings:
        """Update user's notification preferences in Firestore"""
        try:
            settings.uid = uid
            settings.updated_at = datetime.now(timezone.utc)
            settings_data = settings.dict()
            
            # Update the user document with notification settings
            user_doc_ref = self.firebase_service.db.document(f"users/{uid}")
            user_doc_ref.update({
                "notification_settings": settings_data,
                "updated_at": datetime.now(timezone.utc)
            })
            
            print(f"Notification settings updated for user {uid}")
            return settings
            
        except Exception as e:
            raise Exception(f"Failed to update notification settings: {e}")
    
    async def get_user_preferences(self, uid: str) -> UserPreferences:
        """Get user's app preferences from Firestore"""
        try:
            # Try to get existing preferences from user document
            user_doc = self.firebase_service.db.document(f"users/{uid}").get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                preferences_data = user_data.get('user_preferences')
                
                if preferences_data:
                    preferences_data['uid'] = uid
                    return UserPreferences(**preferences_data)
            
            # Return default preferences if none exist
            default_prefs = UserPreferences(uid=uid)
            
            # Save default preferences to Firestore
            try:
                user_doc_ref = self.firebase_service.db.document(f"users/{uid}")
                user_doc_ref.update({
                    "user_preferences": default_prefs.dict(),
                    "updated_at": datetime.now(timezone.utc)
                })
            except Exception as save_error:
                print(f"Warning: Could not save default user preferences: {save_error}")
            
            return default_prefs
            
        except Exception as e:
            print(f"Error getting user preferences: {e}")
            return UserPreferences(uid=uid)
    
    async def update_user_preferences(
        self, 
        uid: str, 
        preferences: UserPreferences
    ) -> UserPreferences:
        """Update user's app preferences in Firestore"""
        try:
            preferences.uid = uid
            preferences.updated_at = datetime.now(timezone.utc)
            prefs_data = preferences.dict()
            
            # Update the user document with preferences
            user_doc_ref = self.firebase_service.db.document(f"users/{uid}")
            user_doc_ref.update({
                "user_preferences": prefs_data,
                "updated_at": datetime.now(timezone.utc)
            })
            
            print(f"User preferences updated for user {uid}")
            return preferences
            
        except Exception as e:
            raise Exception(f"Failed to update user preferences: {e}")
    
    async def delete_account(self, uid: str) -> bool:
        """Soft delete user account"""
        try:
            # Mark account as deleted in Firestore
            await self.firebase_service.update_user_profile(
                uid,
                {
                    "is_active": False,
                    "deleted_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
            )
            
            # Archive user data to deleted_users collection
            try:
                user_data = await self.firebase_service.get_user_profile(uid)
                if user_data:
                    deleted_user_ref = self.firebase_service.db.document(f"deleted_users/{uid}")
                    deleted_user_ref.set({
                        **user_data,
                        "deleted_at": datetime.now(timezone.utc),
                        "archived_at": datetime.now(timezone.utc)
                    })
            except Exception as archive_error:
                print(f"Warning: Could not archive user data: {archive_error}")
            
            # Clean up local avatar files
            try:
                user_avatar_files = [f for f in os.listdir(self.avatar_dir) if f.startswith(f"{uid}_")]
                for avatar_file in user_avatar_files:
                    avatar_path = os.path.join(self.avatar_dir, avatar_file)
                    if os.path.exists(avatar_path):
                        os.remove(avatar_path)
                        print(f"Deleted avatar file: {avatar_file}")
            except Exception as cleanup_error:
                print(f"Warning: Failed to clean up avatar files for {uid}: {cleanup_error}")
            
            print(f"Account {uid} marked for deletion")
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete account: {e}")