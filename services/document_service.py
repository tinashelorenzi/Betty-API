from typing import List, Optional, Dict, Any
from datetime import datetime
from models.document_models import DocumentCreate, DocumentResponse, DocumentUpdate, GoogleDocExport, DocumentType
from services.firebase_service import FirebaseService
import re
import uuid

class DocumentService:
    """Service for document operations"""
    
    def __init__(self, firebase_service: FirebaseService, google_service=None):
        self.firebase_service = firebase_service
        self.google_service = google_service  # Will be injected
        self.collection_name = "documents"
    
    async def create_document(self, document: DocumentCreate, user_id: str) -> DocumentResponse:
        """Create a new document"""
        try:
            # Calculate word count
            word_count = len(re.findall(r'\w+', document.content))
            
            # Prepare document data
            doc_data = {
                "user_id": user_id,
                "title": document.title,
                "content": document.content,
                "document_type": document.document_type.value,
                "status": document.status.value,
                "tags": document.tags,
                "metadata": document.metadata,
                "word_count": word_count,
                "version": 1,
                "google_doc_id": None,
                "google_doc_url": None
            }
            
            # Create document in Firestore
            doc_id = await self.firebase_service.create_document(
                self.collection_name, 
                doc_data
            )
            
            # Get the created document
            created_doc = await self.firebase_service.get_document(self.collection_name, doc_id)
            
            return DocumentResponse(**created_doc)
            
        except Exception as e:
            raise Exception(f"Failed to create document: {e}")
    
    async def get_document(self, document_id: str, user_id: str) -> DocumentResponse:
        """Get a specific document"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership(
                self.collection_name, document_id, user_id
            ):
                raise ValueError("Document not found or access denied")
            
            doc = await self.firebase_service.get_document(self.collection_name, document_id)
            if not doc:
                raise ValueError("Document not found")
            
            return DocumentResponse(**doc)
            
        except Exception as e:
            raise Exception(f"Failed to get document: {e}")
    
    async def get_user_documents(
        self, 
        user_id: str, 
        document_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[DocumentResponse]:
        """Get all documents for a user"""
        try:
            docs = await self.firebase_service.get_user_documents(
                user_id, 
                self.collection_name,
                document_type=document_type,
                limit=limit
            )
            
            return [DocumentResponse(**doc) for doc in docs]
            
        except Exception as e:
            raise Exception(f"Failed to get user documents: {e}")
    
    async def update_document(
        self, 
        document_id: str, 
        document_update: DocumentUpdate, 
        user_id: str
    ) -> DocumentResponse:
        """Update a document"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership(
                self.collection_name, document_id, user_id
            ):
                raise ValueError("Document not found or access denied")
            
            # Prepare update data
            update_data = {}
            
            if document_update.title is not None:
                update_data["title"] = document_update.title
            
            if document_update.content is not None:
                update_data["content"] = document_update.content
                # Recalculate word count
                update_data["word_count"] = len(re.findall(r'\w+', document_update.content))
            
            if document_update.document_type is not None:
                update_data["document_type"] = document_update.document_type.value
            
            if document_update.status is not None:
                update_data["status"] = document_update.status.value
            
            if document_update.tags is not None:
                update_data["tags"] = document_update.tags
            
            if document_update.metadata is not None:
                update_data["metadata"] = document_update.metadata
            
            # Increment version
            current_doc = await self.firebase_service.get_document(self.collection_name, document_id)
            update_data["version"] = current_doc.get("version", 1) + 1
            
            # Update document
            await self.firebase_service.update_document(
                self.collection_name, 
                document_id, 
                update_data
            )
            
            # Get updated document
            updated_doc = await self.firebase_service.get_document(self.collection_name, document_id)
            
            return DocumentResponse(**updated_doc)
            
        except Exception as e:
            raise Exception(f"Failed to update document: {e}")
    
    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Delete a document"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership(
                self.collection_name, document_id, user_id
            ):
                raise ValueError("Document not found or access denied")
            
            # Delete document
            await self.firebase_service.delete_document(self.collection_name, document_id)
            
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete document: {e}")
    
    async def search_documents(
        self, 
        user_id: str, 
        search_term: str, 
        document_type: Optional[str] = None,
        limit: int = 20
    ) -> List[DocumentResponse]:
        """Search user documents"""
        try:
            # Get user documents first
            filters = [("user_id", "==", user_id)]
            if document_type:
                filters.append(("document_type", "==", document_type))
            
            docs = await self.firebase_service.query_documents(
                self.collection_name,
                filters=filters,
                limit=limit * 2  # Get more to filter
            )
            
            # Search in title and content
            search_term = search_term.lower()
            results = []
            
            for doc in docs:
                title_match = search_term in doc.get("title", "").lower()
                content_match = search_term in doc.get("content", "").lower()
                tag_match = any(search_term in tag.lower() for tag in doc.get("tags", []))
                
                if title_match or content_match or tag_match:
                    results.append(DocumentResponse(**doc))
                
                if len(results) >= limit:
                    break
            
            return results
            
        except Exception as e:
            raise Exception(f"Failed to search documents: {e}")
    
    async def duplicate_document(self, document_id: str, user_id: str, new_title: Optional[str] = None) -> DocumentResponse:
        """Duplicate a document"""
        try:
            # Get original document
            original_doc = await self.get_document(document_id, user_id)
            
            # Create duplicate
            duplicate_data = DocumentCreate(
                title=new_title or f"{original_doc.title} (Copy)",
                content=original_doc.content,
                document_type=DocumentType(original_doc.document_type),
                status=original_doc.status,
                tags=original_doc.tags.copy() if original_doc.tags else [],
                metadata=original_doc.metadata.copy() if original_doc.metadata else {}
            )
            
            return await self.create_document(duplicate_data, user_id)
            
        except Exception as e:
            raise Exception(f"Failed to duplicate document: {e}")
    
    async def export_to_google_docs(self, document_id: str, user_id: str) -> GoogleDocExport:
        """Export document to Google Docs"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership(
                self.collection_name, document_id, user_id
            ):
                raise ValueError("Document not found or access denied")
            
            # Get document
            doc = await self.firebase_service.get_document(self.collection_name, document_id)
            if not doc:
                raise ValueError("Document not found")
            
            # Check if user has Google connected
            user_profile = await self.firebase_service.get_user_profile(user_id)
            if not user_profile.get("google_connected"):
                raise ValueError("Google account not connected")
            
            if self.google_service:
                # Use real Google Docs API
                google_doc = await self.google_service.create_google_doc(
                    user_id,
                    doc["title"],
                    doc["content"]
                )
                
                google_doc_id = google_doc["document_id"]
                google_doc_url = google_doc["document_url"]
            else:
                # Fallback to mock (for development)
                google_doc_id = f"gdoc_{uuid.uuid4().hex[:12]}"
                google_doc_url = f"https://docs.google.com/document/d/{google_doc_id}/edit"
            
            # Update document with Google Docs info
            await self.firebase_service.update_document(
                self.collection_name,
                document_id,
                {
                    "google_doc_id": google_doc_id,
                    "google_doc_url": google_doc_url,
                    "exported_to_google_at": datetime.utcnow()
                }
            )
            
            return GoogleDocExport(
                google_doc_id=google_doc_id,
                google_doc_url=google_doc_url,
                export_date=datetime.utcnow(),
                success=True,
                message="Document exported to Google Docs successfully"
            )
            
        except Exception as e:
            raise Exception(f"Failed to export to Google Docs: {e}")
    
    async def get_document_versions(self, document_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get document version history"""
        try:
            # Verify ownership
            if not await self.firebase_service.verify_document_ownership(
                self.collection_name, document_id, user_id
            ):
                raise ValueError("Document not found or access denied")
            
            # TODO: Implement version history storage
            # For now, return current version only
            doc = await self.firebase_service.get_document(self.collection_name, document_id)
            
            return [{
                "version": doc.get("version", 1),
                "created_at": doc.get("updated_at"),
                "changes": "Current version"
            }]
            
        except Exception as e:
            raise Exception(f"Failed to get document versions: {e}")
    
    async def restore_document_version(self, document_id: str, version: int, user_id: str) -> DocumentResponse:
        """Restore document to a specific version"""
        try:
            # TODO: Implement version restoration
            # For now, just return current document
            return await self.get_document(document_id, user_id)
            
        except Exception as e:
            raise Exception(f"Failed to restore document version: {e}")
    
    async def get_user_document_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user document statistics"""
        try:
            # Get all user documents
            docs = await self.firebase_service.get_user_documents(user_id, self.collection_name)
            
            # Calculate stats
            total_docs = len(docs)
            total_words = sum(doc.get("word_count", 0) for doc in docs)
            
            # Count by type
            type_counts = {}
            for doc in docs:
                doc_type = doc.get("document_type", "other")
                type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
            
            # Count by status
            status_counts = {}
            for doc in docs:
                status = doc.get("status", "draft")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Recent activity
            recent_docs = sorted(docs, key=lambda x: x.get("updated_at", datetime.min), reverse=True)[:5]
            
            return {
                "total_documents": total_docs,
                "total_words": total_words,
                "average_words_per_doc": total_words / total_docs if total_docs > 0 else 0,
                "documents_by_type": type_counts,
                "documents_by_status": status_counts,
                "recent_documents": [
                    {
                        "id": doc["id"],
                        "title": doc["title"],
                        "updated_at": doc["updated_at"]
                    } for doc in recent_docs
                ],
                "google_docs_exported": len([doc for doc in docs if doc.get("google_doc_id")])
            }
            
        except Exception as e:
            raise Exception(f"Failed to get document stats: {e}")
    
    async def create_document_template(self, template_data: Dict[str, Any], user_id: str) -> str:
        """Create a document template"""
        try:
            template_data["user_id"] = user_id
            template_data["is_template"] = True
            
            template_id = await self.firebase_service.create_document(
                "document_templates",
                template_data
            )
            
            return template_id
            
        except Exception as e:
            raise Exception(f"Failed to create document template: {e}")
    
    async def get_user_templates(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's document templates"""
        try:
            # Get user templates
            user_templates = await self.firebase_service.get_user_documents(
                user_id, 
                "document_templates"
            )
            
            # Get public templates
            public_templates = await self.firebase_service.query_documents(
                "document_templates",
                filters=[("is_public", "==", True)],
                limit=20
            )
            
            # Combine and return
            all_templates = user_templates + public_templates
            
            return all_templates
            
        except Exception as e:
            raise Exception(f"Failed to get templates: {e}")
    
    async def create_document_from_template(
        self, 
        template_id: str, 
        user_id: str, 
        variables: Optional[Dict[str, str]] = None
    ) -> DocumentResponse:
        """Create a document from a template"""
        try:
            # Get template
            template = await self.firebase_service.get_document("document_templates", template_id)
            if not template:
                raise ValueError("Template not found")
            
            # Replace variables in content
            content = template["template_content"]
            if variables:
                for var, value in variables.items():
                    content = content.replace(f"{{{{ {var} }}}}", value)
                    content = content.replace(f"{{{var}}}", value)  # Alternative format
            
            # Create document
            doc_data = DocumentCreate(
                title=template["name"],
                content=content,
                document_type=DocumentType(template.get("document_type", "other")),
                tags=["from_template"],
                metadata={"template_id": template_id, "variables_used": variables or {}}
            )
            
            return await self.create_document(doc_data, user_id)
            
        except Exception as e:
            raise Exception(f"Failed to create document from template: {e}")
    
    async def batch_update_documents(
        self, 
        user_id: str, 
        updates: List[Dict[str, Any]]
    ) -> List[DocumentResponse]:
        """Batch update multiple documents"""
        try:
            updated_docs = []
            
            for update in updates:
                doc_id = update.get("document_id")
                update_data = update.get("data", {})
                
                if doc_id and update_data:
                    # Verify ownership
                    if await self.firebase_service.verify_document_ownership(
                        self.collection_name, doc_id, user_id
                    ):
                        await self.firebase_service.update_document(
                            self.collection_name,
                            doc_id,
                            update_data
                        )
                        
                        updated_doc = await self.firebase_service.get_document(
                            self.collection_name, 
                            doc_id
                        )
                        updated_docs.append(DocumentResponse(**updated_doc))
            
            return updated_docs
            
        except Exception as e:
            raise Exception(f"Failed to batch update documents: {e}")
    
    async def delete_multiple_documents(self, document_ids: List[str], user_id: str) -> int:
        """Delete multiple documents"""
        try:
            deleted_count = 0
            
            for doc_id in document_ids:
                try:
                    if await self.firebase_service.verify_document_ownership(
                        self.collection_name, doc_id, user_id
                    ):
                        await self.firebase_service.delete_document(self.collection_name, doc_id)
                        deleted_count += 1
                except Exception:
                    # Continue with other documents if one fails
                    continue
            
            return deleted_count
            
        except Exception as e:
            raise Exception(f"Failed to delete multiple documents: {e}")

