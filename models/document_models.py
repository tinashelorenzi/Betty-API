from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class DocumentType(str, Enum):
    """Enum for document types"""
    CONTRACT = "contract"
    MOI = "moi"
    BUSINESS_PLAN = "business_plan"
    INVOICE = "invoice"
    PROPOSAL = "proposal"
    NDA = "nda"
    POLICY = "policy"
    TEMPLATE = "template"
    AI_GENERATED = "ai_generated"
    OTHER = "other"

class DocumentStatus(str, Enum):
    """Enum for document status"""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    ARCHIVED = "archived"

class DocumentBase(BaseModel):
    """Base document model"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    document_type: DocumentType = DocumentType.OTHER
    status: DocumentStatus = DocumentStatus.DRAFT
    tags: list[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DocumentCreate(DocumentBase):
    """Model for creating a new document"""
    pass

class DocumentUpdate(BaseModel):
    """Model for updating a document"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    document_type: Optional[DocumentType] = None
    status: Optional[DocumentStatus] = None
    tags: Optional[list[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class DocumentResponse(DocumentBase):
    """Model for document response"""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    google_doc_id: Optional[str] = None
    google_doc_url: Optional[str] = None
    version: int = 1
    word_count: int = 0
    
    class Config:
        from_attributes = True

class DocumentSummary(BaseModel):
    """Model for document summary (list view)"""
    id: str
    title: str
    document_type: DocumentType
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    word_count: int
    tags: list[str]

class GoogleDocExport(BaseModel):
    """Model for Google Docs export response"""
    google_doc_id: str
    google_doc_url: str
    export_date: datetime
    success: bool = True
    message: str = "Document exported successfully"

class DocumentTemplate(BaseModel):
    """Model for document templates"""
    name: str
    description: str
    document_type: DocumentType
    template_content: str
    variables: list[str] = Field(default_factory=list)  # Variables that can be replaced
    is_public: bool = False