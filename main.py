from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
from typing import Optional
import os
import jwt
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our custom modules
from services.firebase_service import FirebaseService
from services.auth_service import AuthService
from services.document_service import DocumentService
from services.ai_service import AIService
from services.planner_service import PlannerService
from services.google_service import GoogleService
from services.profile_service import ProfileService
from models.user_models import (
    UserCreate, UserResponse, UserUpdate, ProfileStats, 
    NotificationSettings, UserPreferences
)
from models.document_models import DocumentCreate, DocumentResponse, DocumentUpdate
from models.chat_models import ChatMessage, ChatResponse
from models.planner_models import TaskCreate, TaskResponse, TaskUpdate, NoteCreate, NoteResponse

# Initialize services
firebase_service = FirebaseService()
auth_service = AuthService(firebase_service)
google_service = GoogleService(firebase_service)
document_service = DocumentService(firebase_service, google_service)
ai_service = AIService(firebase_service)
planner_service = PlannerService(firebase_service)
profile_service = ProfileService(firebase_service, auth_service)

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Betty Backend starting up...")
    
    # Create uploads directory if it doesn't exist
    os.makedirs("uploads/avatars", exist_ok=True)
    print("✅ Upload directories created")
    
    try:
        firebase_service.initialize()
        print("✅ Firebase initialized")
    except Exception as e:
        print(f"⚠️  Firebase initialization failed: {e}")
        print("The app will continue but Firebase features may not work")
    yield
    # Shutdown
    print("👋 Betty Backend shutting down...")

app = FastAPI(
    title="Betty - Office Genius API",
    description="Backend API for Betty, your AI-powered office assistant",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files for serving uploaded images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS middleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    try:
        token = credentials.credentials
        user_data = await auth_service.verify_token(token)
        return user_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_admin_user(current_user = Depends(get_current_user)):
    """Ensure the current user has admin privileges"""
    try:
        # Check if user is admin (you might have an 'is_admin' field or specific admin UIDs)
        user_profile = await firebase_service.get_user_profile(current_user["uid"])
        
        if not user_profile:
            raise HTTPException(status_code=403, detail="User profile not found")
        
        # Method 1: Check for admin flag
        if user_profile.get("is_admin", False):
            return current_user
        
        # Method 2: Check for specific admin UIDs (more secure)
        ADMIN_UIDS = [
            "your-admin-uid-1",  # Replace with your actual admin UID
            "your-admin-uid-2",  # Add more admin UIDs as needed
        ]
        
        if current_user["uid"] in ADMIN_UIDS:
            return current_user
        
        # Method 3: Check for admin email domains
        admin_email_domains = ["@yourdomain.com"]  # Replace with your domain
        user_email = current_user.get("email", "")
        
        if any(user_email.endswith(domain) for domain in admin_email_domains):
            return current_user
        
        raise HTTPException(
            status_code=403, 
            detail="Admin access required for this operation"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Admin verification failed: {str(e)}"
        )

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "message": "Betty Backend is running!",
        "firebase_initialized": firebase_service._initialized,
        "ai_initialized": ai_service.model is not None
    }

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.post("/auth/register", response_model=UserResponse)
async def register_user(user_data: UserCreate):
    """Register a new user"""
    try:
        user = await auth_service.create_user(user_data)
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login")
async def login_user(email: str, password: str):
    """Verify user exists - client handles Firebase Auth"""
    try:
        result = await auth_service.login_user(email, password)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/auth/verify-token")
async def verify_token(user=Depends(get_current_user)):
    """Verify if token is valid"""
    return {"valid": True, "user": user}

@app.get("/auth/me", response_model=UserResponse)
async def get_me(user=Depends(get_current_user)):
    """Get current user info"""
    return user

# ============================================================================
# PROFILE ROUTES
# ============================================================================

@app.get("/profile/me", response_model=UserResponse)
async def get_my_profile(user=Depends(get_current_user)):
    """Get current user's profile information"""
    return UserResponse(**user)

