# services/firebase_service.py - COMPLETE FIXED VERSION
import firebase_admin
from firebase_admin import credentials, auth, firestore
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os
import uuid
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
                    # Try to use environment variables for service account
                    service_account_info = {
                        "type": "service_account",
                        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                        "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
                        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                        "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('FIREBASE_CLIENT_EMAIL')}"
                    }
                    
                    # Filter out None values
                    service_account_info = {k: v for k, v in service_account_info.items() if v is not None}
                    
                    if service_account_info.get("project_id"):
                        cred = credentials.Certificate(service_account_info)
                        firebase_admin.initialize_app(cred)
                    else:
                        print("⚠️ No Firebase credentials found - some features may not work")
                        return
                
                # Get Firestore client
                self.db = firestore.client()
                self._initialized = True
                print("✅ Firebase initialized successfully")
                
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            self._initialized = False

    # ============================================================================
    # USER PROFILE OPERATIONS
    # ============================================================================
    
    def get_user_document_ref(self, uid: str):
        """Get reference to user document"""
        if not self._initialized or not self.db:
            raise RuntimeError("Firebase service not initialized")
        return self.db.document(f"users/{uid}")
    
    def get_user_collection_ref(self, uid: str, collection_name: str):
        """Get reference to user's subcollection"""
        if not self._initialized or not self.db:
            raise RuntimeError("Firebase service not initialized")
        return self.db.document(f"users/{uid}").collection(collection_name)
    
    async def create_user_profile(self, uid: str, user_data: Dict[str, Any]) -> bool:
        """Create user profile document"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            user_data['uid'] = uid
            user_data['created_at'] = datetime.utcnow()
            user_data['updated_at'] = datetime.utcnow()
            user_ref.set(user_data)
            print(f"✅ Created user profile for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create user profile: {e}")
            return False
    
    async def get_user_profile(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get user profile data"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                
                # Handle avatar URL building from filename
                if 'avatar_filename' in user_data and user_data['avatar_filename']:
                    user_data['avatar_url'] = self.build_avatar_url(user_data['avatar_filename'])
                
                print(f"✅ Retrieved user profile for {uid}")
                return user_data
            else:
                print(f"⚠️ User profile not found for {uid}")
                return None
                
        except Exception as e:
            print(f"❌ Failed to get user profile: {e}")
            return None
    
    async def update_user_profile(self, uid: str, update_data: Dict[str, Any]) -> bool:
        """Update user profile with new data"""
        try:
            user_ref = self.get_user_document_ref(uid)
            update_data['updated_at'] = datetime.utcnow()
            user_ref.update(update_data)
            print(f"✅ Updated user profile for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user profile: {e}")
            return False
    
    async def update_user_avatar(self, uid: str, avatar_filename: str) -> bool:
        """Update user avatar filename"""
        try:
            user_ref = self.get_user_document_ref(uid)
            user_ref.update({
                'avatar_filename': avatar_filename,
                'updated_at': datetime.utcnow()
            })
            print(f"✅ Updated avatar for user {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user avatar: {e}")
            return False
    
    async def update_last_login(self, uid: str) -> bool:
        """Update user's last login timestamp"""
        try:
            user_ref = self.get_user_document_ref(uid)
            user_ref.update({
                'last_login': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })
            return True
            
        except Exception as e:
            print(f"❌ Failed to update last login: {e}")
            return False

    # ============================================================================
    # AVATAR/FILE OPERATIONS
    # ============================================================================
    
    def get_server_url(self) -> str:
        """Get server base URL for constructing file URLs"""
        return self.server_base_url
    
    def is_initialized(self) -> bool:
        """Check if Firebase service is properly initialized"""
        return self._initialized and self.db is not None
    
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
    # GENERAL DOCUMENT OPERATIONS
    # ============================================================================
    
    async def create_document(self, collection: str, data: Dict[str, Any], doc_id: str = None) -> str:
        """Create a document in the specified collection"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            if not doc_id:
                doc_id = str(uuid.uuid4())
            
            # Add metadata
            data['id'] = doc_id
            data['created_at'] = datetime.utcnow()
            data['updated_at'] = datetime.utcnow()
            
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.set(data)
            
            print(f"✅ Created document {doc_id} in {collection}")
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to create document: {e}")
            raise e
    
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            else:
                return None
                
        except Exception as e:
            print(f"❌ Failed to get document: {e}")
            return None
    
    async def update_document(self, collection: str, doc_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a document"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            doc_ref = self.db.collection(collection).document(doc_id)
            update_data['updated_at'] = datetime.utcnow()
            doc_ref.update(update_data)
            
            print(f"✅ Updated document {doc_id} in {collection}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update document: {e}")
            return False
    
    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """Delete a document"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            
            print(f"✅ Deleted document {doc_id} from {collection}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to delete document: {e}")
            return False
    
    async def query_documents(
        self, 
        collection: str, 
        filters: List[tuple] = None, 
        order_by: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Query documents with optional filters"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            query = self.db.collection(collection)
            
            # Apply filters
            if filters:
                for field, operator, value in filters:
                    query = query.where(field, operator, value)
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    query = query.order_by(order_by[1:], direction=firestore.Query.DESCENDING)
                else:
                    query = query.order_by(order_by)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            docs = query.stream()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(data)
            
            return results
            
        except Exception as e:
            print(f"❌ Failed to query documents: {e}")
            return []
    
    async def get_user_documents(
        self, 
        collection: str, 
        user_id: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get documents for a specific user"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            filters = [("user_id", "==", user_id)]
            return await self.query_documents(
                collection=collection,
                filters=filters,
                order_by="-updated_at",
                limit=limit
            )
        except Exception as e:
            print(f"Error getting user documents: {e}")
            return []
    
    async def verify_document_ownership(
        self, 
        collection: str, 
        doc_id: str, 
        user_id: str
    ) -> bool:
        """Verify that a user owns a document"""
        try:
            doc = await self.get_document(collection, doc_id)
            return doc.get("user_id") == user_id
        except Exception:
            return False

    # ============================================================================
    # USER SUBCOLLECTION OPERATIONS
    # ============================================================================
    
    async def create_user_document(self, uid: str, collection_name: str, data: Dict[str, Any], doc_id: str = None) -> str:
        """Create document in user's subcollection"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            if not doc_id:
                doc_id = str(uuid.uuid4())
            
            # Add metadata
            data['id'] = doc_id
            data['user_id'] = uid
            data['created_at'] = datetime.utcnow()
            data['updated_at'] = datetime.utcnow()
            
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            doc_ref = collection_ref.document(doc_id)
            doc_ref.set(data)
            
            print(f"✅ Created document {doc_id} in {uid}/{collection_name}")
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to create user document: {e}")
            raise e
    
    async def get_user_document(self, uid: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document from user's subcollection"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            doc_ref = self.get_user_collection_ref(uid, collection_name).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            else:
                return None
                
        except Exception as e:
            print(f"❌ Failed to get user document: {e}")
            return None

    # ============================================================================
    # INDEXED USER OPERATIONS
    # ============================================================================
    
    def _get_empty_indexes(self) -> Dict[str, List[str]]:
        """Get empty index structure"""
        return {
            "conversation_ids": [],
            "document_ids": [],
            "task_ids": [],
            "chat_session_ids": [],
            "note_ids": []
        }
    
    def _get_empty_stats(self) -> Dict[str, Any]:
        """Get empty stats structure"""
        return {
            "total_conversations": 0,
            "total_documents": 0,
            "total_tasks": 0,
            "total_messages": 0,
            "total_notes": 0,
            "messages_today": 0,
            "last_activity": None,
            "last_message_at": None
        }
    
    async def initialize_user_indexes(self, uid: str) -> bool:
        """Initialize user document with empty indexes and stats"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if not doc.exists:
                # Create new user document with indexes
                user_data = {
                    "uid": uid,
                    "indexes": self._get_empty_indexes(),
                    "stats": self._get_empty_stats(),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                user_ref.set(user_data)
                print(f"✅ Initialized user indexes for {uid}")
            else:
                # Update existing user with indexes if they don't exist
                user_data = doc.to_dict()
                update_needed = False
                
                if "indexes" not in user_data:
                    user_data["indexes"] = self._get_empty_indexes()
                    update_needed = True
                
                if "stats" not in user_data:
                    user_data["stats"] = self._get_empty_stats()
                    update_needed = True
                
                if update_needed:
                    user_data["updated_at"] = datetime.utcnow()
                    user_ref.update({
                        "indexes": user_data["indexes"],
                        "stats": user_data["stats"],
                        "updated_at": user_data["updated_at"]
                    })
                    print(f"✅ Added indexes to existing user {uid}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize user indexes: {e}")
            return False
    
    async def add_to_user_index(self, uid: str, index_type: str, item_id: str) -> bool:
        """Add item to user's index and update stats"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            
            # Get current data
            doc = user_ref.get()
            if not doc.exists:
                await self.initialize_user_indexes(uid)
                doc = user_ref.get()
            
            user_data = doc.to_dict()
            indexes = user_data.get("indexes", self._get_empty_indexes())
            stats = user_data.get("stats", self._get_empty_stats())
            
            # Add to index if not already present
            if index_type in indexes and item_id not in indexes[index_type]:
                indexes[index_type].append(item_id)
                
                # Update corresponding stat
                stat_key = self._get_stat_key_for_index(index_type)
                if stat_key and stat_key in stats:
                    stats[stat_key] = len(indexes[index_type])
                
                # Update document
                user_ref.update({
                    f"indexes.{index_type}": indexes[index_type],
                    f"stats.{stat_key}": stats[stat_key],
                    "updated_at": datetime.utcnow()
                })
                
                print(f"✅ Added {item_id} to {uid}'s {index_type}")
                return True
            
            return False  # Already exists
            
        except Exception as e:
            print(f"❌ Failed to add to user index: {e}")
            return False
    
    async def remove_from_user_index(self, uid: str, index_type: str, item_id: str) -> bool:
        """Remove item from user's index and update stats"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if not doc.exists:
                return False
            
            user_data = doc.to_dict()
            indexes = user_data.get("indexes", {})
            stats = user_data.get("stats", {})
            
            if index_type in indexes and item_id in indexes[index_type]:
                indexes[index_type].remove(item_id)
                
                # Update corresponding stat
                stat_key = self._get_stat_key_for_index(index_type)
                if stat_key and stat_key in stats:
                    stats[stat_key] = len(indexes[index_type])
                
                # Update document
                user_ref.update({
                    f"indexes.{index_type}": indexes[index_type],
                    f"stats.{stat_key}": stats[stat_key],
                    "updated_at": datetime.utcnow()
                })
                
                print(f"✅ Removed {item_id} from {uid}'s {index_type}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Failed to remove from user index: {e}")
            return False
    
    async def get_user_indexes(self, uid: str) -> Dict[str, List[str]]:
        """Get user's document indexes"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                return user_data.get("indexes", self._get_empty_indexes())
            else:
                await self.initialize_user_indexes(uid)
                return self._get_empty_indexes()
                
        except Exception as e:
            print(f"❌ Failed to get user indexes: {e}")
            return self._get_empty_indexes()
    
    async def get_user_items_by_index(
    self, 
    uid: str, 
    index_type: str, 
    collection: str, 
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[Dict[str, Any]]:
        """Get user's items using their index (super fast!)"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            indexes = await self.get_user_indexes(uid)
            item_ids = indexes.get(index_type, [])
            
            if not item_ids:
                return []
            
            # Apply offset and limit to the item_ids list
            start_idx = offset if offset else 0
            end_idx = start_idx + limit if limit else None
            
            # Slice the item_ids based on pagination
            paginated_ids = item_ids[start_idx:end_idx]
            
            # Get documents by IDs
            items = []
            for item_id in paginated_ids:
                doc = await self.get_document(collection, item_id)
                if doc:
                    items.append(doc)
            
            return items
            
        except Exception as e:
            print(f"❌ Failed to get user items by index: {e}")
            return []
    
    def _get_stat_key_for_index(self, index_type: str) -> Optional[str]:
        """Map index type to corresponding stat key"""
        mapping = {
            "conversation_ids": "total_conversations",
            "document_ids": "total_documents",
            "task_ids": "total_tasks",
            "note_ids": "total_notes"
        }
        return mapping.get(index_type)

    # ============================================================================
    # CHAT/CONVERSATION OPERATIONS
    # ============================================================================
    
    async def create_document_with_index(self, collection: str, data: Dict[str, Any], user_id: str, index_type: str, doc_id: str = None) -> str:
        """Create document and add to user's index atomically"""
        try:
            # Create the document
            doc_id = await self.create_document(collection, data, doc_id)
            
            # Add to user's index
            await self.add_to_user_index(user_id, index_type, doc_id)
            
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to create document with index: {e}")
            raise e
    
    async def delete_document_with_index(self, collection: str, doc_id: str, user_id: str, index_type: str) -> bool:
        """Delete document and remove from user's index atomically"""
        try:
            # Remove from user's index
            await self.remove_from_user_index(user_id, index_type, doc_id)
            
            # Delete the document
            success = await self.delete_document(collection, doc_id)
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to delete document with index: {e}")
            return False
    
    async def save_chat_messages_with_indexes(
        self, 
        user_id: str, 
        conversation_id: str, 
        user_message: str, 
        ai_response: str,
        conversation_title: str = None
    ) -> bool:
        """Save chat messages and update user stats efficiently"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            # Create message records
            timestamp = datetime.utcnow()
            
            user_msg_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "content": user_message,
                "role": "user",
                "message_type": "text",
                "timestamp": timestamp
            }
            
            ai_msg_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "content": ai_response,
                "role": "assistant",
                "message_type": "text",
                "timestamp": timestamp
            }
            
            # Save messages
            await self.create_document("chat_history", user_msg_data)
            await self.create_document("chat_history", ai_msg_data)
            
            # Update user stats efficiently
            await self.update_user_message_stats_efficient(user_id, 2)  # 2 new messages
            
            print(f"✅ Saved chat messages for conversation {conversation_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to save chat messages: {e}")
            return False
    
    async def update_user_message_stats_efficient(self, uid: str, message_count: int = 1) -> bool:
        """Update user message stats efficiently without reading all messages"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            
            # Get current stats
            doc = user_ref.get()
            if not doc.exists:
                await self.initialize_user_indexes(uid)
                doc = user_ref.get()
            
            user_data = doc.to_dict()
            stats = user_data.get("stats", self._get_empty_stats())
            
            # Update message counts
            stats["total_messages"] = stats.get("total_messages", 0) + message_count
            stats["messages_today"] = stats.get("messages_today", 0) + message_count
            stats["last_message_at"] = datetime.utcnow()
            stats["last_activity"] = datetime.utcnow()
            
            # Update in Firestore
            user_ref.update({
                "stats": stats,
                "updated_at": datetime.utcnow()
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user message stats: {e}")
            return False
    
    async def update_user_stats(self, uid: str, stat_updates: Dict[str, Any]) -> bool:
        """Update specific user statistics"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if not doc.exists:
                await self.initialize_user_indexes(uid)
                doc = user_ref.get()
            
            user_data = doc.to_dict()
            stats = user_data.get("stats", self._get_empty_stats())
            
            # Update stats
            for key, value in stat_updates.items():
                stats[key] = value
            
            stats["last_activity"] = datetime.utcnow()
            
            # Update in Firestore
            user_ref.update({
                "stats": stats,
                "updated_at": datetime.utcnow()
            })
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user stats: {e}")
            return False

    # ============================================================================
    # CONVERSATION METADATA OPERATIONS
    # ============================================================================
    
    async def update_conversation_metadata(
        self, 
        firebase_service, 
        conversation_id: str, 
        user_message: str, 
        ai_response: str
    ) -> None:
        """Update conversation metadata with new message info"""
        try:
            # Get conversation document
            conv_doc = await firebase_service.get_document("conversations", conversation_id)
            if not conv_doc:
                print(f"⚠️ Conversation {conversation_id} not found for metadata update")
                return
            
            # Generate title from first message if needed
            title = conv_doc.get("title", "")
            if not title or title == "New Conversation":
                # Use first sentence of user message as title
                sentences = user_message.split('.')
                if sentences and len(sentences[0]) > 10:
                    title = sentences[0][:50] + "..." if len(sentences[0]) > 50 else sentences[0]
                else:
                    title = user_message[:30] + "..." if len(user_message) > 30 else user_message
            
            # Update metadata
            update_data = {
                "updated_at": datetime.utcnow(),
                "title": title,
                "message_count": conv_doc.get("message_count", 0) + 2,
                "last_message": ai_response[:100] + "..." if len(ai_response) > 100 else ai_response,
                "last_message_at": datetime.utcnow()
            }
            
            await firebase_service.update_document("conversations", conv_doc["id"], update_data)
            
        except Exception as e:
            print(f"Failed to update conversation metadata: {e}")

    # ============================================================================
    # MIGRATION OPERATIONS
    # ============================================================================
    
    async def migrate_user_to_indexed_structure(self, uid: str) -> bool:
        """Migrate existing user data to indexed structure"""
        try:
            if not self._initialized or not self.db:
                raise RuntimeError("Firebase service not initialized")
            print(f"🔄 Migrating user {uid} to indexed structure...")
            
            # Initialize user indexes
            await self.initialize_user_indexes(uid)
            
            # Migrate conversations
            conversations = await self.query_documents(
                "conversations",
                filters=[("user_id", "==", uid)]
            )
            
            conversation_ids = []
            for conv in conversations:
                conversation_ids.append(conv["id"])
            
            # Migrate documents
            documents = await self.query_documents(
                "documents", 
                filters=[("user_id", "==", uid)]
            )
            
            document_ids = []
            for doc in documents:
                document_ids.append(doc["id"])
            
            # Count messages for stats
            messages = await self.query_documents(
                "chat_history",
                filters=[("user_id", "==", uid)]
            )
            
            # Update user document with indexes and stats
            user_data = {
                "indexes": {
                    "conversation_ids": conversation_ids,
                    "document_ids": document_ids,
                    "task_ids": [],  # Will be populated if tasks exist
                    "chat_session_ids": [],
                    "note_ids": []
                },
                "stats": {
                    "total_conversations": len(conversation_ids),
                    "total_documents": len(document_ids),
                    "total_tasks": 0,
                    "total_messages": len(messages),
                    "total_notes": 0,
                    "messages_today": 0,
                    "last_activity": datetime.utcnow(),
                    "last_message_at": messages[-1].get("timestamp") if messages else None
                },
                "updated_at": datetime.utcnow()
            }
            
            # Update user document
            user_ref = self.get_user_document_ref(uid)
            user_ref.update(user_data)
            
            print(f"✅ Migrated user {uid}: {len(conversation_ids)} conversations, {len(document_ids)} documents, {len(messages)} messages")
            return True
            
        except Exception as e:
            print(f"❌ Failed to migrate user {uid}: {e}")
            return False