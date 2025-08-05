import firebase_admin
from firebase_admin import credentials, firestore, auth
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os
from google.cloud.firestore_v1.base_query import FieldFilter

class FirebaseService:
    """Service for Firebase operations"""
    
    def __init__(self):
        self.db = None
        self._initialized = False
    
    def initialize(self):
        """Initialize Firebase Admin SDK"""
        if self._initialized:
            return
            
        try:
            # Try to get credentials from environment variable first
            cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
            
            if cred_path:
                # Handle relative paths by making them absolute
                if not os.path.isabs(cred_path):
                    cred_path = os.path.join(os.getcwd(), cred_path)
                
                if os.path.exists(cred_path):
                    # Use service account file
                    cred = credentials.Certificate(cred_path)
            else:
                # Try to get credentials from environment variable as JSON string
                cred_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
                if cred_json:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                else:
                    raise ValueError("Firebase credentials not found. Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON")
            
            # Initialize Firebase Admin
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            self._initialized = True
            print("✅ Firebase initialized successfully")
            
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            raise
    
    # ========================================================================
    # COLLECTION OPERATIONS
    # ========================================================================
    
    async def create_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Create a document in a collection"""
        try:
            # Add timestamps
            now = datetime.utcnow()
            data['created_at'] = now
            data['updated_at'] = now
            
            if doc_id:
                doc_ref = self.db.collection(collection).document(doc_id)
                doc_ref.set(data)
                return doc_id
            else:
                doc_ref = self.db.collection(collection).add(data)[1]
                return doc_ref.id
        except Exception as e:
            raise Exception(f"Failed to create document: {e}")
    
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID"""
        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            raise Exception(f"Failed to get document: {e}")
    
    async def update_document(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update a document"""
        try:
            # Add updated timestamp
            data['updated_at'] = datetime.utcnow()
            
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.update(data)
            return True
        except Exception as e:
            raise Exception(f"Failed to update document: {e}")
    
    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """Delete a document"""
        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            return True
        except Exception as e:
            raise Exception(f"Failed to delete document: {e}")
    
    async def query_documents(
        self, 
        collection: str, 
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents with filters"""
        try:
            query = self.db.collection(collection)
            
            # Apply filters
            if filters:
                for field, operator, value in filters:
                    query = query.where(filter=FieldFilter(field, operator, value))
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    query = query.order_by(order_by[1:], direction=firestore.Query.DESCENDING)
                else:
                    query = query.order_by(order_by)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Apply offset
            if offset:
                query = query.offset(offset)
            
            docs = query.stream()
            
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(data)
            
            return results
        except Exception as e:
            raise Exception(f"Failed to query documents: {e}")
    
    async def get_collection_count(self, collection: str, filters: Optional[List[tuple]] = None) -> int:
        """Get count of documents in collection"""
        try:
            query = self.db.collection(collection)
            
            if filters:
                for field, operator, value in filters:
                    query = query.where(filter=FieldFilter(field, operator, value))
            
            docs = query.stream()
            return len(list(docs))
        except Exception as e:
            raise Exception(f"Failed to get collection count: {e}")
    
    # ========================================================================
    # USER OPERATIONS
    # ========================================================================
    
    async def create_user_profile(self, uid: str, user_data: Dict[str, Any]) -> bool:
        """Create user profile in Firestore"""
        try:
            await self.create_document("users", user_data, uid)
            return True
        except Exception as e:
            raise Exception(f"Failed to create user profile: {e}")
    
    async def get_user_profile(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get user profile from Firestore"""
        return await self.get_document("users", uid)
    
    async def update_user_profile(self, uid: str, user_data: Dict[str, Any]) -> bool:
        """Update user profile"""
        return await self.update_document("users", uid, user_data)
    
    # ========================================================================
    # USER-SPECIFIC DOCUMENT OPERATIONS
    # ========================================================================
    
    async def get_user_documents(
        self, 
        user_id: str, 
        collection: str,
        document_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get documents for a specific user"""
        filters = [("user_id", "==", user_id)]
        
        if document_type:
            filters.append(("document_type", "==", document_type))
        
        return await self.query_documents(
            collection, 
            filters=filters,
            order_by="-created_at",
            limit=limit
        )
    
    async def verify_document_ownership(self, collection: str, doc_id: str, user_id: str) -> bool:
        """Verify if user owns the document"""
        doc = await self.get_document(collection, doc_id)
        return doc is not None and doc.get("user_id") == user_id
    
    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    
    async def batch_create(self, operations: List[Dict[str, Any]]) -> bool:
        """Perform batch write operations"""
        try:
            batch = self.db.batch()
            
            for op in operations:
                collection = op['collection']
                data = op['data']
                doc_id = op.get('doc_id')
                
                # Add timestamps
                now = datetime.utcnow()
                data['created_at'] = now
                data['updated_at'] = now
                
                if doc_id:
                    doc_ref = self.db.collection(collection).document(doc_id)
                else:
                    doc_ref = self.db.collection(collection).document()
                
                batch.set(doc_ref, data)
            
            batch.commit()
            return True
        except Exception as e:
            raise Exception(f"Failed to perform batch operations: {e}")
    
    # ========================================================================
    # SEARCH OPERATIONS
    # ========================================================================
    
    async def search_documents(
        self, 
        collection: str, 
        search_term: str, 
        search_fields: List[str],
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search documents by text (basic implementation)"""
        try:
            # This is a basic implementation. For advanced search, consider using Algolia or Elasticsearch
            filters = []
            
            if user_id:
                filters.append(("user_id", "==", user_id))
            
            documents = await self.query_documents(collection, filters=filters, limit=limit * 2)
            
            # Filter documents that contain search term in specified fields
            search_term = search_term.lower()
            results = []
            
            for doc in documents:
                for field in search_fields:
                    if field in doc and isinstance(doc[field], str):
                        if search_term in doc[field].lower():
                            results.append(doc)
                            break
                
                if len(results) >= limit:
                    break
            
            return results
        except Exception as e:
            raise Exception(f"Failed to search documents: {e}")
    
    # ========================================================================
    # ANALYTICS & STATS
    # ========================================================================
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics"""
        try:
            stats = {}
            
            # Count documents
            stats['total_documents'] = len(await self.get_user_documents(user_id, "documents"))
            stats['total_tasks'] = len(await self.get_user_documents(user_id, "tasks"))
            stats['total_notes'] = len(await self.get_user_documents(user_id, "notes"))
            
            # Count completed tasks
            completed_tasks = await self.query_documents(
                "tasks",
                filters=[
                    ("user_id", "==", user_id),
                    ("status", "==", "completed")
                ]
            )
            stats['completed_tasks'] = len(completed_tasks)
            
            return stats
        except Exception as e:
            raise Exception(f"Failed to get user stats: {e}")
    
    # ========================================================================
    # AUTHENTICATION HELPERS  
    # ========================================================================
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify Firebase ID token"""
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except Exception as e:
            raise Exception(f"Invalid token: {e}")
    
    def create_custom_token(self, uid: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
        """Create custom token for user"""
        try:
            return auth.create_custom_token(uid, additional_claims)
        except Exception as e:
            raise Exception(f"Failed to create custom token: {e}")