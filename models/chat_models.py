from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

class MessageRole(str, Enum):
    """Enum for message roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class MessageType(str, Enum):
    """Enum for message types"""
    TEXT = "text"
    DOCUMENT_CREATION = "document_creation"
    TASK_CREATION = "task_creation"
    CALENDAR_EVENT = "calendar_event"
    FILE_ANALYSIS = "file_analysis"

class ChatMessage(BaseModel):
    """Model for incoming chat messages"""
    content: str = Field(..., min_length=1, max_length=4000)
    message_type: MessageType = MessageType.TEXT
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    attachments: Optional[List[str]] = Field(default_factory=list)  # File IDs

class ChatResponse(BaseModel):
    """Model for AI chat responses"""
    content: str
    message_type: MessageType = MessageType.TEXT
    
    # Document creation fields
    document_created: bool = False
    document_title: Optional[str] = None
    document_content: Optional[str] = None
    document_type: Optional[str] = None
    
    # Task creation fields
    task_created: bool = False
    task_data: Optional[Dict[str, Any]] = None
    
    # Calendar fields
    calendar_event_created: bool = False
    event_data: Optional[Dict[str, Any]] = None
    
    # Analysis fields
    analysis_data: Optional[Dict[str, Any]] = None
    
    # Metadata
    processing_time: Optional[float] = None
    tokens_used: Optional[int] = None
    confidence_score: Optional[float] = None

class MessageHistory(BaseModel):
    """Model for stored message history"""
    id: str
    user_id: str
    role: MessageRole
    content: str
    message_type: MessageType
    context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    
    # Response metadata
    processing_time: Optional[float] = None
    tokens_used: Optional[int] = None
    
    class Config:
        from_attributes = True

class ConversationSummary(BaseModel):
    """Model for conversation summary"""
    user_id: str
    total_messages: int
    last_message_at: datetime
    topics_discussed: List[str] = Field(default_factory=list)
    documents_created: int = 0
    tasks_created: int = 0

class AIContext(BaseModel):
    """Model for AI context information"""
    user_location: str = "Johannesburg, South Africa"
    user_timezone: str = "Africa/Johannesburg"
    current_time: datetime
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[MessageHistory] = Field(default_factory=list)
    recent_documents: List[str] = Field(default_factory=list)  # Document IDs
    recent_tasks: List[str] = Field(default_factory=list)  # Task IDs

class ChatSettings(BaseModel):
    """Model for chat settings"""
    user_id: str
    ai_personality: str = "professional"  # professional, casual, creative
    response_length: str = "medium"  # short, medium, long
    auto_create_documents: bool = True
    auto_create_tasks: bool = False
    language: str = "en"
    max_context_messages: int = 10