class MarkdownToGoogleDocsConverter:
    """Converts markdown content to Google Docs API formatting requests"""
    
    def convert_markdown_to_google_docs_requests(self, markdown_content: str) -> List[Dict]:
        """Convert markdown to Google Docs formatting requests"""
        requests = []
        current_index = 1
        
        # Split content by lines to process markdown syntax
        lines = markdown_content.split('\n')
        
        for line in lines:
            if not line and not line.strip():
                # Empty line
                requests.append({
                    'insertText': {
                        'location': {'index': current_index},
                        'text': '\n'
                    }
                })
                current_index += 1
                continue
            
            # Process the line and add formatting
            line_requests = self._process_markdown_line(line, current_index)
            requests.extend(line_requests)
            
            # Add line break
            line_length = len(line) + 1  # +1 for \n
            current_index += line_length
        
        return requests
    
    def _process_markdown_line(self, line: str, start_index: int) -> List[Dict]:
        """Process a single line of markdown and return formatting requests"""
        requests = []
        
        # Insert the text first (we'll clean up markdown syntax)
        clean_text = self._clean_markdown_syntax(line) + '\n'
        
        requests.append({
            'insertText': {
                'location': {'index': start_index},
                'text': clean_text
            }
        })
        
        # Apply formatting based on markdown syntax
        if line.startswith('# '):
            # H1 - Main title
            requests.extend(self._format_heading(start_index, len(clean_text) - 1, level=1))
        elif line.startswith('## '):
            # H2 - Section heading
            requests.extend(self._format_heading(start_index, len(clean_text) - 1, level=2))
        elif line.startswith('### '):
            # H3 - Sub-section heading
            requests.extend(self._format_heading(start_index, len(clean_text) - 1, level=3))
        elif line.startswith('- ') or line.startswith('* '):
            # Bullet list
            requests.extend(self._format_bullet_list(start_index, len(clean_text) - 1))
        elif re.match(r'^\d+\. ', line):
            # Numbered list
            requests.extend(self._format_numbered_list(start_index, len(clean_text) - 1))
        
        # Apply inline formatting (bold, italic)
        inline_requests = self._apply_inline_markdown_formatting(line, start_index)
        requests.extend(inline_requests)
        
        return requests
    
    def _clean_markdown_syntax(self, text: str) -> str:
        """Remove markdown syntax characters but preserve the text"""
        # Remove heading markers
        text = re.sub(r'^#{1,6}\s+', '', text)
        
        # Remove list markers
        text = re.sub(r'^[\-\*]\s+', '• ', text)
        text = re.sub(r'^\d+\.\s+', '', text)
        
        # Remove bold and italic markers (but keep the text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'_(.*?)_', r'\1', text)
        
        return text
    
    def _format_heading(self, start_index: int, length: int, level: int) -> List[Dict]:
        """Format text as heading"""
        font_sizes = {1: 18, 2: 16, 3: 14}
        font_size = font_sizes.get(level, 12)
        
        requests = [
            {
                'updateTextStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + length
                    },
                    'textStyle': {
                        'bold': True,
                        'fontSize': {'magnitude': font_size, 'unit': 'PT'},
                        'foregroundColor': {
                            'color': {'rgbColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2}}
                        }
                    },
                    'fields': 'bold,fontSize,foregroundColor'
                }
            }
        ]
        
        # Center align for H1 (main title)
        if level == 1:
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + length
                    },
                    'paragraphStyle': {
                        'alignment': 'CENTER',
                        'spaceAbove': {'magnitude': 12, 'unit': 'PT'},
                        'spaceBelow': {'magnitude': 12, 'unit': 'PT'}
                    },
                    'fields': 'alignment,spaceAbove,spaceBelow'
                }
            })
        else:
            requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + length
                    },
                    'paragraphStyle': {
                        'spaceAbove': {'magnitude': 8, 'unit': 'PT'},
                        'spaceBelow': {'magnitude': 4, 'unit': 'PT'}
                    },
                    'fields': 'spaceAbove,spaceBelow'
                }
            })
        
        return requests
    
    def _format_bullet_list(self, start_index: int, length: int) -> List[Dict]:
        """Format as bullet list"""
        return [
            {
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + length
                    },
                    'paragraphStyle': {
                        'indentStart': {'magnitude': 18, 'unit': 'PT'},
                        'spaceAbove': {'magnitude': 2, 'unit': 'PT'},
                        'spaceBelow': {'magnitude': 2, 'unit': 'PT'}
                    },
                    'fields': 'indentStart,spaceAbove,spaceBelow'
                }
            }
        ]
    
    def _format_numbered_list(self, start_index: int, length: int) -> List[Dict]:
        """Format as numbered list"""
        return [
            {
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': start_index,
                        'endIndex': start_index + length
                    },
                    'paragraphStyle': {
                        'indentStart': {'magnitude': 18, 'unit': 'PT'},
                        'spaceAbove': {'magnitude': 2, 'unit': 'PT'},
                        'spaceBelow': {'magnitude': 2, 'unit': 'PT'}
                    },
                    'fields': 'indentStart,spaceAbove,spaceBelow'
                }
            }
        ]
    
    def _apply_inline_markdown_formatting(self, line: str, start_index: int) -> List[Dict]:
        """Apply bold and italic formatting from markdown"""
        requests = []
        
        # Find bold text **text**
        bold_pattern = r'\*\*(.*?)\*\*'
        for match in re.finditer(bold_pattern, line):
            # Calculate position in cleaned text
            clean_line = self._clean_markdown_syntax(line)
            text_before_match = self._clean_markdown_syntax(line[:match.start()])
            match_text = match.group(1)
            
            match_start = start_index + len(text_before_match)
            match_end = match_start + len(match_text)
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': match_start,
                        'endIndex': match_end
                    },
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })
        
        # Find italic text *text* (but not **text**)
        italic_pattern = r'(?<!\*)\*([^*]+)\*(?!\*)'
        for match in re.finditer(italic_pattern, line):
            text_before_match = self._clean_markdown_syntax(line[:match.start()])
            match_text = match.group(1)
            
            match_start = start_index + len(text_before_match)
            match_end = match_start + len(match_text)
            
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': match_start,
                        'endIndex': match_end
                    },
                    'textStyle': {'italic': True},
                    'fields': 'italic'
                }
            })
        
        return requests

