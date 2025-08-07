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
                        # Initialize with default credentials (for development)
                        firebase_admin.initialize_app()
                
                self.db = firestore.client()
                self._initialized = True
                print("✅ Firebase initialized successfully")
                
        except Exception as e:
            print(f"⚠️ Firebase initialization failed: {e}")
            raise e
    
    async def get_user_indexes(self, uid: str) -> Dict[str, Any]:
        """Get user's data indexes"""
        try:
            user_doc = await self.get_user_profile(uid)
            if not user_doc:
                # Initialize user with empty indexes
                await self.initialize_user_indexes(uid)
                return self._get_empty_indexes()
            
            return user_doc.get("indexes", self._get_empty_indexes())
        except Exception as e:
            print(f"❌ Failed to get user indexes: {e}")
            return self._get_empty_indexes()
    
    async def initialize_user_indexes(self, uid: str) -> bool:
        """Initialize user document with empty indexes"""
        try:
            user_data = {
                "indexes": self._get_empty_indexes(),
                "stats": self._get_empty_stats(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            user_ref = self.get_user_document_ref(uid)
            user_ref.set(user_data, merge=True)  # Merge to not overwrite existing data
            print(f"✅ Initialized indexes for user {uid}")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize user indexes: {e}")
            return False
    
    async def add_to_user_index(self, uid: str, index_type: str, item_id: str) -> bool:
        """Add an item ID to user's index array"""
        try:
            user_ref = self.get_user_document_ref(uid)
            
            # Use Firestore transaction to ensure consistency
            transaction = self.db.transaction()
            
            @firestore.transactional
            def update_index(transaction, user_ref):
                # Get current user data
                user_doc = user_ref.get(transaction=transaction)
                user_data = user_doc.to_dict() if user_doc.exists else {}
                
                # Initialize indexes if they don't exist
                if "indexes" not in user_data:
                    user_data["indexes"] = self._get_empty_indexes()
                if "stats" not in user_data:
                    user_data["stats"] = self._get_empty_stats()
                
                # Add to the specific index array
                index_array = user_data["indexes"].get(index_type, [])
                if item_id not in index_array:
                    index_array.append(item_id)
                    user_data["indexes"][index_type] = index_array
                    
                    # Update corresponding stat
                    stat_key = self._get_stat_key_for_index(index_type)
                    if stat_key:
                        user_data["stats"][stat_key] = len(index_array)
                
                user_data["updated_at"] = datetime.utcnow()
                
                # Update the document
                transaction.set(user_ref, user_data, merge=True)
            
            update_index(transaction, user_ref)
            print(f"✅ Added {item_id} to {uid}'s {index_type} index")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add to user index: {e}")
            return False
    
    async def remove_from_user_index(self, uid: str, index_type: str, item_id: str) -> bool:
        """Remove an item ID from user's index array"""
        try:
            user_ref = self.get_user_document_ref(uid)
            
            transaction = self.db.transaction()
            
            @firestore.transactional
            def update_index(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                if not user_doc.exists:
                    return
                
                user_data = user_doc.to_dict()
                indexes = user_data.get("indexes", {})
                stats = user_data.get("stats", {})
                
                # Remove from the specific index array
                index_array = indexes.get(index_type, [])
                if item_id in index_array:
                    index_array.remove(item_id)
                    indexes[index_type] = index_array
                    
                    # Update corresponding stat
                    stat_key = self._get_stat_key_for_index(index_type)
                    if stat_key:
                        stats[stat_key] = len(index_array)
                
                user_data["indexes"] = indexes
                user_data["stats"] = stats
                user_data["updated_at"] = datetime.utcnow()
                
                transaction.set(user_ref, user_data, merge=True)
            
            update_index(transaction, user_ref)
            print(f"✅ Removed {item_id} from {uid}'s {index_type} index")
            return True
            
        except Exception as e:
            print(f"❌ Failed to remove from user index: {e}")
            return False
    
    async def get_user_items_by_index(
        self, 
        uid: str, 
        collection: str, 
        index_type: str, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get user's items using the index for efficient retrieval"""
        try:
            # Get the index from user document
            indexes = await self.get_user_indexes(uid)
            item_ids = indexes.get(index_type, [])
            
            if not item_ids:
                return []
            
            # Apply pagination
            if limit:
                paginated_ids = item_ids[offset:offset + limit]
            else:
                paginated_ids = item_ids[offset:]
            
            # Batch get documents by ID
            items = []
            for item_id in paginated_ids:
                try:
                    item = await self.get_document(collection, item_id)
                    if item:
                        items.append(item)
                except Exception as e:
                    print(f"⚠️ Could not fetch {item_id} from {collection}: {e}")
                    # Remove invalid ID from index
                    await self.remove_from_user_index(uid, index_type, item_id)
            
            return items
            
        except Exception as e:
            print(f"❌ Failed to get user items by index: {e}")
            return []
    
    async def update_user_stats(self, uid: str, stats_update: Dict[str, Any]) -> bool:
        """Update user statistics"""
        try:
            user_ref = self.get_user_document_ref(uid)
            
            transaction = self.db.transaction()
            
            @firestore.transactional
            def update_stats(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                user_data = user_doc.to_dict() if user_doc.exists else {}
                
                if "stats" not in user_data:
                    user_data["stats"] = self._get_empty_stats()
                
                # Update the stats
                user_data["stats"].update(stats_update)
                user_data["updated_at"] = datetime.utcnow()
                
                transaction.set(user_ref, user_data, merge=True)
            
            update_stats(transaction, user_ref)
            print(f"✅ Updated stats for user {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update user stats: {e}")
            return False

    async def create_document_with_index(
        self, 
        collection: str, 
        data: Dict[str, Any], 
        user_id: str,
        index_type: str
    ) -> str:
        """Create document and update user index in a single transaction"""
        try:
            doc_id = str(uuid.uuid4())
            now = datetime.utcnow()
            
            # Prepare document data
            data.update({
                "id": doc_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now
            })
            
            # Create document
            await self.create_document(collection, data, doc_id)
            
            # Update user index
            await self.add_to_user_index(user_id, index_type, doc_id)
            
            print(f"✅ Created {collection} document {doc_id} with index update")
            return doc_id
            
        except Exception as e:
            print(f"❌ Failed to create document with index: {e}")
            raise e
    
    async def delete_document_with_index(
        self, 
        collection: str, 
        doc_id: str, 
        user_id: str,
        index_type: str
    ) -> bool:
        """Delete document and update user index"""
        try:
            # Delete document
            success = await self.delete_document(collection, doc_id)
            
            if success:
                # Remove from user index
                await self.remove_from_user_index(user_id, index_type, doc_id)
                print(f"✅ Deleted {collection} document {doc_id} with index update")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to delete document with index: {e}")
            return False
    
    # ============================================================================
    # HELPER METHODS
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
    
    def _get_stat_key_for_index(self, index_type: str) -> Optional[str]:
        """Map index type to corresponding stat key"""
        mapping = {
            "conversation_ids": "total_conversations",
            "document_ids": "total_documents",
            "task_ids": "total_tasks",
            "note_ids": "total_notes"
        }
        return mapping.get(index_type)
    
    async def migrate_user_to_indexed_structure(self, uid: str) -> bool:
        """Migrate existing user data to indexed structure"""
        try:
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
                    "task_ids": [],  # Add tasks if they exist
                    "chat_session_ids": [],
                    "note_ids": []
                },
                "stats": {
                    "total_conversations": len(conversations),
                    "total_documents": len(documents),
                    "total_messages": len(messages),
                    "total_tasks": 0,
                    "total_notes": 0,
                    "messages_today": 0,  # Calculate this based on today's messages
                    "last_activity": datetime.utcnow(),
                    "last_message_at": messages[-1]["timestamp"] if messages else None
                },
                "updated_at": datetime.utcnow()
            }
            
            user_ref = self.get_user_document_ref(uid)
            user_ref.set(user_data, merge=True)
            
            print(f"✅ Successfully migrated user {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to migrate user {uid}: {e}")
            return False
    
    async def save_chat_messages_with_indexes(
        user_id: str,
        conversation_id: str,
        user_message: str,
        ai_response: str,
        tokens_used: int = 0
    ):
        """Save chat messages and update user statistics automatically"""
        try:
            now = datetime.utcnow()
            
            # Save user message
            user_message_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "user",
                "content": user_message,
                "timestamp": now,
                "message_type": "text"
            }
            
            await firebase_service.create_document("chat_history", user_message_data)
            
            # Save AI response
            ai_message_data = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": ai_response,
                "timestamp": now,
                "message_type": "text",
                "tokens_used": tokens_used,
                "model_used": "claude-3"
            }
            
            await firebase_service.create_document("chat_history", ai_message_data)
            
            # Update user stats (increment by 2 messages)
            await update_user_message_stats_efficient(user_id, 2)
            
            # Update conversation metadata
            await update_conversation_metadata_efficient(user_id, conversation_id, user_message, ai_response)
            
        except Exception as e:
            print(f"Failed to save messages with indexes: {e}")
    
    async def update_user_message_stats_efficient(user_id: str, message_count: int):
        """Efficiently update user message statistics"""
        try:
            # Calculate messages today efficiently
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get current stats
            user_profile = await firebase_service.get_user_profile(user_id)
            current_stats = user_profile.get("stats", {}) if user_profile else {}
            
            # Update total messages
            total_messages = current_stats.get("total_messages", 0) + message_count
            
            # Quick query for today's count
            today_messages = await firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("timestamp", ">=", today_start)
                ]
            )
            
            # Update stats in single operation
            stats_update = {
                "total_messages": total_messages,
                "messages_today": len(today_messages),
                "last_message_at": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            
            await firebase_service.update_user_stats(user_id, stats_update)
            
        except Exception as e:
            print(f"Failed to update message stats: {e}")

async def update_conversation_metadata_efficient(
    user_id: str,
    conversation_id: str,
    user_message: str,
    ai_response: str
):
    """Efficiently update conversation title and metadata"""
    try:
        # Find conversation
        conversations = await firebase_service.query_documents(
            "conversations",
            filters=[
                ("user_id", "==", user_id),
                ("conversation_id", "==", conversation_id)
            ]
        )
        
        if not conversations:
            return
        
        conv_doc = conversations[0]
        
        # Generate title if needed
        title = conv_doc.get("title", "New Chat")
        if title == "New Chat" and len(user_message) > 10:
            sentences = user_message.split('. ')
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
    
    def get_user_collection_ref(self, uid: str, collection_name: str):
        """Get reference to user's subcollection"""
        return self.db.document(f"users/{uid}").collection(collection_name)
    
    async def create_user_profile(self, uid: str, user_data: Dict[str, Any]) -> bool:
        """Create user profile document"""
        try:
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
            user_ref = self.get_user_document_ref(uid)
            doc = user_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                
                # Handle avatar URL building from filename
                if 'avatar_filename' in user_data and user_data['avatar_filename']:
                    user_data['avatar_url'] = self.build_avatar_url(user_data['avatar_filename'])
                
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
    # DOCUMENT OPERATIONS - FIXED create_document METHOD
    # ============================================================================
    
    async def create_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Create a new document in Firestore - FIXED METHOD"""
        try:
            if not self.db:
                raise Exception("Firebase not initialized")
            
            # Add timestamps
            now = datetime.utcnow()
            data["created_at"] = now
            data["updated_at"] = now
            
            # Generate ID if not provided
            if not doc_id:
                doc_id = str(uuid.uuid4())
            
            # Add the document ID to the data
            data["id"] = doc_id
            
            # Create the document
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.set(data)
            
            return doc_id
            
        except Exception as e:
            print(f"Error creating document in {collection}: {e}")
            raise Exception(f"Failed to create document: {e}")
    
    async def get_document(self, collection: str, doc_id: str) -> Dict[str, Any]:
        """Get a document from Firestore"""
        try:
            if not self.db:
                raise Exception("Firebase not initialized")
            
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            else:
                raise Exception(f"Document {doc_id} not found in {collection}")
                
        except Exception as e:
            print(f"Error getting document {doc_id} from {collection}: {e}")
            raise Exception(f"Failed to get document: {e}")
    
    async def update_document(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update a document in Firestore"""
        try:
            if not self.db:
                raise Exception("Firebase not initialized")
            
            # Add update timestamp
            data["updated_at"] = datetime.utcnow()
            
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.update(data)
            
            return True
            
        except Exception as e:
            print(f"Error updating document {doc_id} in {collection}: {e}")
            raise Exception(f"Failed to update document: {e}")
    
    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """Delete a document from Firestore"""
        try:
            if not self.db:
                raise Exception("Firebase not initialized")
            
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            
            return True
            
        except Exception as e:
            print(f"Error deleting document {doc_id} from {collection}: {e}")
            raise Exception(f"Failed to delete document: {e}")
    
    async def query_documents(
        self, 
        collection: str, 
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents from Firestore with filters - FIXED VERSION"""
        try:
            if not self.db:
                raise Exception("Firebase not initialized")
            
            query = self.db.collection(collection)
            
            # Apply filters using proper keyword argument syntax
            if filters:
                for field, operator, value in filters:
                    # Use filter keyword argument instead of positional arguments
                    query = query.where(filter=firestore.FieldFilter(field, operator, value))
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    # Descending order
                    field = order_by[1:]
                    query = query.order_by(field, direction=firestore.Query.DESCENDING)
                else:
                    # Ascending order
                    query = query.order_by(order_by)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            docs = query.stream()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)
            
            return results
            
        except Exception as e:
            print(f"Error querying documents from {collection}: {e}")
            raise Exception(f"Failed to query documents: {e}")
    
    async def get_user_documents(
        self, 
        user_id: str, 
        collection: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get documents for a specific user"""
        try:
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
    
    async def query_user_documents(
        self,
        uid: str,
        collection_name: str,
        where_conditions: List[tuple] = None,
        order_by: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """Query documents from user's subcollection - FIXED VERSION"""
        try:
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            query = collection_ref
            
            # Apply where conditions using proper syntax
            if where_conditions:
                for field, operator, value in where_conditions:
                    # Use filter keyword argument
                    query = query.where(filter=firestore.FieldFilter(field, operator, value))
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    field = order_by[1:]
                    query = query.order_by(field, direction=firestore.Query.DESCENDING)
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
            print(f"❌ Failed to query user documents: {e}")
            return []
    
    async def update_user_document(self, uid: str, collection_name: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update document in user's subcollection"""
        try:
            data['updated_at'] = datetime.utcnow()
            doc_ref = self.get_user_collection_ref(uid, collection_name).document(doc_id)
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
        """Count documents in user's subcollection with optional conditions - FIXED VERSION"""
        try:
            collection_ref = self.get_user_collection_ref(uid, collection_name)
            query = collection_ref
            
            # Apply where conditions if provided using proper syntax
            if where_conditions:
                for field, operator, value in where_conditions:
                    # Use filter keyword argument
                    query = query.where(filter=firestore.FieldFilter(field, operator, value))
            
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
            return {}
    
    async def update_notification_settings(self, uid: str, settings: Dict[str, Any]) -> bool:
        """Update user notification settings"""
        try:
            user_ref = self.get_user_document_ref(uid)
            user_ref.update({
                'notification_settings': settings,
                'updated_at': datetime.utcnow()
            })
            print(f"✅ Updated notification settings for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update notification settings: {e}")
            return False
    
    # ============================================================================
    # PREFERENCES OPERATIONS
    # ============================================================================
    
    async def get_user_preferences(self, uid: str) -> Dict[str, Any]:
        """Get user preferences"""
        try:
            user_profile = await self.get_user_profile(uid)
            if user_profile and 'preferences' in user_profile:
                prefs = user_profile['preferences']
                prefs['uid'] = uid
                return prefs
            
            # Return default preferences
            return {
                'uid': uid,
                'theme': 'auto',
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
            return {}
    
    async def update_user_preferences(self, uid: str, preferences: Dict[str, Any]) -> bool:
        """Update user preferences"""
        try:
            user_ref = self.get_user_document_ref(uid)
            user_ref.update({
                'preferences': preferences,
                'updated_at': datetime.utcnow()
            })
            print(f"✅ Updated preferences for {uid}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update preferences: {e}")
            return False
    
    # ============================================================================
    # AUTHENTICATION OPERATIONS
    # ============================================================================
    
    def verify_id_token(self, id_token: str) -> Dict[str, Any]:
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