from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn
from typing import Optional

# Import our custom modules
from services.firebase_service import FirebaseService
from services.auth_service import AuthService
from services.document_service import DocumentService
from services.ai_service import AIService
from services.planner_service import PlannerService
from models.user_models import UserCreate, UserResponse
from models.document_models import DocumentCreate, DocumentResponse, DocumentUpdate
from models.chat_models import ChatMessage, ChatResponse
from models.planner_models import TaskCreate, TaskResponse, TaskUpdate, NoteCreate, NoteResponse

# Initialize services
firebase_service = FirebaseService()
auth_service = AuthService(firebase_service)
document_service = DocumentService(firebase_service)
ai_service = AIService()
planner_service = PlannerService(firebase_service)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Betty Backend starting up...")
    firebase_service.initialize()
    print("✅ Firebase initialized")
    yield
    # Shutdown
    print("👋 Betty Backend shutting down...")

app = FastAPI(
    title="Betty - Office Genius API",
    description="Backend API for Betty, your AI-powered office assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user"""
    try:
        user = await auth_service.verify_token(credentials.credentials)
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Betty Backend is running!"}

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
    """Login user and return custom token"""
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
        doc = await document_service.create_document(document, user["uid"])
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents", response_model=list[DocumentResponse])
async def get_user_documents(
    document_type: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Get all user documents"""
    try:
        docs = await document_service.get_user_documents(user["uid"], document_type)
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user=Depends(get_current_user)
):
    """Get specific document"""
    try:
        doc = await document_service.get_document(document_id, user["uid"])
        return doc
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
        doc = await document_service.update_document(document_id, document_update, user["uid"])
        return doc
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
async def export_to_google_docs(
    document_id: str,
    user=Depends(get_current_user)
):
    """Export document to Google Docs"""
    try:
        result = await document_service.export_to_google_docs(document_id, user["uid"])
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
async def get_tasks(
    completed: Optional[bool] = None,
    user=Depends(get_current_user)
):
    """Get user tasks"""
    try:
        tasks = await planner_service.get_tasks(user["uid"], completed)
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
        task = await planner_service.update_task(task_id, task_update, user["uid"])
        return task
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
        events = await planner_service.get_calendar_events(user["uid"], start_date, end_date)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ADMIN ROUTES (Optional)
# ============================================================================

@app.get("/admin/stats")
async def get_admin_stats(user=Depends(get_current_user)):
    """Get admin statistics - implement role checking"""
    # TODO: Add admin role checking
    try:
        stats = {
            "total_users": await firebase_service.get_collection_count("users"),
            "total_documents": await firebase_service.get_collection_count("documents"),
            "total_tasks": await firebase_service.get_collection_count("tasks"),
        }
        return stats
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