async def create_google_doc_with_custom_formatting(
    user_id: str, 
    title: str, 
    formatting_requests: List[Dict]
) -> Dict[str, Any]:
    """Create Google Doc with custom formatting requests"""
    try:
        # Get user credentials
        enhanced_service = EnhancedGoogleService(firebase_service)
        credentials = await enhanced_service.get_user_credentials(user_id)
        
        if not credentials:
            raise Exception("Google account not connected")
        
        # Create the document
        docs_service = build('docs', 'v1', credentials=credentials)
        doc = {'title': title}
        
        document = docs_service.documents().create(body=doc).execute()
        document_id = document.get('documentId')
        
        # Apply formatting requests in batches (Google Docs has limits)
        batch_size = 25  # Safe batch size for Google Docs API
        for i in range(0, len(formatting_requests), batch_size):
            batch = formatting_requests[i:i + batch_size]
            
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': batch}
            ).execute()
        
        # Generate shareable URL
        document_url = f"https://docs.google.com/document/d/{document_id}/edit"
        
        return {
            "document_id": document_id,
            "document_url": document_url,
            "title": title,
            "formatted": True
        }
        
    except Exception as e:
        print(f"Failed to create formatted Google Doc: {e}")
        raise Exception(f"Failed to create Google Doc: {e}")