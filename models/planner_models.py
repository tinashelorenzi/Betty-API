# models/planner_models.py - Enhanced version
from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

# Enums
class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class NoteType(str, Enum):
    TEXT = "text"
    CHECKLIST = "checklist"
    VOICE_MEMO = "voice_memo"
    MEETING_NOTES = "meeting_notes"

class EventType(str, Enum):
    TASK_DEADLINE = "task_deadline"
    MEETING = "meeting"
    REMINDER = "reminder"
    APPOINTMENT = "appointment"

class RecordingStatus(str, Enum):
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# Task Models
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[TaskPriority] = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}
    sync_to_calendar: Optional[bool] = False

    @validator('title')
    def title_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class TaskResponse(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    priority: TaskPriority
    status: TaskStatus
    due_date: Optional[datetime] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    completed_at: Optional[datetime] = None
    calendar_event_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Note Models
class NoteCreate(BaseModel):
    title: str
    content: str
    note_type: Optional[NoteType] = NoteType.TEXT
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}

    @validator('title')
    def title_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[NoteType] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class NoteResponse(BaseModel):
    id: str
    user_id: str
    title: str
    content: str
    note_type: NoteType
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    google_keep_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Calendar Models
class CalendarEventCreate(BaseModel):
    summary: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime
    timezone: Optional[str] = "UTC"
    attendees: Optional[List[str]] = []
    location: Optional[str] = None
    reminders: Optional[List[Dict[str, Any]]] = []

class CalendarEvent(BaseModel):
    id: str
    summary: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime
    timezone: str
    attendees: List[str] = []
    location: Optional[str] = None
    event_type: EventType
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Recording Models
class RecordingCreate(BaseModel):
    title: str
    meeting_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class RecordingUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[RecordingStatus] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = None

class MeetingRecording(BaseModel):
    id: str
    user_id: str
    title: str
    status: RecordingStatus
    file_url: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: List[str] = []
    duration_seconds: Optional[int] = None
    meeting_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Dashboard and Stats Models
class PlannerStats(BaseModel):
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    overdue_tasks: int
    completion_rate: float
    total_notes: int
    tasks_this_week: Optional[int] = 0
    tasks_completed_this_week: Optional[int] = 0

class PlannerDashboard(BaseModel):
    stats: PlannerStats
    upcoming_tasks: List[TaskResponse]
    recent_notes: List[NoteResponse]
    calendar_events: List[CalendarEvent]
    overdue_tasks: List[TaskResponse]

# Search and Filter Models
class TaskFilter(BaseModel):
    status: Optional[List[TaskStatus]] = None
    priority: Optional[List[TaskPriority]] = None
    tags: Optional[List[str]] = None
    due_date_from: Optional[date] = None
    due_date_to: Optional[date] = None
    created_after: Optional[datetime] = None
    search_term: Optional[str] = None

class NoteFilter(BaseModel):
    note_type: Optional[List[NoteType]] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    search_term: Optional[str] = None

# Bulk Operations Models
class BulkTaskUpdate(BaseModel):
    task_ids: List[str]
    update: TaskUpdate

class BulkTaskResponse(BaseModel):
    updated_count: int
    failed_count: int
    updated_tasks: List[TaskResponse]
    errors: List[str] = []

# Integration Models
class GoogleKeepExport(BaseModel):
    note_id: str
    export_as_checklist: Optional[bool] = False

class CalendarSyncRequest(BaseModel):
    sync_existing_tasks: Optional[bool] = True
    days_ahead: Optional[int] = 30
    create_reminders: Optional[bool] = True

class CalendarSyncResponse(BaseModel):
    synced_tasks: int
    created_events: int
    updated_events: int
    errors: List[str] = []

# Quick Action Models
class QuickTaskCreate(BaseModel):
    title: str
    due_today: Optional[bool] = False
    priority: Optional[TaskPriority] = TaskPriority.MEDIUM

class QuickNoteCreate(BaseModel):
    content: str
    title: Optional[str] = None  # Auto-generated from content if not provided

# Notification Models
class TaskReminder(BaseModel):
    task_id: str
    reminder_type: str  # "due_soon", "overdue", "completed"
    message: str
    scheduled_at: datetime

class PlannerNotification(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    type: str  # "task_reminder", "calendar_event", "sync_status"
    data: Dict[str, Any] = {}
    read: bool = False
    created_at: datetime