@app.put("/profile/me", response_model=UserResponse)
async def update_my_profile(
    profile_update: UserUpdate,
    user=Depends(get_current_user)
):
    """Update current user's profile"""
    try:
        updated_user = await profile_service.update_profile(
            user["uid"], 
            profile_update
        )
        return updated_user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@app.post("/profile/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    """Upload user avatar image"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    try:
        avatar_url = await profile_service.upload_avatar(
            user["uid"], 
            file
        )
        return {"avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}"
        )

@app.get("/profile/stats", response_model=ProfileStats)
async def get_profile_stats(user=Depends(get_current_user)):
    """Get user's activity statistics"""
    try:
        stats = await profile_service.get_user_stats(user["uid"])
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )

@app.get("/profile/notifications", response_model=NotificationSettings)
async def get_notification_settings(user=Depends(get_current_user)):
    """Get user's notification preferences"""
    try:
        settings = await profile_service.get_notification_settings(user["uid"])
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification settings: {str(e)}"
        )

@app.put("/profile/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    settings: NotificationSettings,
    user=Depends(get_current_user)
):
    """Update user's notification preferences"""
    try:
        updated_settings = await profile_service.update_notification_settings(
            user["uid"], 
            settings
        )
        return updated_settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@app.get("/profile/preferences", response_model=UserPreferences)
async def get_user_preferences(user=Depends(get_current_user)):
    """Get user's app preferences"""
    try:
        preferences = await profile_service.get_user_preferences(user["uid"])
        return preferences
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user preferences: {str(e)}"
        )

@app.put("/profile/preferences", response_model=UserPreferences)
async def update_user_preferences(
    preferences: UserPreferences,
    user=Depends(get_current_user)
):
    """Update user's app preferences"""
    try:
        updated_preferences = await profile_service.update_user_preferences(
            user["uid"], 
            preferences
        )
        return updated_preferences
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@app.delete("/profile/account")
async def delete_account(user=Depends(get_current_user)):
    """Delete user account (soft delete)"""
    try:
        await profile_service.delete_account(user["uid"])
        return {"message": "Account scheduled for deletion"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )

# ============================================================================
# GOOGLE OAUTH ROUTES
# ============================================================================

@app.get("/auth/google/connect")
async def connect_google_account(user=Depends(get_current_user)):
    """Get Google OAuth URL for connecting account"""
    try:
        auth_url = google_service.get_authorization_url(user["uid"])
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/google/callback")
async def google_oauth_callback(code: str, state: str):
    """Handle Google OAuth callback"""
    try:
        result = await google_service.handle_oauth_callback(code, state)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/google/disconnect")
async def disconnect_google_account(user=Depends(get_current_user)):
    """Disconnect Google account"""
    try:
        success = await google_service.disconnect_google_account(user["uid"])
        return {"success": success, "message": "Google account disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/google/status")
async def get_google_connection_status(user=Depends(get_current_user)):
    """Check Google connection status"""
    try:
        status = await google_service.check_google_connection_status(user["uid"])
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CHAT/AI ROUTES
# ============================================================================

