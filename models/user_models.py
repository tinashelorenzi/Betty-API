# models/user_models.py - COMPLETE REWRITE
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class UserBase(BaseModel):
    """Base user model with common fields"""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    location: Optional[str] = "Johannesburg, South Africa"
    timezone: Optional[str] = "Africa/Johannesburg"

class UserCreate(UserBase):
    """Model for creating a new user"""
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)
    
    def passwords_match(self) -> bool:
        return self.password == self.confirm_password

class UserUpdate(BaseModel):
    """Model for updating user information"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    location: Optional[str] = None
    timezone: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

class UserResponse(BaseModel):
    """Model for user response (excludes sensitive data)"""
    uid: str
    email: str
    first_name: str
    last_name: str
    location: Optional[str]
    timezone: Optional[str]
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool = False
    google_connected: bool = False
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    preferences: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    """Model for user login"""
    email: EmailStr
    password: str

class AuthToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse

class GoogleAuthUser(BaseModel):
    """Model for Google OAuth user data"""
    google_id: str
    email: EmailStr
    first_name: str
    last_name: str
    picture_url: Optional[str] = None
    verified_email: bool = False

class ProfileStats(BaseModel):
    """Model for user activity statistics"""
    uid: str
    tasks_completed: int = 0
    documents_created: int = 0
    hours_saved: float = 0.0
    ai_chats: int = 0
    last_activity: Optional[datetime] = None
    streak_days: int = 0
    total_login_days: int = 0

class NotificationPreference(str, Enum):
    """Notification preference levels"""
    ALL = "all"
    IMPORTANT = "important"
    NONE = "none"

class NotificationSettings(BaseModel):
    """Model for notification preferences"""
    uid: str
    push_notifications: bool = True
    email_notifications: bool = True
    task_reminders: NotificationPreference = NotificationPreference.ALL
    document_updates: NotificationPreference = NotificationPreference.IMPORTANT
    ai_suggestions: NotificationPreference = NotificationPreference.ALL
    marketing_emails: bool = False
    security_alerts: bool = True
    weekly_digest: bool = True
    quiet_hours_start: Optional[str] = "22:00"  # Format: "HH:MM"
    quiet_hours_end: Optional[str] = "07:00"
    weekend_notifications: bool = False
    updated_at: Optional[datetime] = None

    @validator('quiet_hours_start', 'quiet_hours_end')
    def validate_time_format(cls, v):
        if v is not None:
            try:
                hours, minutes = v.split(':')
                hours, minutes = int(hours), int(minutes)
                if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError('Time must be in HH:MM format')
        return v

class UserPreferences(BaseModel):
    """Model for user app preferences"""
    uid: str
    theme: str = "light"  # light, dark, auto
    language: str = "en"
    currency: str = "ZAR"
    date_format: str = "DD/MM/YYYY"
    time_format: str = "24h"  # 12h, 24h
    default_view: str = "home"  # home, assistant, documents, planner
    auto_save: bool = True
    analytics_enabled: bool = True
    updated_at: Optional[datetime] = None

class LoginRequest(BaseModel):
    email: str
    password: str