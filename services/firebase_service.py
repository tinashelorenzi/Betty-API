# services/firebase_service.py - COMPLETE REWRITE WITH LOCAL FILE REFERENCES
import firebase_admin
from firebase_admin import credentials, auth, firestore
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class FirebaseService:
    """Firebase service for authentication and database operations with local file references"""
    
    def __init__(self):
        self._initialized = False
        self.db = None
        self.server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
    
    def initialize(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not self._initialized:
                # Get service account path from environment
                service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
                
                if service_account_path and os.path.exists(service_account_path):
                    # Initialize with service account
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                else:
                    # Initialize with default credentials (for development)
                    firebase_admin.initialize_app()
                
                self.db = firestore.client()
                self._initialized = True
                print("✅ Firebase initialized successfully")
                
        except Exception as e:
            print(f"⚠️ Firebase initialization failed: {e}")
            raise e
    
    def get_server_url(self) -> str:
        """Get server base URL for constructing file URLs"""
        return self.server_base_url
    
    def build_avatar_url(self, filename: str) -> Optional[str]:
        """Build full avatar URL from filename stored in database"""
        if filename:
            return f"{self.get_server_url()}/uploads/avatars/{filename}"
        return None
    
    def extract_filename_from_url(self, url: str) -> Optional[str]:
        """Extract filename from avatar URL (for backward compatibility)"""
        if url and "/uploads/avatars/" in url:
            return url.split("/uploads/avatars/")[-1]
        return None
    
    # ============================================================================
    # USER PROFILE OPERATIONS
    # ============================================================================
    
    def get_user_document_ref(self, uid: str):
        """Get reference to user document"""
        return self.db.document(f"users/{uid}")
    
    async def create_user_profile(self, uid: str, profile_data: Dict[str, Any]) -> bool:
        """Create user profile in Firestore"""
        try:
            user_ref = self.get_user_document_ref(uid)
            
            # Ensure timestamps are set
            profile_data['created_at'] = datetime.utcnow()
            profile_data['updated_at'] = datetime.utcnow()
            
            # Initialize with default settings
            if 'notification_settings' not in profile_data:
                profile_data['notification_settings'] = {
                    'push_notifications': True,
                    'email_notifications': True,
                    'task_reminders': 'all',
                    'document_updates': 'important',
                    'ai_suggestions': 'all',
                    'marketing_emails': False,
                    'security_alerts': True,
                    'weekly_digest': True,
                    'weekend_notifications': False,
                    'created_at': datetime.utcnow()
                }
            
            if 'user_preferences' not in profile_data:
                profile_data['user_preferences'] = {
                    'theme': 'light',
                    'language': 'en',
                    'currency': 'ZAR',
                    'date_format': 'DD/MM/YYYY',
                    'time_format': '24h',
                    'default_view': 'home',
                    'auto_save': True,
                    'analytics_enabled': True,
                    'created_at': datetime.utcnow()
                }
            
            user_ref.set(profile_data)
            print(f"✅ User profile created for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create user profile: {e}")
            return False
    
    async def get_user_profile(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get user profile from Firestore and build avatar URL"""
        try:
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if doc.exists:
                profile_data = doc.to_dict()
                
                # Build avatar URL from filename if exists
                avatar_filename = profile_data.get('avatar_filename')
                if avatar_filename:
                    profile_data['avatar_url'] = self.build_avatar_url(avatar_filename)
                else:
                    # Check for legacy avatar_url and convert to filename
                    legacy_url = profile_data.get('avatar_url')
                    if legacy_url:
                        filename = self.extract_filename_from_url(legacy_url)
                        if filename:
                            profile_data['avatar_filename'] = filename
                            profile_data['avatar_url'] = self.build_avatar_url(filename)
                            # Update database to store filename instead of URL
                            await self.update_user_profile(uid, {'avatar_filename': filename})
                
                return profile_data
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to get user profile: {e}")
            return None
    
    async def update_user_profile(self, uid: str, update_data: Dict[str, Any]) -> bool:
        """Update user profile in Firestore"""
        try:
            user_ref = self.get_user_document_ref(uid)
            
            # Always update timestamp
            update_data['updated_at'] = datetime.utcnow()
            
            # Handle avatar URL -> filename conversion
            if 'avatar_url' in update_data:
                avatar_url = update_data.pop('avatar_url')  # Remove URL from update
                filename = self.extract_filename_from_url(avatar_url)
                if filename:
                    update_data['avatar_filename'] = filename
            
            user_ref.update(update_data)
            print(f"✅ User profile updated for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user profile: {e}")
            return False
    
    async def delete_user_profile(self, uid: str) -> bool:
        """Delete user profile from Firestore"""
        try:
            user_ref = self.get_user_document_ref(uid)
            user_ref.delete()
            print(f"✅ User profile deleted for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delete user profile: {e}")
            return False
    
    # ============================================================================
    # USER SUBCOLLECTIONS OPERATIONS
    # ============================================================================
    
    def get_user_collection_ref(self, uid: str, collection_name: str):
        """Get reference to user's subcollection"""
        return self.db.collection(f"users/{uid}/{collection_name}")
    
    async def add_to_user_collection(self, uid: str, collection_name: str, data: Dict[str, Any]) -> Optional[str]:
        """Add document to user's subcollection"""
        try:
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            
            # Add metadata
            data['user_id'] = uid
            data['created_at'] = datetime.utcnow()
            data['updated_at'] = datetime.utcnow()
            
            # Add document and return ID
            timestamp, doc_ref = collection_ref.add(data)
            print(f"✅ Added document to {uid}/{collection_name}: {doc_ref.id}")
            return doc_ref.id
            
        except Exception as e:
            print(f"❌ Failed to add to user collection {collection_name}: {e}")
            return None
    
    async def get_user_collection(self, uid: str, collection_name: str, limit: int = 100, order_by: str = 'created_at') -> List[Dict[str, Any]]:
        """Get documents from user's subcollection"""
        try:
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            
            # Build query with ordering and limit
            query = collection_ref.order_by(order_by, direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()
            
            results = []
            for doc in docs:
                doc_data = doc.to_dict()
                doc_data['id'] = doc.id
                results.append(doc_data)
            
            return results
            
        except Exception as e:
            print(f"❌ Failed to get user collection {collection_name}: {e}")
            return []
    
    async def get_user_document(self, uid: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get specific document from user's subcollection"""
        try:
            doc_ref = self.get_user_collection_ref(uid, collection_name).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                doc_data = doc.to_dict()
                doc_data['id'] = doc.id
                return doc_data
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to get user document: {e}")
            return None
    
    async def update_user_document(self, uid: str, collection_name: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update document in user's subcollection"""
        try:
            doc_ref = self.get_user_collection_ref(uid, collection_name).document(doc_id)
            data['updated_at'] = datetime.utcnow()
            doc_ref.update(data)
            print(f"✅ Updated document {doc_id} in {uid}/{collection_name}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user document: {e}")
            return False
    
    async def delete_user_document(self, uid: str, collection_name: str, doc_id: str) -> bool:
        """Delete document from user's subcollection"""
        try:
            doc_ref = self.get_user_collection_ref(uid, collection_name).document(doc_id)
            doc_ref.delete()
            print(f"✅ Deleted document {doc_id} from {uid}/{collection_name}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delete user document: {e}")
            return False
    
    async def count_user_collection(self, uid: str, collection_name: str, where_conditions: List[tuple] = None) -> int:
        """Count documents in user's subcollection with optional conditions"""
        try:
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            query = collection_ref
            
            # Apply where conditions if provided
            if where_conditions:
                for field, operator, value in where_conditions:
                    query = query.where(field, operator, value)
            
            # Count documents
            docs = query.stream()
            count = sum(1 for _ in docs)
            return count
            
        except Exception as e:
            print(f"❌ Failed to count user collection {collection_name}: {e}")
            return 0
    
    # ============================================================================
    # NOTIFICATION SETTINGS
    # ============================================================================
    
    async def get_notification_settings(self, uid: str) -> Dict[str, Any]:
        """Get user notification settings"""
        try:
            user_profile = await self.get_user_profile(uid)
            if user_profile and 'notification_settings' in user_profile:
                settings = user_profile['notification_settings']
                settings['uid'] = uid
                return settings
            
            # Return default settings
            return {
                'uid': uid,
                'push_notifications': True,
                'email_notifications': True,
                'task_reminders': 'all',
                'document_updates': 'important',
                'ai_suggestions': 'all',
                'marketing_emails': False,
                'security_alerts': True,
                'weekly_digest': True,
                'weekend_notifications': False,
                'created_at': datetime.utcnow()
            }
            
        except Exception as e:
            print(f"❌ Failed to get notification settings: {e}")
            return {'uid': uid}
    
    async def update_notification_settings(self, uid: str, settings: Dict[str, Any]) -> bool:
        """Update user notification settings"""
        try:
            settings['updated_at'] = datetime.utcnow()
            return await self.update_user_profile(uid, {'notification_settings': settings})
            
        except Exception as e:
            print(f"❌ Failed to update notification settings: {e}")
            return False
    
    # ============================================================================
    # USER PREFERENCES
    # ============================================================================
    
    async def get_user_preferences(self, uid: str) -> Dict[str, Any]:
        """Get user app preferences"""
        try:
            user_profile = await self.get_user_profile(uid)
            if user_profile and 'user_preferences' in user_profile:
                preferences = user_profile['user_preferences']
                preferences['uid'] = uid
                return preferences
            
            # Return default preferences
            return {
                'uid': uid,
                'theme': 'light',
                'language': 'en',
                'currency': 'ZAR',
                'date_format': 'DD/MM/YYYY',
                'time_format': '24h',
                'default_view': 'home',
                'auto_save': True,
                'analytics_enabled': True,
                'created_at': datetime.utcnow()
            }
            
        except Exception as e:
            print(f"❌ Failed to get user preferences: {e}")
            return {'uid': uid}
    
    async def update_user_preferences(self, uid: str, preferences: Dict[str, Any]) -> bool:
        """Update user app preferences"""
        try:
            preferences['updated_at'] = datetime.utcnow()
            return await self.update_user_profile(uid, {'user_preferences': preferences})
            
        except Exception as e:
            print(f"❌ Failed to update user preferences: {e}")
            return False
    
    # ============================================================================
    # STATISTICS AND ANALYTICS
    # ============================================================================
    
    async def get_user_stats(self, uid: str) -> Dict[str, Any]:
        """Get comprehensive user activity statistics"""
        try:
            # Count documents in various subcollections
            tasks_total = await self.count_user_collection(uid, "tasks")
            tasks_completed = await self.count_user_collection(uid, "tasks", [("status", "==", "completed")])
            tasks_pending = await self.count_user_collection(uid, "tasks", [("status", "==", "pending")])
            
            documents_created = await self.count_user_collection(uid, "documents")
            ai_conversations = await self.count_user_collection(uid, "conversations")
            notes_created = await self.count_user_collection(uid, "notes")
            
            # Get user profile for account age
            user_profile = await self.get_user_profile(uid)
            account_age_days = 1
            last_activity = None
            
            if user_profile:
                created_at = user_profile.get('created_at')
                if created_at:
                    if isinstance(created_at, str):
                        try:
                            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            account_age_days = max(1, (datetime.utcnow() - created_date).days)
                        except ValueError:
                            pass
                    elif isinstance(created_at, datetime):
                        account_age_days = max(1, (datetime.utcnow() - created_at).days)
                
                # Get last activity
                last_login = user_profile.get('last_login') or user_profile.get('updated_at')
                if last_login:
                    if isinstance(last_login, str):
                        try:
                            last_activity = datetime.fromisoformat(last_login.replace('Z', '+00:00'))
                        except ValueError:
                            pass
                    elif isinstance(last_login, datetime):
                        last_activity = last_login
            
            # Calculate estimated hours saved
            hours_saved = round(
                (tasks_completed * 0.25) +  # 15 min per task
                (documents_created * 0.5) +  # 30 min per document
                (ai_conversations * 0.17) +  # 10 min per conversation
                (notes_created * 0.08),      # 5 min per note
                1
            )
            
            # Calculate streak (simple version)
            streak_days = 0
            if last_activity:
                days_since_activity = (datetime.utcnow() - last_activity).days
                if days_since_activity <= 1:
                    streak_days = min(account_age_days, 7)  # Max 7 day streak
            
            return {
                'uid': uid,
                'tasks_completed': tasks_completed,
                'tasks_pending': tasks_pending,
                'tasks_total': tasks_total,
                'documents_created': documents_created,
                'ai_conversations': ai_conversations,
                'notes_created': notes_created,
                'hours_saved': hours_saved,
                'last_activity': last_activity,
                'streak_days': streak_days,
                'account_age_days': account_age_days,
                'total_login_days': min(account_age_days, 30)  # Estimate
            }
            
        except Exception as e:
            print(f"❌ Failed to get user stats: {e}")
            return {'uid': uid}
    
    async def get_user_activity_summary(self, uid: str, days: int = 30) -> Dict[str, Any]:
        """Get user activity summary for specified period"""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Count recent activities
            recent_tasks = await self.count_user_collection(
                uid, "tasks", 
                [("updated_at", ">=", start_date)]
            )
            
            recent_documents = await self.count_user_collection(
                uid, "documents",
                [("created_at", ">=", start_date)]
            )
            
            recent_conversations = await self.count_user_collection(
                uid, "conversations",
                [("created_at", ">=", start_date)]
            )
            
            return {
                "period_days": days,
                "tasks_activity": recent_tasks,
                "documents_created": recent_documents,
                "ai_conversations": recent_conversations,
                "total_activity": recent_tasks + recent_documents + recent_conversations,
                "start_date": start_date,
                "end_date": end_date
            }
            
        except Exception as e:
            print(f"❌ Failed to get activity summary: {e}")
            return {
                "period_days": days,
                "tasks_activity": 0,
                "documents_created": 0,
                "ai_conversations": 0,
                "total_activity": 0
            }
    
    # ============================================================================
    # TOKEN OPERATIONS (for auth service integration)
    # ============================================================================
    
    def verify_token(self, id_token: str) -> Dict[str, Any]:
        """Verify Firebase ID token"""
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except Exception as e:
            print(f"❌ Token verification failed: {e}")
            raise e
    
    def create_custom_token(self, uid: str, additional_claims: Dict[str, Any] = None) -> str:
        """Create custom Firebase token"""
        try:
            custom_token = auth.create_custom_token(uid, additional_claims)
            return custom_token
        except Exception as e:
            print(f"❌ Failed to create custom token: {e}")
            raise e
    
    # ============================================================================
    # CLEANUP OPERATIONS
    # ============================================================================
    
    async def cleanup_user_data(self, uid: str) -> bool:
        """Clean up all user data (for account deletion)"""
        try:
            # List of subcollections to clean up
            subcollections = ["tasks", "documents", "conversations", "notes", "settings"]
            
            for collection_name in subcollections:
                try:
                    collection_ref = self.get_user_collection_ref(uid, collection_name)
                    docs = collection_ref.stream()
                    
                    for doc in docs:
                        doc.reference.delete()
                    
                    print(f"✅ Cleaned up {collection_name} for user {uid}")
                except Exception as cleanup_error:
                    print(f"⚠️ Could not cleanup {collection_name}: {cleanup_error}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to cleanup user data: {e}")
            return False
    
    async def archive_user_data(self, uid: str) -> bool:
        """Archive user data to deleted_users collection"""
        try:
            user_data = await self.get_user_profile(uid)
            if user_data:
                # Archive to deleted_users collection
                deleted_user_ref = self.db.document(f"deleted_users/{uid}")
                deleted_user_ref.set({
                    **user_data,
                    "deleted_at": datetime.utcnow(),
                    "archived_at": datetime.utcnow()
                })
                
                print(f"✅ User data archived for {uid}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Failed to archive user data: {e}")
            return False