@app.post("/chat/message", response_model=ChatResponse)
async def send_chat_message(
    message: ChatMessage,
    user=Depends(get_current_user)
):
    """Send message to Betty AI and get response - ENHANCED WITH INDEXING"""
    try:
        user_id = user["uid"]
        
        # Get or create conversation - using indexed approach
        if not message.conversation_id:
            conversation_id = await ai_service.create_conversation_session_indexed(user_id)
            message.conversation_id = conversation_id
        else:
            conversation_id = message.conversation_id
        
        # Process message with AI (existing logic)
        response = await ai_service.process_message(message, user_id)
        
        # Enhanced: Save messages and update indexes automatically
        await save_chat_messages_with_indexes(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message.content,
            ai_response=response.content,
            tokens_used=response.tokens_used
        )
        
        # If AI created a document, save it with indexing
        if response.document_created:
            doc_data = DocumentCreate(
                title=response.document_title,
                content=response.document_content,
                document_type="ai_generated"
            )
            # Use indexed document creation
            doc_id = await firebase_service.create_document_with_index(
                collection="documents",
                data=doc_data.dict(),
                user_id=user_id,
                index_type="document_ids"
            )
            response.document_id = doc_id
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/history")
async def get_chat_history(
    limit: int = 50,
    user=Depends(get_current_user)
):
    """Get user's chat history - ENHANCED PERFORMANCE"""
    try:
        # Same API, but now using optimized queries
        history = await ai_service.get_chat_history_optimized(user["uid"], limit)
        return {"messages": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversations")
async def get_user_conversations(
    user=Depends(get_current_user)
):
    """Get user's conversation list - MUCH FASTER WITH INDEXING"""
    try:
        # Same API signature, but now using indexed approach for speed
        conversations = await ai_service.get_user_conversations_indexed(user["uid"])
        return {"conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DOCUMENT ROUTES
# ============================================================================

@app.post("/documents", response_model=DocumentResponse)
async def create_document(
    document: DocumentCreate,
    user=Depends(get_current_user)
):
    """Create a new document - WITH AUTOMATIC INDEXING"""
    try:
        # Create document with automatic index update
        doc_id = await firebase_service.create_document_with_index(
            collection="documents",
            data=document.dict(),
            user_id=user["uid"],
            index_type="document_ids"
        )
        
        # Return the document in expected format
        created_doc = await firebase_service.get_document("documents", doc_id)
        return DocumentResponse(**created_doc)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents", response_model=list[DocumentResponse])
async def get_documents(user=Depends(get_current_user)):
    """Get user documents - MUCH FASTER WITH INDEXING"""
    try:
        # Same API, but now uses user's document index for instant retrieval
        documents = await firebase_service.get_user_items_by_index(
            uid=user["uid"],
            collection="documents",
            index_type="document_ids",
            limit=100  # reasonable limit for mobile
        )
        
        # Sort by updated_at (most recent first)
        documents.sort(key=lambda x: x.get("updated_at", datetime.min), reverse=True)
        
        return [DocumentResponse(**doc) for doc in documents]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user=Depends(get_current_user)
):
    """Get specific document - SAME PERFORMANCE (ALREADY FAST)"""
    try:
        document = await document_service.get_document(document_id, user["uid"])
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document: DocumentUpdate,
    user=Depends(get_current_user)
):
    """Update document - SAME API"""
    try:
        updated_document = await document_service.update_document(
            document_id, document, user["uid"]
        )
        return updated_document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user=Depends(get_current_user)
):
    """Delete document - WITH AUTOMATIC INDEX CLEANUP"""
    try:
        # Enhanced: Remove from document collection AND user index
        success = await firebase_service.delete_document_with_index(
            collection="documents",
            doc_id=document_id,
            user_id=user["uid"],
            index_type="document_ids"
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
            
        return {"message": "Document deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/export-google")
async def export_document_to_google(
    document_id: str,
    user=Depends(get_current_user)
):
    """Export document to Google Docs"""
    try:
        document = await document_service.get_document(document_id, user["uid"])
        result = await google_service.create_google_doc(
            user["uid"], document.title, document.content
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PLANNER ROUTES
# ============================================================================

# Tasks
@app.post("/planner/tasks", response_model=TaskResponse)
async def create_task(
    task: TaskCreate,
    user=Depends(get_current_user)
):
    """Create a new task"""
    try:
        new_task = await planner_service.create_task(task, user["uid"])
        return new_task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/planner/tasks", response_model=list[TaskResponse])
async def get_tasks(user=Depends(get_current_user)):
    """Get user tasks"""
    try:
        tasks = await planner_service.get_tasks(user["uid"])
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/planner/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_update: TaskUpdate,
    user=Depends(get_current_user)
):
    """Update task"""
    try:
        updated_task = await planner_service.update_task(task_id, task_update, user["uid"])
        return updated_task
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/planner/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user=Depends(get_current_user)
):
    """Delete task"""
    try:
        await planner_service.delete_task(task_id, user["uid"])
        return {"message": "Task deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Notes
@app.post("/planner/notes", response_model=NoteResponse)
async def create_note(
    note: NoteCreate,
    user=Depends(get_current_user)
):
    """Create a new note"""
    try:
        new_note = await planner_service.create_note(note, user["uid"])
        return new_note
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/planner/notes", response_model=list[NoteResponse])
async def get_notes(user=Depends(get_current_user)):
    """Get user notes"""
    try:
        notes = await planner_service.get_notes(user["uid"])
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Calendar integration
@app.get("/planner/calendar/events")
async def get_calendar_events(
    start_date: str,
    end_date: str,
    user=Depends(get_current_user)
):
    """Get calendar events (Google Calendar integration)"""
    try:
        events = await google_service.get_calendar_events(user["uid"], start_date, end_date)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/planner/calendar/events")
async def create_calendar_event(
    event_data: dict,
    user=Depends(get_current_user)
):
    """Create calendar event in Google Calendar"""
    try:
        result = await google_service.create_calendar_event(user["uid"], event_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/planner/notes/{note_id}/export-google")
async def export_note_to_google_keep(
    note_id: str,
    user=Depends(get_current_user)
):
    """Export note to Google Keep"""
    try:
        note = await planner_service.get_note(note_id, user["uid"])
        result = await google_service.create_keep_note(
            user["uid"], note.title, note.content
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversations")
async def get_user_conversations(
    user=Depends(get_current_user)
):
    """Get user's conversation list with metadata"""
    try:
        # Get conversations grouped by session/date
        conversations = await ai_service.get_user_conversations(user["uid"])
        return {"conversations": conversations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/conversation/new")
async def create_new_conversation(
    user=Depends(get_current_user)
):
    """Create a new conversation session - WITH INDEX UPDATE"""
    try:
        # Use indexed conversation creation
        conversation_id = await ai_service.create_conversation_session_indexed(user["uid"])
        return {"conversation_id": conversation_id, "message": "New conversation created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversation/{conversation_id}")
async def get_conversation_messages(
    conversation_id: str,
    user=Depends(get_current_user)
):
    """Get messages for a specific conversation - OPTIMIZED"""
    try:
        # Same API, optimized performance
        messages = await ai_service.get_conversation_messages_optimized(user["uid"], conversation_id)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user=Depends(get_current_user)
):
    """Delete a specific conversation - WITH INDEX CLEANUP"""
    try:
        # Same API, but now properly maintains indexes
        success = await ai_service.delete_conversation_indexed(user["uid"], conversation_id)
        return {"success": success, "message": "Conversation deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/stats/chat")
async def get_chat_stats(
    user=Depends(get_current_user)
):
    """Get user's chat statistics - LIGHTNING FAST O(1) LOOKUP!"""
    try:
        # Same API, but now uses cached stats instead of expensive queries
        stats = await ai_service.get_user_chat_stats_indexed(user["uid"])
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/debug/firebase-data")
async def debug_firebase_data(
    user=Depends(get_current_user)
):
    """Debug endpoint to check what's actually in Firebase"""
    try:
        user_id = user["uid"]
        
        # Check conversations collection
        conversations = await firebase_service.query_documents("conversations")
        user_conversations = [conv for conv in conversations if conv.get("user_id") == user_id]
        
        # Check chat_history collection  
        chat_history = await firebase_service.query_documents("chat_history")
        user_messages = [msg for msg in chat_history if msg.get("user_id") == user_id]
        
        # Check if collections exist at all
        all_conversations = await firebase_service.query_documents("conversations", limit=5)
        all_messages = await firebase_service.query_documents("chat_history", limit=5)
        
        debug_info = {
            "user_id": user_id,
            "collections_overview": {
                "total_conversations_in_db": len(conversations),
                "total_messages_in_db": len(chat_history),
                "sample_conversations": all_conversations[:2],  # First 2 for inspection
                "sample_messages": all_messages[:2]  # First 2 for inspection
            },
            "user_data": {
                "user_conversations_count": len(user_conversations),
                "user_messages_count": len(user_messages),
                "user_conversations": user_conversations[:3],  # First 3 for inspection
                "user_messages": user_messages[:3]  # First 3 for inspection
            }
        }
        
        return debug_info
        
    except Exception as e:
        return {"error": str(e), "message": "Debug failed"}

@app.get("/debug/test-chat-stats")
async def debug_test_chat_stats(
    user=Depends(get_current_user)
):
    """Test the chat stats specifically"""
    try:
        user_id = user["uid"]
        
        # Test each part of the stats calculation
        conversations_raw = await firebase_service.query_documents(
            "conversations",
            filters=[("user_id", "==", user_id)]
        )
        
        messages_raw = await firebase_service.query_documents(
            "chat_history", 
            filters=[("user_id", "==", user_id)]
        )
        
        # Test today's messages
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_messages_raw = await firebase_service.query_documents(
            "chat_history",
            filters=[
                ("user_id", "==", user_id),
                ("timestamp", ">=", today_start)
            ]
        )
        
        return {
            "user_id": user_id,
            "raw_counts": {
                "conversations_found": len(conversations_raw),
                "messages_found": len(messages_raw), 
                "today_messages_found": len(today_messages_raw)
            },
            "sample_data": {
                "sample_conversation": conversations_raw[0] if conversations_raw else None,
                "sample_message": messages_raw[0] if messages_raw else None
            },
            "query_filters_used": {
                "user_filter": ("user_id", "==", user_id),
                "today_start": today_start.isoformat()
            }
        }
        
    except Exception as e:
        return {"error": str(e), "message": "Chat stats debug failed"}

@app.get("/debug/collections-structure")
async def debug_collections_structure():
    """Check the overall structure of your Firebase collections"""
    try:
        # Get sample documents from each collection to see structure
        conversations_sample = await firebase_service.query_documents("conversations", limit=3)
        messages_sample = await firebase_service.query_documents("chat_history", limit=3)
        
        return {
            "conversations_collection": {
                "document_count": len(conversations_sample),
                "sample_documents": conversations_sample,
                "sample_fields": list(conversations_sample[0].keys()) if conversations_sample else []
            },
            "chat_history_collection": {
                "document_count": len(messages_sample),
                "sample_documents": messages_sample,
                "sample_fields": list(messages_sample[0].keys()) if messages_sample else []
            }
        }
        
    except Exception as e:
        return {"error": str(e), "message": "Structure debug failed"}

@app.post("/admin/migrate-all-users")
async def migrate_all_users_to_indexed(admin_user = Depends(get_admin_user)):
    """Migrate all existing users to indexed structure"""
    try:
        print("🚀 Starting migration of all users to indexed structure...")
        
        # Get all users from the users collection
        all_users = await firebase_service.query_documents("users")
        print(f"Found {len(all_users)} users to migrate")
        
        migrated_count = 0
        failed_count = 0
        skipped_count = 0
        migration_results = []
        
        for user_doc in all_users:
            user_id = user_doc.get("uid")
            if not user_id:
                print(f"⚠️ Skipping user with missing uid: {user_doc.get('id', 'unknown')}")
                skipped_count += 1
                continue
            
            try:
                print(f"🔄 Migrating user: {user_id}")
                
                # Check if user already has indexes
                existing_indexes = user_doc.get("indexes")
                if existing_indexes and len(existing_indexes.get("conversation_ids", [])) > 0:
                    print(f"✅ User {user_id} already migrated, skipping...")
                    skipped_count += 1
                    migration_results.append({
                        "user_id": user_id,
                        "status": "skipped",
                        "reason": "already_migrated"
                    })
                    continue
                
                # Perform the migration
                success = await migrate_single_user(user_id)
                
                if success:
                    migrated_count += 1
                    migration_results.append({
                        "user_id": user_id,
                        "status": "success"
                    })
                    print(f"✅ Successfully migrated user {user_id}")
                else:
                    failed_count += 1
                    migration_results.append({
                        "user_id": user_id,
                        "status": "failed",
                        "reason": "migration_function_failed"
                    })
                    print(f"❌ Failed to migrate user {user_id}")
                
            except Exception as e:
                print(f"❌ Error migrating user {user_id}: {e}")
                failed_count += 1
                migration_results.append({
                    "user_id": user_id,
                    "status": "failed",
                    "reason": str(e)
                })
            
            # Small delay to avoid overwhelming Firebase
            await asyncio.sleep(0.1)
        
        print(f"🏁 Migration completed!")
        print(f"   Migrated: {migrated_count}")
        print(f"   Failed: {failed_count}")
        print(f"   Skipped: {skipped_count}")
        
        return {
            "message": "Migration completed",
            "summary": {
                "total_users": len(all_users),
                "migrated_users": migrated_count,
                "failed_migrations": failed_count,
                "skipped_users": skipped_count
            },
            "results": migration_results[:10],  # First 10 for brevity
            "full_results_available": len(migration_results) > 10
        }
        
    except Exception as e:
        print(f"❌ Migration process failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@app.post("/admin/migrate-user/{user_id}")
async def migrate_single_user_endpoint(
    user_id: str,
    admin_user = Depends(get_admin_user)
):
    """Migrate a single user to indexed structure"""
    try:
        success = await migrate_single_user(user_id)
        
        if success:
            return {
                "message": f"Successfully migrated user {user_id} to indexed structure",
                "user_id": user_id,
                "status": "success"
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Migration failed for user {user_id}"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/dashboard")
async def get_user_dashboard(user=Depends(get_current_user)):
    """Get comprehensive user dashboard data using indexed approach - LIGHTNING FAST!"""
    try:
        user_id = user["uid"]
        
        # Get user profile with cached stats (O(1) operation)
        user_profile = await firebase_service.get_user_profile(user_id)
        
        if not user_profile:
            # Initialize user if they don't exist
            await firebase_service.initialize_user_indexes(user_id)
            user_profile = await firebase_service.get_user_profile(user_id)
        
        # Extract cached stats (super fast!)
        stats = user_profile.get("stats", {})
        indexes = user_profile.get("indexes", {})
        
        # Get recent conversations using indexed approach (limited to 5 for dashboard)
        recent_conversations = []
        conversation_ids = indexes.get("conversation_ids", [])
        
        if conversation_ids:
            # Get the 5 most recent conversations
            recent_conv_ids = conversation_ids[:5] if len(conversation_ids) <= 5 else conversation_ids[-5:]
            
            for conv_id in reversed(recent_conv_ids):  # Most recent first
                try:
                    conv = await firebase_service.get_document("conversations", conv_id)
                    if conv:
                        # Add last message preview
                        recent_messages = await firebase_service.query_documents(
                            "chat_history",
                            filters=[
                                ("user_id", "==", user_id),
                                ("conversation_id", "==", conv.get("conversation_id"))
                            ],
                            order_by="-timestamp",
                            limit=1
                        )
                        
                        if recent_messages:
                            last_msg = recent_messages[0]["content"]
                            conv["last_message"] = last_msg[:100] + "..." if len(last_msg) > 100 else last_msg
                            conv["last_message_at"] = recent_messages[0]["timestamp"]
                        else:
                            conv["last_message"] = "Start chatting..."
                            conv["last_message_at"] = conv.get("created_at")
                        
                        recent_conversations.append(conv)
                except Exception as e:
                    print(f"Error loading conversation {conv_id}: {e}")
                    continue
        
        # Get recent documents using indexed approach (limited to 5 for dashboard)
        recent_documents = []
        document_ids = indexes.get("document_ids", [])
        
        if document_ids:
            # Get the 5 most recent documents
            recent_doc_ids = document_ids[:5] if len(document_ids) <= 5 else document_ids[-5:]
            
            for doc_id in reversed(recent_doc_ids):  # Most recent first
                try:
                    doc = await firebase_service.get_document("documents", doc_id)
                    if doc:
                        recent_documents.append(doc)
                except Exception as e:
                    print(f"Error loading document {doc_id}: {e}")
                    continue
        
        # Calculate today's messages dynamically (this is the only expensive operation)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = 0
        
        try:
            today_messages = await firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("timestamp", ">=", today_start)
                ]
            )
            messages_today = len(today_messages)
            
            # Update cached value for next time
            await firebase_service.update_user_stats(user_id, {
                "messages_today": messages_today,
                "last_activity": datetime.utcnow()
            })
            
        except Exception as e:
            print(f"Could not calculate today's messages: {e}")
            messages_today = stats.get("messages_today", 0)
        
        # Determine user level based on activity
        total_messages = stats.get("total_messages", 0)
        user_level = "starter"
        if total_messages > 500:
            user_level = "expert"
        elif total_messages > 100:
            user_level = "pro"
        
        # Build comprehensive dashboard response
        dashboard_data = {
            "user_info": {
                "uid": user_id,
                "first_name": user_profile.get("first_name"),
                "last_name": user_profile.get("last_name"),
                "email": user_profile.get("email"),
                "avatar_url": user_profile.get("avatar_url"),
                "user_level": user_level
            },
            "stats": {
                "total_conversations": stats.get("total_conversations", 0),
                "total_documents": stats.get("total_documents", 0),
                "total_messages": total_messages,
                "total_tasks": stats.get("total_tasks", 0),
                "messages_today": messages_today,
                "last_activity": stats.get("last_activity"),
                "last_message_at": stats.get("last_message_at"),
                
                # Calculated metrics
                "avg_messages_per_conversation": (
                    total_messages / stats.get("total_conversations", 1) if stats.get("total_conversations", 0) > 0 else 0
                ),
                "estimated_hours_saved": round(total_messages * 0.1, 1)  # 6 minutes per 10 messages
            },
            "recent_activity": {
                "conversations": recent_conversations,
                "documents": recent_documents
            },
            "quick_stats": {
                "conversations_this_week": 0,  # Could be calculated if needed
                "documents_this_week": 0,      # Could be calculated if needed
                "productivity_score": min(100, total_messages),  # Simple score out of 100
            },
            "indexes_info": {  # For debugging/admin purposes
                "conversation_count": len(indexes.get("conversation_ids", [])),
                "document_count": len(indexes.get("document_ids", [])),
                "task_count": len(indexes.get("task_ids", [])),
                "last_index_update": user_profile.get("updated_at")
            }
        }
        
        return dashboard_data
        
    except Exception as e:
        print(f"Error getting user dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {str(e)}")

# Alternative simpler version if you want just the stats
@app.get("/user/stats")
async def get_user_stats_simple(user=Depends(get_current_user)):
    """Get user statistics in a simple format"""
    try:
        user_id = user["uid"]
        
        # Get cached stats from user profile
        user_profile = await firebase_service.get_user_profile(user_id)
        
        if not user_profile:
            return {
                "total_conversations": 0,
                "total_documents": 0,
                "total_messages": 0,
                "total_tasks": 0,
                "messages_today": 0
            }
        
        stats = user_profile.get("stats", {})
        
        # Update today's messages
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            today_messages = await firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("timestamp", ">=", today_start)
                ]
            )
            messages_today = len(today_messages)
        except:
            messages_today = stats.get("messages_today", 0)
        
        return {
            "total_conversations": stats.get("total_conversations", 0),
            "total_documents": stats.get("total_documents", 0),  
            "total_messages": stats.get("total_messages", 0),
            "total_tasks": stats.get("total_tasks", 0),
            "messages_today": messages_today,
            "last_activity": stats.get("last_activity"),
            "last_message_at": stats.get("last_message_at")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Quick endpoint to just get user profile with stats (for React Native)
@app.get("/user/profile-with-stats")
async def get_user_profile_with_stats(user=Depends(get_current_user)):
    """Get user profile with embedded stats - optimized for mobile"""
    try:
        user_id = user["uid"]
        user_profile = await firebase_service.get_user_profile(user_id)
        
        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        # Calculate today's messages quickly
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = 0
        
        try:
            today_messages = await firebase_service.query_documents(
                "chat_history",
                filters=[
                    ("user_id", "==", user_id),
                    ("timestamp", ">=", today_start)
                ]
            )
            messages_today = len(today_messages)
        except:
            pass
        
        stats = user_profile.get("stats", {})
        total_messages = stats.get("total_messages", 0)
        
        return {
            # User profile info
            "uid": user_id,
            "first_name": user_profile.get("first_name"),
            "last_name": user_profile.get("last_name"),
            "email": user_profile.get("email"),
            "phone": user_profile.get("phone"),
            "avatar_url": user_profile.get("avatar_url"),
            "bio": user_profile.get("bio"),
            "location": user_profile.get("location"),
            
            # Embedded stats for ProfileScreen
            "activity_stats": {
                "tasks_completed": stats.get("total_tasks", 0),
                "documents_created": stats.get("total_documents", 0),
                "hours_saved": round(total_messages * 0.1, 1),
                "ai_chats": stats.get("total_conversations", 0),
                "total_messages": total_messages,
                "messages_today": messages_today,
                "last_chat_at": stats.get("last_message_at")
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )