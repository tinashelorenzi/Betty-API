from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from enum import Enum

# ============================================================================
# TASK MODELS
# ============================================================================

class TaskPriority(str, Enum):
    """Enum for task priorities"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskStatus(str, Enum):
    """Enum for task status"""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TaskBase(BaseModel):
    """Base task model"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    due_date: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TaskCreate(TaskBase):
    """Model for creating a new task"""
    pass

class TaskUpdate(BaseModel):
    """Model for updating a task"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class TaskResponse(TaskBase):
    """Model for task response"""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# ============================================================================
# NOTE MODELS
# ============================================================================

class NoteType(str, Enum):
    """Enum for note types"""
    GENERAL = "general"
    MEETING = "meeting"
    IDEA = "idea"
    PROJECT = "project"
    PERSONAL = "personal"

class NoteBase(BaseModel):
    """Base note model"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    note_type: NoteType = NoteType.GENERAL
    tags: List[str] = Field(default_factory=list)
    is_pinned: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class NoteCreate(NoteBase):
    """Model for creating a new note"""
    pass

class NoteUpdate(BaseModel):
    """Model for updating a note"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    note_type: Optional[NoteType] = None
    tags: Optional[List[str]] = None
    is_pinned: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

class NoteResponse(NoteBase):
    """Model for note response"""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    google_keep_id: Optional[str] = None
    word_count: int = 0
    
    class Config:
        from_attributes = True

# ============================================================================
# CALENDAR MODELS
# ============================================================================

class EventType(str, Enum):
    """Enum for calendar event types"""
    MEETING = "meeting"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"
    DEADLINE = "deadline"
    PERSONAL = "personal"
    BUSINESS = "business"

class CalendarEvent(BaseModel):
    """Model for calendar events"""
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    event_type: EventType = EventType.MEETING
    attendees: List[str] = Field(default_factory=list)  # Email addresses
    is_all_day: bool = False
    reminder_minutes: Optional[int] = 15
    google_event_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CalendarEventCreate(BaseModel):
    """Model for creating calendar events"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    event_type: EventType = EventType.MEETING
    attendees: List[str] = Field(default_factory=list)
    is_all_day: bool = False
    reminder_minutes: Optional[int] = 15

# ============================================================================
# MEETING RECORDER MODELS
# ============================================================================

class RecordingStatus(str, Enum):
    """Enum for recording status"""
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class MeetingRecording(BaseModel):
    """Model for meeting recordings"""
    id: str
    user_id: str
    title: str
    duration_seconds: int
    status: RecordingStatus
    file_url: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: List[str] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True

class RecordingCreate(BaseModel):
    """Model for creating a new recording"""
    title: str = Field(..., min_length=1, max_length=200)
    participants: List[str] = Field(default_factory=list)

class RecordingUpdate(BaseModel):
    """Model for updating recording"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    status: Optional[RecordingStatus] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[List[str]] = None

# ============================================================================
# PLANNER DASHBOARD MODELS
# ============================================================================

class PlannerDashboard(BaseModel):
    """Model for planner dashboard data"""
    user_id: str
    today_tasks: int
    overdue_tasks: int
    completed_tasks_today: int
    upcoming_events: List[CalendarEvent]
    recent_notes: List[NoteResponse]
    active_recordings: int
    
class PlannerStats(BaseModel):
    """Model for planner statistics"""
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    total_notes: int
    total_recordings: int
    most_used_tags: List[str]
    productivity_score: float