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
from fastapi import Query
from dotenv import load_dotenv
import json
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
from typing import List, Dict, Any
import logging
from pydantic import BaseModel
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from firebase_admin import firestore

# Load environment variables from .env file
load_dotenv()

# Configure logging for debug router
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("betty_debug")

# Create a file handler for debug logs
debug_handler = logging.FileHandler('debug_logs.txt')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)
logger.addHandler(debug_handler)

# Debug router models
class DebugLog(BaseModel):
    level: str
    message: str
    data: Optional[str] = None
    platform: str
    timestamp: str
    component: str

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
from models.document_models import DocumentCreate, DocumentResponse, DocumentUpdate, DocumentGenerationRequest, FormattedGoogleDocRequest
from models.chat_models import ChatMessage, ChatResponse, EnhancedChatResponse, EnhancedChatMessage
from models.planner_models import (
    TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskPriority,
    NoteCreate, NoteResponse, NoteUpdate, 
    CalendarEventCreate, CalendarEvent, EventType,  # <- Add this line
    MeetingRecording, RecordingCreate, RecordingUpdate, RecordingStatus,
    PlannerDashboard, PlannerStats, TaskFilter, QuickTaskCreate
)
from services.enhanced_planner_service import EnhancedPlannerService

#Import routes
from routes.planner_routes import router as planner_router
from routes.auth_routes import router as auth_router

# Initialize services
firebase_service = FirebaseService()
auth_service = AuthService(firebase_service)
google_service = GoogleService(firebase_service)
document_service = DocumentService(firebase_service, google_service)
ai_service = AIService(firebase_service)
planner_service = PlannerService(firebase_service)
profile_service = ProfileService(firebase_service, auth_service)
enhanced_planner_service = EnhancedPlannerService(firebase_service, google_service)

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

app.include_router(planner_router)
app.include_router(auth_router)
# Mount static files for serving uploaded images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS middleware
allowed_origins = [
    "http://localhost:3000",      # React web apps
    "http://localhost:8080",      # Alternative React port
    "http://localhost:8081",      # Expo web default port
    "http://127.0.0.1:3000",      # Alternative localhost
    "http://127.0.0.1:8080",      # Alternative localhost
    "http://127.0.0.1:8081",      # Alternative localhost
    "exp://localhost:8081",       # Expo specific
    "exp://127.0.0.1:8081",       # Expo specific
    "*"                           # Allow all origins (development only)
]
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
        print(f"🔍 Validating JWT token for protected endpoint...")
        
        # Verify JWT token using auth_service
        payload = auth_service.verify_jwt_token(token)
        uid = payload['uid']
        email = payload['email']
        
        print(f"✅ JWT token valid for UID: {uid}")
        
        # Try to get user profile, but don't fail if it doesn't exist
        user_profile = None
        try:
            if hasattr(auth_service.firebase_service, 'get_user_profile'):
                user_profile = await auth_service.firebase_service.get_user_profile(uid)
                if user_profile:
                    print(f"✅ User profile found and loaded")
                    return user_profile
            else:
                print(f"⚠️ get_user_profile method not available in FirebaseService")
        except Exception as e:
            print(f"⚠️ Could not get user profile: {e}")
        
        # If profile doesn't exist or can't be retrieved, create minimal user object from JWT
        print(f"🆕 Using minimal user data from JWT payload")
        minimal_user = {
            "uid": uid,
            "email": email,
            "first_name": "",
            "last_name": "",
            "location": "Johannesburg, South Africa",
            "timezone": "Africa/Johannesburg", 
            "phone": None,
            "bio": None,
            "avatar_url": None,
            "avatar_filename": None,
            "is_verified": False,
            "google_connected": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_login": datetime.now(timezone.utc),
            "preferences": None
        }
        
        print(f"✅ Returning minimal user data for authenticated request")
        return minimal_user
        
    except Exception as e:
        print(f"❌ JWT validation failed: {e}")
        print(f"❌ Error type: {type(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
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

# Debug router endpoints
from fastapi import APIRouter

debug_router = APIRouter(prefix="/debug", tags=["debug"])

class GoogleUserInfo(BaseModel):
    email: str
    name: str
    photo: Optional[str] = None
    id: str

class GoogleConnectNativeRequest(BaseModel):
    access_token: str
    id_token: Optional[str] = None
    user_info: GoogleUserInfo

class GoogleConnectResponse(BaseModel):
    success: bool
    message: str
    user_info: Optional[Dict[str, Any]] = None

@debug_router.post("/log")
async def receive_debug_log(
    log_data: DebugLog,
    user=Depends(get_current_user)  # Ensure user is authenticated
):
    """Receive debug logs from the mobile app"""
    try:
        # Format the log message
        log_message = f"[{log_data.platform}] [{log_data.component}] {log_data.message}"
        if log_data.data:
            log_message += f" | Data: {log_data.data}"
        
        # Log to console and file based on level
        if log_data.level == "error":
            logger.error(log_message)
        elif log_data.level == "info":
            logger.info(log_message)
        elif log_data.level == "debug":
            logger.debug(log_message)
        else:
            logger.info(log_message)
        
        # Also print to console for immediate visibility
        print(f"🐛 DEBUG [{log_data.timestamp}] [{user.get('email', 'unknown')}] {log_message}")
        
        return {"status": "logged", "timestamp": datetime.utcnow().isoformat()}
        
    except Exception as e:
        print(f"❌ Error logging debug message: {e}")
        return {"status": "error", "error": str(e)}

@debug_router.get("/logs")
async def get_recent_logs(
    lines: int = 50,
    user=Depends(get_current_user)  # Ensure user is authenticated
):
    """Get recent debug logs"""
    try:
        with open('debug_logs.txt', 'r') as f:
            logs = f.readlines()
            return {"logs": logs[-lines:]}
    except FileNotFoundError:
        return {"logs": [], "message": "No debug logs found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include the debug router in the app
app.include_router(debug_router)

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

@app.post("/auth/google/connect-native", response_model=GoogleConnectResponse)
async def connect_google_native(
    request: GoogleConnectNativeRequest,
    current_user = Depends(get_current_user)  # Your existing auth dependency
):
    """
    Connect a user's Google account using native mobile authentication.
    This endpoint receives tokens from React Native Google Sign-In.
    """
    try:
        logger.info(f"Processing Google connect request for user: {current_user.get('uid', 'unknown')}")
        logger.debug(f"Request data: access_token present={bool(request.access_token)}, id_token present={bool(request.id_token)}")
        
        # Validate required fields
        if not request.access_token:
            raise HTTPException(status_code=400, detail="access_token is required")
        
        if not request.user_info or not request.user_info.email:
            raise HTTPException(status_code=400, detail="user_info with email is required")

        # Try to verify the ID token if provided, but don't fail if it's expired
        # Since React Native tokens can be short-lived
        verified_claims = None
        token_verification_failed = False
        
        if request.id_token:
            try:
                # Replace with your Google Client ID
                GOOGLE_CLIENT_ID = "1092345143344-vd984vtn6cdo6tlid624r5aqhi0ov331.apps.googleusercontent.com"
                
                # Verify the ID token
                verified_claims = id_token.verify_oauth2_token(
                    request.id_token, 
                    google_requests.Request(), 
                    GOOGLE_CLIENT_ID
                )
                logger.info(f"ID token verified successfully for email: {verified_claims.get('email')}")
                
                # Ensure the email matches
                if verified_claims.get('email') != request.user_info.email:
                    logger.warning(f"Email mismatch: token={verified_claims.get('email')}, user_info={request.user_info.email}")
                    # Don't fail here, just log the mismatch
                    
            except ValueError as e:
                logger.warning(f"ID token verification failed: {str(e)}")
                token_verification_failed = True
                
                # Check if it's just an expired token (common with React Native)
                if "expired" in str(e).lower() or "Token expired" in str(e):
                    logger.info("Token expired - this is common with React Native Google Sign-In, continuing with access token validation")
                else:
                    logger.error(f"Non-expiry ID token error: {str(e)}")

        # If ID token verification failed for reasons other than expiry, 
        # we can still proceed but should validate the access token
        if token_verification_failed and not verified_claims:
            try:
                # Validate the access token by making a request to Google's userinfo endpoint
                import requests
                
                userinfo_response = requests.get(
                    'https://www.googleapis.com/oauth2/v2/userinfo',
                    headers={'Authorization': f'Bearer {request.access_token}'},
                    timeout=10
                )
                
                if userinfo_response.status_code == 200:
                    userinfo = userinfo_response.json()
                    logger.info(f"Access token validated successfully for email: {userinfo.get('email')}")
                    
                    # Verify email matches
                    if userinfo.get('email') != request.user_info.email:
                        logger.error(f"Email mismatch in access token validation: {userinfo.get('email')} != {request.user_info.email}")
                        raise HTTPException(
                            status_code=400, 
                            detail="Email mismatch between access token and user info"
                        )
                else:
                    logger.error(f"Access token validation failed: {userinfo_response.status_code}")
                    raise HTTPException(
                        status_code=400, 
                        detail="Invalid access token - unable to verify user identity"
                    )
                    
            except requests.RequestException as e:
                logger.error(f"Failed to validate access token: {str(e)}")
                raise HTTPException(
                    status_code=400, 
                    detail="Unable to validate Google tokens - please try again"
                )
        
        # Prepare user data for storage
        google_user_data = {
            "email": request.user_info.email,
            "name": request.user_info.name,
            "photo": request.user_info.photo,
            "google_id": request.user_info.id,
            "access_token": request.access_token,  # Store securely, consider encryption
            "verified": bool(verified_claims) and not token_verification_failed
        }

        # Update user in Firebase/database with Google connection
        try:
            user_uid = current_user.get('uid')
            if not user_uid:
                raise HTTPException(status_code=401, detail="Invalid user session")

            # Update user record in Firebase
            user_update_data = {
                'google_connected': True,
                'google_email': request.user_info.email,
                'google_name': request.user_info.name,
                'google_photo': request.user_info.photo,
                'google_id': request.user_info.id,
                'google_access_token': request.access_token,
                'google_tokens': {
                    'access_token': request.access_token,
                    'email': request.user_info.email,
                    'name': request.user_info.name,
                    'photo': request.user_info.photo,
                    'google_id': request.user_info.id,
                    'connected_at': firestore.SERVER_TIMESTAMP,
                    'verified': bool(verified_claims) and not token_verification_failed
                },
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            # If we have an ID token, store it too (even if expired, for reference)
            if request.id_token:
                user_update_data['google_id_token'] = request.id_token
                user_update_data['google_tokens']['id_token'] = request.id_token
            
            # Update in Firestore (adjust based on your Firebase service implementation)
            firebase_service.db.collection('users').document(user_uid).update(user_update_data)
            
            # Also store in separate google_tokens collection for easier access
            token_doc_data = {
                'user_id': user_uid,
                'access_token': request.access_token,
                'email': request.user_info.email,
                'name': request.user_info.name,
                'photo': request.user_info.photo,
                'google_id': request.user_info.id,
                'verified': bool(verified_claims) and not token_verification_failed,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            if request.id_token:
                token_doc_data['id_token'] = request.id_token
                
            firebase_service.db.collection('google_tokens').document(user_uid).set(token_doc_data)
            
            logger.info(f"Successfully connected Google account for user {user_uid}")

            return GoogleConnectResponse(
                success=True,
                message="Google account connected successfully",
                user_info={
                    "email": request.user_info.email,
                    "name": request.user_info.name,
                    "photo": request.user_info.photo,
                    "google_connected": True,
                    "verified": bool(verified_claims) and not token_verification_failed
                }
            )

        except Exception as db_error:
            logger.error(f"Database update failed: {str(db_error)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to update user record: {str(db_error)}"
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Google connect: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during Google account connection"
        )

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
async def get_google_oauth_url(user=Depends(get_current_user)):
    """
    Get Google OAuth URL for web-based authentication
    """
    try:
        import urllib.parse
        from urllib.parse import urlencode
        
        # Google OAuth 2.0 parameters
        oauth_params = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI', f"{request.base_url}auth/google/callback"),
            'scope': ' '.join([
                'openid',
                'profile',
                'email',
                'https://www.googleapis.com/auth/drive.file',
                'https://www.googleapis.com/auth/documents',
                'https://www.googleapis.com/auth/calendar'
            ]),
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': user.get('uid')  # Use uid as state for security
        }
        
        oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(oauth_params)}"
        
        return {
            "authorization_url": oauth_url,
            "state": user.get('uid')
        }
        
    except Exception as e:
        logger.error(f"Error generating OAuth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate OAuth URL: {str(e)}"
        )

@app.get("/auth/google/callback")
async def google_oauth_callback(code: str = None, state: str = None, error: str = None):
    """
    Handle Google OAuth callback
    """
    try:
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth error: {error}"
            )
        
        if not code or not state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing authorization code or state"
            )
        
        # Exchange authorization code for tokens
        import requests
        
        token_data = {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI')
        }
        
        token_response = requests.post(
            'https://oauth2.googleapis.com/token',
            data=token_data
        )
        
        if not token_response.ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange authorization code"
            )
        
        tokens = token_response.json()
        access_token = tokens.get('access_token')
        
        # Get user info from Google
        user_info_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if user_info_response.ok:
            user_info = user_info_response.json()
        else:
            user_info = {}
        
        # Store tokens for the user (state contains uid)
        uid = state
        user_ref = firebase_service.get_user_document_ref(uid)
        
        update_data = {
            'google_access_token': access_token,
            'google_refresh_token': tokens.get('refresh_token'),
            'google_id_token': tokens.get('id_token'),
            'google_user_info': user_info,
            'google_connected': True,
            'google_connected_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        user_ref.update(update_data)
        
        # Redirect to app with success message
        return {
            "success": True,
            "message": "Google account connected successfully!",
            "redirect_url": "bettyapp://google-auth-success"  # Deep link to your app
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {str(e)}"
        )


@app.post("/auth/google/disconnect")
async def disconnect_google(user=Depends(get_current_user)):
    """
    Disconnect user's Google account
    """
    try:
        uid = user.get('uid')
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )
        
        # Clear Google tokens from Firestore
        user_ref = firebase_service.get_user_document_ref(uid)
        
        update_data = {
            'google_access_token': None,
            'google_id_token': None,
            'google_user_info': None,
            'google_connected': False,
            'google_connected_at': None,
            'updated_at': datetime.now(timezone.utc)
        }
        
        user_ref.update(update_data)
        
        logger.info(f"Google account disconnected for user {uid}")
        return {
            "success": True,
            "message": "Google account disconnected successfully"
        }
        
    except Exception as e:
        logger.error(f"Error disconnecting Google: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect Google account: {str(e)}"
        )

@app.get("/auth/google/status")
async def get_google_status(user=Depends(get_current_user)):
    """
    Check if user has Google account connected
    """
    try:
        uid = user.get('uid')
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )
        
        # Get user profile from Firestore
        user_profile = await firebase_service.get_user_profile(uid)
        
        if not user_profile:
            return {"connected": False, "message": "User profile not found"}
        
        # Check if user has Google tokens stored
        has_google_access = (
            user_profile.get('google_access_token') and 
            user_profile.get('google_access_token').strip() != ""
        )
        
        response_data = {
            "connected": has_google_access,
            "user_id": uid,
        }
        
        if has_google_access and user_profile.get('google_user_info'):
            response_data["user_info"] = user_profile.get('google_user_info')
        
        logger.info(f"Google status check for user {uid}: {has_google_access}")
        return response_data
        
    except Exception as e:
        logger.error(f"Error checking Google status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check Google status: {str(e)}"
        )

@app.post("/auth/google/token")
async def store_google_tokens(
    request: dict,
    user=Depends(get_current_user)
):
    """
    Store Google tokens after successful authentication
    """
    try:
        uid = user.get('uid')
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )
        
        access_token = request.get('access_token')
        id_token = request.get('id_token')
        user_info = request.get('user_info')
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access token is required"
            )
        
        # Update user profile in Firestore with Google tokens
        user_ref = firebase_service.get_user_document_ref(uid)
        
        update_data = {
            'google_access_token': access_token,
            'google_connected': True,
            'google_connected_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        if id_token:
            update_data['google_id_token'] = id_token
        
        if user_info:
            update_data['google_user_info'] = user_info
        
        # Update the user document
        user_ref.update(update_data)
        
        logger.info(f"Google tokens stored successfully for user {uid}")
        return {
            "success": True,
            "message": "Google account connected successfully",
            "user_id": uid
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing Google tokens: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store Google tokens: {str(e)}"
        )


# ============================================================================
# GOOGLE DRIVE/DOCS ROUTES
# ============================================================================

@app.post("/documents/export/google-docs")
async def export_to_google_docs(
    request: dict,
    user=Depends(get_current_user)
):
    """
    Export document to Google Docs
    """
    try:
        uid = user.get('uid')
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )
        
        # Get user profile to check Google connection
        user_profile = await firebase_service.get_user_profile(uid)
        
        if not user_profile or not user_profile.get('google_access_token'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected. Please connect your Google account first."
            )
        
        access_token = user_profile.get('google_access_token')
        document_title = request.get('title', 'Untitled Document')
        document_content = request.get('content', '')
        document_format = request.get('format', 'html')
        
        # Create Google Doc using Google Docs API
        import requests
        import json
        
        # Step 1: Create empty document
        create_doc_url = 'https://docs.googleapis.com/v1/documents'
        create_doc_data = {
            'title': document_title
        }
        
        create_response = requests.post(
            create_doc_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            },
            json=create_doc_data
        )
        
        if not create_response.ok:
            error_data = create_response.json()
            if create_response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google authentication expired. Please reconnect your Google account."
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create Google Doc: {error_data.get('error', {}).get('message', 'Unknown error')}"
            )
        
        doc_data = create_response.json()
        document_id = doc_data['documentId']
        
        # Step 2: Insert content into document
        if document_content.strip():
            batch_update_url = f'https://docs.googleapis.com/v1/documents/{document_id}:batchUpdate'
            
            # Convert HTML to plain text if needed
            if document_format == 'html':
                from html import unescape
                import re
                # Simple HTML to text conversion
                content_text = re.sub('<[^<]+?>', '', document_content)
                content_text = unescape(content_text)
            else:
                content_text = document_content
            
            batch_update_data = {
                'requests': [
                    {
                        'insertText': {
                            'location': {'index': 1},
                            'text': content_text
                        }
                    }
                ]
            }
            
            update_response = requests.post(
                batch_update_url,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                },
                json=batch_update_data
            )
            
            if not update_response.ok:
                logger.warning(f"Failed to update document content: {update_response.text}")
                # Don't fail the export if content update fails
        
        # Generate document URL
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
        
        # Store document info in user's Firestore subcollection
        try:
            documents_ref = firebase_service.get_user_collection_ref(uid, 'exported_documents')
            doc_ref = documents_ref.document(document_id)
            
            export_data = {
                'document_id': document_id,
                'title': document_title,
                'google_doc_url': doc_url,
                'exported_at': datetime.now(timezone.utc),
                'content_length': len(document_content),
                'format': document_format
            }
            
            doc_ref.set(export_data)
            logger.info(f"Document export record saved for user {uid}")
            
        except Exception as e:
            logger.warning(f"Failed to save export record: {e}")
            # Don't fail the export if record saving fails
        
        return {
            "success": True,
            "google_doc_id": document_id,
            "google_doc_url": doc_url,
            "message": f"Document '{document_title}' exported to Google Docs successfully!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export document: {str(e)}"
        )

@app.get("/documents/exports")
async def get_user_exports(user=Depends(get_current_user)):
    """
    Get user's exported documents history
    """
    try:
        uid = user.get('uid')
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )
        
        # Get user's exported documents from Firestore
        documents_ref = firebase_service.get_user_collection_ref(uid, 'exported_documents')
        docs = documents_ref.order_by('exported_at', direction='DESCENDING').limit(50).stream()
        
        exports = []
        for doc in docs:
            export_data = doc.to_dict()
            export_data['id'] = doc.id
            exports.append(export_data)
        
        return {
            "exports": exports,
            "total": len(exports)
        }
        
    except Exception as e:
        logger.error(f"Error getting user exports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get exports: {str(e)}"
        )

@app.post("/auth/google/store-tokens")
async def store_google_tokens(
    request: dict,
    user=Depends(get_current_user)
):
    """Store Google tokens from native sign-in"""
    try:
        access_token = request.get('access_token')
        id_token = request.get('id_token') 
        user_info = request.get('user_info')
        
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="Access token is required"
            )
        
        # Use your existing GoogleService to store the tokens
        result = await google_service.store_user_tokens(
            user["uid"], 
            access_token, 
            id_token, 
            user_info
        )
        
        return {
            "success": True,
            "message": "Google tokens stored successfully",
            "user_info": user_info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/google/create-doc")
async def create_google_doc(
    request: dict,
    user=Depends(get_current_user)
):
    """Create a Google Doc with the provided content"""
    try:
        title = request.get("title", "Untitled Document")
        content = request.get("content", "")
        
        result = await google_service.create_google_doc(
            user["uid"], 
            title, 
            content
        )
        
        return {
            "success": True,
            "document_id": result["document_id"],
            "document_url": result["document_url"],
            "title": title,
            "message": "Document created successfully in Google Drive"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail="Google account not connected. Please connect your Google account first."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/google/drive/files")
async def list_drive_files(user=Depends(get_current_user)):
    """List user's Google Drive files"""
    try:
        files = await google_service.list_user_drive_files(user["uid"])
        return {"files": files}
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail="Google account not connected"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/google/calendar/events")
async def get_calendar_events(
    start_date: str,
    end_date: str,
    user=Depends(get_current_user)
):
    """Get user's calendar events"""
    try:
        events = await google_service.get_calendar_events(
            user["uid"], 
            start_date, 
            end_date
        )
        return {"events": events}
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail="Google account not connected"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# CHAT/AI ROUTES
# ============================================================================

# main.py - Fixed chat message endpoint

@app.post("/chat/message")
async def send_chat_message(
    message: ChatMessage,
    conversation_id: Optional[str] = Query(None, description="Optional conversation ID"),
    user=Depends(get_current_user)
):
    """Send message to Betty AI and get response - NETWORK ERROR FIX"""
    try:
        user_id = user["uid"]
        
        print(f"📥 Received message: '{message.content[:50]}...'")
        print(f"📥 Conversation ID from query: {conversation_id}")
        print(f"📥 Conversation ID from message: {getattr(message, 'conversation_id', None)}")
        
        # Get or create conversation - handle both query param and message body
        final_conversation_id = None
        
        if conversation_id:
            # Use conversation_id from query parameter (preferred)
            final_conversation_id = conversation_id
            print(f"✅ Using conversation ID from query: {final_conversation_id}")
        elif hasattr(message, 'conversation_id') and message.conversation_id:
            # Use conversation_id from message body
            final_conversation_id = message.conversation_id
            print(f"✅ Using conversation ID from message body: {final_conversation_id}")
        else:
            # Create new conversation
            final_conversation_id = await ai_service.create_conversation_session_indexed(user_id)
            print(f"✅ Created new conversation: {final_conversation_id}")
        
        # Process message with AI - pass conversation_id explicitly
        print(f"🔄 Processing message with AI...")
        response = await ai_service.process_message(message, user_id, final_conversation_id)
        
        # Enhanced: Save messages and update indexes automatically
        print(f"💾 Saving chat messages...")
        await firebase_service.save_chat_messages_with_indexes(
            user_id=user_id,
            conversation_id=final_conversation_id,
            user_message=message.content,
            ai_response=response.content,
        )
        
        # If AI created a document, save it with indexing
        if response.document_created:
            print(f"📄 Creating document: {response.document_title}")
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
        
        # Add conversation_id to response for frontend
        response.conversation_id = final_conversation_id
        
        print(f"✅ Message processed successfully")
        return response
        
    except Exception as e:
        print(f"❌ Chat message error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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

@app.get("/auth/google/mobile-redirect")
async def google_mobile_redirect(code: str = None, state: str = None, error: str = None):
    """Handle Google OAuth mobile redirect from Serveo tunnel"""
    try:
        if error:
            # Handle OAuth error
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Error</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
            </head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>Authentication Failed</h1>
                <p>Error: {error}</p>
                <p>Please close this window and try again.</p>
                <script>
                    // Try to close the window after 3 seconds
                    setTimeout(() => {{
                        window.close();
                    }}, 3000);
                </script>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=400)
        
        if not code:
            # No code provided
            error_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authentication Error</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
            </head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1>Authentication Error</h1>
                <p>No authorization code received.</p>
                <p>Please close this window and try again.</p>
                <script>
                    setTimeout(() => {
                        window.close();
                    }, 3000);
                </script>
            </body>
            </html>
            """
            return HTMLResponse(content=error_html, status_code=400)
        
        # Success - show a page that can be closed
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>✅ Authentication Successful!</h1>
            <p>You can now close this window and return to the Betty app.</p>
            <p>Authorization code: {code[:10]}...</p>
            <script>
                // Try to communicate back to the app if possible
                if (window.ReactNativeWebView) {{
                    window.ReactNativeWebView.postMessage(JSON.stringify({{
                        type: 'GOOGLE_AUTH_SUCCESS',
                        code: '{code}'
                    }}));
                }}
                
                // Auto-close after 5 seconds
                setTimeout(() => {{
                    window.close();
                }}, 5000);
                
                // Also try to redirect back to the app
                setTimeout(() => {{
                    // This might work for some mobile browsers
                    window.location.href = 'com.tinashelorenzi.bettyofficegenius://auth/google/success?code={code}';
                }}, 1000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=success_html)
        
    except Exception as e:
        print(f"Error in mobile redirect: {e}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Server Error</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>Server Error</h1>
            <p>Something went wrong: {str(e)}</p>
            <p>Please close this window and try again.</p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

@app.post("/auth/google/mobile-callback")
async def google_mobile_oauth_callback(
    request: dict,
    user=Depends(get_current_user)
):
    """Handle Google OAuth callback from mobile app"""
    try:
        code = request.get("code")
        redirect_uri = request.get("redirect_uri")
        
        if not code:
            raise HTTPException(status_code=400, detail="Authorization code not provided")
        
        # Use the google_service to handle the OAuth callback
        # but modify it to use the mobile redirect_uri
        result = await google_service.handle_mobile_oauth_callback(code, user["uid"], redirect_uri)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@app.post("/google/drive/create-doc")
async def create_google_drive_doc(
    request: dict,
    user=Depends(get_current_user)
):
    """Create a Google Doc in Drive with the provided content"""
    try:
        title = request.get("title", "Untitled Document")
        content = request.get("content", "")
        
        result = await google_service.create_google_doc(
            user["uid"], 
            title, 
            content
        )
        
        return {
            "success": True,
            "document_id": result["document_id"],
            "document_url": result["document_url"],
            "title": title,
            "message": "Document created successfully in Google Drive"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail="Google account not connected. Please connect your Google account first."
        )
    except Exception as e:
        print(f"Error creating Google Doc: {e}")
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
    """Get user's conversation list - MUCH FASTER WITH INDEXING"""
    try:
        # Fixed: Use the corrected method signature
        conversations = await ai_service.get_user_conversations_indexed(user["uid"])
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

@app.post("/api/documents/generate")
async def generate_document(
    request: DocumentGenerationRequest,
    user=Depends(get_current_user)
):
    """Generate document using AI (server-side to protect API key)"""
    try:
        # Use your AI service (Gemini) with server-side API key
        prompt = f'Generate a comprehensive business document for a "{request.document_name}". The response should contain only the text of the document itself, starting with a title. Format the content using markdown for headers, bold text, and lists.'
        
        payload = {
            "contents": [{
                "role": "user", 
                "parts": [{"text": prompt}]
            }]
        }
        
        # Use environment variable for API key (secure)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")
        
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, 
                headers={'Content-Type': 'application/json'}, 
                json=payload,
                timeout=30.0
            )
        
        if not response.is_success:
            raise HTTPException(status_code=500, detail="AI generation failed")
        
        result = response.json()
        content = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Could not generate content.")
        
        return {
            "success": True,
            "content": content,
            "document_name": request.document_name,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        print(f"Document generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")

@app.post("/api/google/create-formatted-doc")
async def create_formatted_google_doc_from_markdown(
    request: FormattedGoogleDocRequest,
    user=Depends(get_current_user)
):
    """Create Google Doc with markdown-to-rich-text conversion"""
    try:
        # Validate Google connection
        user_profile = await firebase_service.get_user_profile(user["uid"])
        if not user_profile.get("google_connected"):
            raise HTTPException(
                status_code=400, 
                detail="Google account not connected. Please connect your Google account first."
            )
        
        # Convert markdown to Google Docs formatting requests
        if request.preserve_markdown:
            markdown_converter = MarkdownToGoogleDocsConverter()
            formatting_requests = markdown_converter.convert_markdown_to_google_docs_requests(
                request.content
            )
        else:
            # Fallback to basic formatting
            enhanced_google_service = EnhancedGoogleService(firebase_service)
            formatting_requests = enhanced_google_service._parse_content_for_formatting(
                request.content
            )
        
        # Create document with formatting
        result = await create_google_doc_with_custom_formatting(
            user_id=user["uid"],
            title=request.title,
            formatting_requests=formatting_requests
        )
        
        return {
            "success": True,
            "document_id": result["document_id"],
            "document_url": result["document_url"],
            "title": request.title,
            "formatted": True,
            "markdown_converted": request.preserve_markdown,
            "message": "Document created successfully with markdown formatting preserved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating formatted Google Doc: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create Google Doc: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )