from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
from typing import Optional
import os
import jwt
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
    """Send message to Betty AI and get response"""
    try:
        response = await ai_service.process_message(message, user["uid"])
        
        # If AI created a document, save it
        if response.document_created:
            doc_data = DocumentCreate(
                title=response.document_title,
                content=response.document_content,
                document_type="ai_generated"
            )
            await document_service.create_document(doc_data, user["uid"])
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/history")
async def get_chat_history(
    limit: int = 50,
    user=Depends(get_current_user)
):
    """Get user's chat history"""
    try:
        history = await ai_service.get_chat_history(user["uid"], limit)
        return {"messages": history}
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
    """Create a new document"""
    try:
        new_document = await document_service.create_document(document, user["uid"])
        return new_document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents", response_model=list[DocumentResponse])
async def get_documents(user=Depends(get_current_user)):
    """Get user documents"""
    try:
        documents = await document_service.get_documents(user["uid"])
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user=Depends(get_current_user)
):
    """Get specific document"""
    try:
        document = await document_service.get_document(document_id, user["uid"])
        return document
    except Exception as e:
        raise HTTPException(status_code=404, detail="Document not found")

@app.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document_update: DocumentUpdate,
    user=Depends(get_current_user)
):
    """Update document"""
    try:
        updated_document = await document_service.update_document(
            document_id, document_update, user["uid"]
        )
        return updated_document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user=Depends(get_current_user)
):
    """Delete document"""
    try:
        await document_service.delete_document(document_id, user["uid"])
        return {"message": "Document deleted successfully"}
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
    """Create a new conversation session"""
    try:
        conversation_id = await ai_service.create_conversation_session(user["uid"])
        return {"conversation_id": conversation_id, "message": "New conversation created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chat/conversation/{conversation_id}")
async def get_conversation_messages(
    conversation_id: str,
    user=Depends(get_current_user)
):
    """Get messages for a specific conversation"""
    try:
        messages = await ai_service.get_conversation_messages(user["uid"], conversation_id)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chat/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user=Depends(get_current_user)
):
    """Delete a specific conversation"""
    try:
        success = await ai_service.delete_conversation(user["uid"], conversation_id)
        return {"success": success, "message": "Conversation deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/stats/chat")
async def get_chat_stats(
    user=Depends(get_current_user)
):
    """Get user's chat statistics for profile screen"""
    try:
        stats = await ai_service.get_user_chat_stats(user["uid"])
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

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )