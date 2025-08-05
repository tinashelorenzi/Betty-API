from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from models.planner_models import (
    TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskPriority,
    NoteCreate, NoteResponse, NoteUpdate, NoteType,
    CalendarEvent, CalendarEventCreate, EventType,
    MeetingRecording, RecordingCreate, RecordingUpdate, RecordingStatus,
    PlannerDashboard, PlannerStats
)
from services.firebase_service import FirebaseService

class PlannerService:
    """Service for planner operations (tasks, notes, calendar, recordings)"""
    
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
    
    # ========================================================================
    # TASK OPERATIONS
    # ========================================================================
    
    async def create_task(self, task: TaskCreate, user_id: str) -> TaskResponse:
        """Create a new task"""
        try:
            task_data = {
                "user_id": user_id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority.value,
                "status": task.status.value,
                "due_date": task.due_date,
                "tags": task.tags,
                "metadata": task.metadata,
                "completed_at": None
            }
            
            task_id = await self.firebase_service.create_document("tasks", task_data)
            created_task = await self.firebase_service.get_document("tasks", task_id)
            
            return TaskResponse(**created_task)
            
        except Exception as e:
            raise Exception(f"Failed to create task: {e}")
    
    async def get_tasks(
        self, 
        user_id: str, 
        completed: Optional[bool] = None,
        priority: Optional[TaskPriority] = None,
        limit: Optional[int] = None
    ) -> List[TaskResponse]:
        """Get user tasks with optional filters"""
        try:
            filters = [("user_id", "==", user_id)]
            
            if completed is not None:
                status = TaskStatus.COMPLETED if completed else TaskStatus.TODO
                if not completed:
                    # Get both TODO and IN_PROGRESS for incomplete tasks
                    filters.append(("status", "in", [TaskStatus.TODO.value, TaskStatus.IN_PROGRESS.value]))
                else:
                    filters.append(("status", "==", status.value))
            
            if priority:
                filters.append(("priority", "==", priority.value))
            
            tasks = await self.firebase_service.query_documents(
                "tasks",
                filters=filters,
                order_by="-created_at",
                limit=limit
            )
            
            return [TaskResponse(**task) for task in tasks]
            
        except Exception as e:
            raise Exception(f"Failed to get tasks: {e}")
    
    async def get_task(self, task_id: str, user_id: str) -> TaskResponse:
        """Get a specific task"""
        try:
            if not await self.firebase_service.verify_document_ownership("tasks", task_id, user_id):
                raise ValueError("Task not found or access denied")
            
            task = await self.firebase_service.get_document("tasks", task_id)
            if not task:
                raise ValueError("Task not found")
            
            return TaskResponse(**task)
            
        except Exception as e:
            raise Exception(f"Failed to get task: {e}")
    
    async def update_task(self, task_id: str, task_update: TaskUpdate, user_id: str) -> TaskResponse:
        """Update a task"""
        try:
            if not await self.firebase_service.verify_document_ownership("tasks", task_id, user_id):
                raise ValueError("Task not found or access denied")
            
            update_data = {}
            
            if task_update.title is not None:
                update_data["title"] = task_update.title
            if task_update.description is not None:
                update_data["description"] = task_update.description
            if task_update.priority is not None:
                update_data["priority"] = task_update.priority.value
            if task_update.status is not None:
                update_data["status"] = task_update.status.value
                # Set completed_at if status is completed
                if task_update.status == TaskStatus.COMPLETED:
                    update_data["completed_at"] = datetime.utcnow()
                elif task_update.status != TaskStatus.COMPLETED:
                    update_data["completed_at"] = None
            if task_update.due_date is not None:
                update_data["due_date"] = task_update.due_date
            if task_update.tags is not None:
                update_data["tags"] = task_update.tags
            if task_update.metadata is not None:
                update_data["metadata"] = task_update.metadata
            
            await self.firebase_service.update_document("tasks", task_id, update_data)
            updated_task = await self.firebase_service.get_document("tasks", task_id)
            
            return TaskResponse(**updated_task)
            
        except Exception as e:
            raise Exception(f"Failed to update task: {e}")
    
    async def delete_task(self, task_id: str, user_id: str) -> bool:
        """Delete a task"""
        try:
            if not await self.firebase_service.verify_document_ownership("tasks", task_id, user_id):
                raise ValueError("Task not found or access denied")
            
            await self.firebase_service.delete_document("tasks", task_id)
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete task: {e}")
    
    async def get_overdue_tasks(self, user_id: str) -> List[TaskResponse]:
        """Get overdue tasks for user"""
        try:
            now = datetime.utcnow()
            tasks = await self.firebase_service.query_documents(
                "tasks",
                filters=[
                    ("user_id", "==", user_id),
                    ("status", "!=", TaskStatus.COMPLETED.value),
                    ("due_date", "<", now)
                ],
                order_by="due_date"
            )
            
            return [TaskResponse(**task) for task in tasks]
            
        except Exception as e:
            raise Exception(f"Failed to get overdue tasks: {e}")
    
    async def get_tasks_due_today(self, user_id: str) -> List[TaskResponse]:
        """Get tasks due today"""
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            tasks = await self.firebase_service.query_documents(
                "tasks",
                filters=[
                    ("user_id", "==", user_id),
                    ("status", "!=", TaskStatus.COMPLETED.value),
                    ("due_date", ">=", today_start),
                    ("due_date", "<", today_end)
                ],
                order_by="due_date"
            )
            
            return [TaskResponse(**task) for task in tasks]
            
        except Exception as e:
            raise Exception(f"Failed to get tasks due today: {e}")
    
    # ========================================================================
    # NOTE OPERATIONS
    # ========================================================================
    
    async def create_note(self, note: NoteCreate, user_id: str) -> NoteResponse:
        """Create a new note"""
        try:
            word_count = len(note.content.split())
            
            note_data = {
                "user_id": user_id,
                "title": note.title,
                "content": note.content,
                "note_type": note.note_type.value,
                "tags": note.tags,
                "is_pinned": note.is_pinned,
                "metadata": note.metadata,
                "word_count": word_count,
                "google_keep_id": None
            }
            
            note_id = await self.firebase_service.create_document("notes", note_data)
            created_note = await self.firebase_service.get_document("notes", note_id)
            
            return NoteResponse(**created_note)
            
        except Exception as e:
            raise Exception(f"Failed to create note: {e}")
    
    async def get_notes(
        self, 
        user_id: str, 
        note_type: Optional[NoteType] = None,
        pinned_only: bool = False,
        limit: Optional[int] = None
    ) -> List[NoteResponse]:
        """Get user notes with optional filters"""
        try:
            filters = [("user_id", "==", user_id)]
            
            if note_type:
                filters.append(("note_type", "==", note_type.value))
            
            if pinned_only:
                filters.append(("is_pinned", "==", True))
            
            notes = await self.firebase_service.query_documents(
                "notes",
                filters=filters,
                order_by="-updated_at",
                limit=limit
            )
            
            return [NoteResponse(**note) for note in notes]
            
        except Exception as e:
            raise Exception(f"Failed to get notes: {e}")
    
    async def get_note(self, note_id: str, user_id: str) -> NoteResponse:
        """Get a specific note"""
        try:
            if not await self.firebase_service.verify_document_ownership("notes", note_id, user_id):
                raise ValueError("Note not found or access denied")
            
            note = await self.firebase_service.get_document("notes", note_id)
            if not note:
                raise ValueError("Note not found")
            
            return NoteResponse(**note)
            
        except Exception as e:
            raise Exception(f"Failed to get note: {e}")
    
    async def update_note(self, note_id: str, note_update: NoteUpdate, user_id: str) -> NoteResponse:
        """Update a note"""
        try:
            if not await self.firebase_service.verify_document_ownership("notes", note_id, user_id):
                raise ValueError("Note not found or access denied")
            
            update_data = {}
            
            if note_update.title is not None:
                update_data["title"] = note_update.title
            if note_update.content is not None:
                update_data["content"] = note_update.content
                update_data["word_count"] = len(note_update.content.split())
            if note_update.note_type is not None:
                update_data["note_type"] = note_update.note_type.value
            if note_update.tags is not None:
                update_data["tags"] = note_update.tags
            if note_update.is_pinned is not None:
                update_data["is_pinned"] = note_update.is_pinned
            if note_update.metadata is not None:
                update_data["metadata"] = note_update.metadata
            
            await self.firebase_service.update_document("notes", note_id, update_data)
            updated_note = await self.firebase_service.get_document("notes", note_id)
            
            return NoteResponse(**updated_note)
            
        except Exception as e:
            raise Exception(f"Failed to update note: {e}")
    
    async def delete_note(self, note_id: str, user_id: str) -> bool:
        """Delete a note"""
        try:
            if not await self.firebase_service.verify_document_ownership("notes", note_id, user_id):
                raise ValueError("Note not found or access denied")
            
            await self.firebase_service.delete_document("notes", note_id)
            return True
            
        except Exception as e:
            raise Exception(f"Failed to delete note: {e}")
    
    async def search_notes(self, user_id: str, search_term: str, limit: int = 20) -> List[NoteResponse]:
        """Search user notes"""
        try:
            notes = await self.firebase_service.search_documents(
                "notes",
                search_term,
                ["title", "content"],
                user_id=user_id,
                limit=limit
            )
            
            return [NoteResponse(**note) for note in notes]
            
        except Exception as e:
            raise Exception(f"Failed to search notes: {e}")
    
    async def export_note_to_google_keep(self, note_id: str, user_id: str) -> Dict[str, Any]:
        """Export note to Google Keep"""
        try:
            if not await self.firebase_service.verify_document_ownership("notes", note_id, user_id):
                raise ValueError("Note not found or access denied")
            
            # Check if user has Google connected
            user_profile = await self.firebase_service.get_user_profile(user_id)
            if not user_profile.get("google_connected"):
                raise ValueError("Google account not connected")
            
            note = await self.firebase_service.get_document("notes", note_id)
            
            # TODO: Implement actual Google Keep API integration
            # For now, simulate the export
            google_keep_id = f"keep_{note_id[:12]}"
            
            # Update note with Google Keep info
            await self.firebase_service.update_document(
                "notes",
                note_id,
                {
                    "google_keep_id": google_keep_id,
                    "exported_to_google_at": datetime.utcnow()
                }
            )
            
            return {
                "success": True,
                "google_keep_id": google_keep_id,
                "message": "Note exported to Google Keep successfully"
            }
            
        except Exception as e:
            raise Exception(f"Failed to export to Google Keep: {e}")
    
    # ========================================================================
    # CALENDAR OPERATIONS
    # ========================================================================
    
    async def get_calendar_events(
        self, 
        user_id: str, 
        start_date: str, 
        end_date: str
    ) -> List[CalendarEvent]:
        """Get calendar events for date range"""
        try:
            # TODO: Implement Google Calendar API integration
            # For now, return mock events
            
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            # Mock events
            mock_events = [
                CalendarEvent(
                    id="event_1",
                    title="Team Meeting",
                    description="Weekly team sync",
                    start_time=start_dt + timedelta(days=1, hours=9),
                    end_time=start_dt + timedelta(days=1, hours=10),
                    event_type=EventType.MEETING,
                    location="Conference Room A"
                ),
                CalendarEvent(
                    id="event_2",
                    title="Client Presentation",
                    description="Q4 Results Presentation",
                    start_time=start_dt + timedelta(days=3, hours=14),
                    end_time=start_dt + timedelta(days=3, hours=15, minutes=30),
                    event_type=EventType.BUSINESS,
                    attendees=["client@example.com"]
                )
            ]
            
            return mock_events
            
        except Exception as e:
            raise Exception(f"Failed to get calendar events: {e}")
    
    async def create_calendar_event(self, event: CalendarEventCreate, user_id: str) -> CalendarEvent:
        """Create a calendar event"""
        try:
            # TODO: Implement Google Calendar API integration
            # For now, store in our database
            
            event_data = {
                "user_id": user_id,
                "title": event.title,
                "description": event.description,
                "start_time": event.start_time,
                "end_time": event.end_time,
                "location": event.location,
                "event_type": event.event_type.value,
                "attendees": event.attendees,
                "is_all_day": event.is_all_day,
                "reminder_minutes": event.reminder_minutes,
                "google_event_id": None
            }
            
            event_id = await self.firebase_service.create_document("calendar_events", event_data)
            created_event = await self.firebase_service.get_document("calendar_events", event_id)
            
            return CalendarEvent(**created_event)
            
        except Exception as e:
            raise Exception(f"Failed to create calendar event: {e}")
    
    # ========================================================================
    # MEETING RECORDER OPERATIONS
    # ========================================================================
    
    async def create_recording(self, recording: RecordingCreate, user_id: str) -> MeetingRecording:
        """Create a new meeting recording"""
        try:
            recording_data = {
                "user_id": user_id,
                "title": recording.title,
                "participants": recording.participants,
                "duration_seconds": 0,
                "status": RecordingStatus.IDLE.value,
                "file_url": None,
                "transcript": None,
                "summary": None,
                "action_items": [],
                "completed_at": None,
                "metadata": {}
            }
            
            recording_id = await self.firebase_service.create_document("recordings", recording_data)
            created_recording = await self.firebase_service.get_document("recordings", recording_id)
            
            return MeetingRecording(**created_recording)
            
        except Exception as e:
            raise Exception(f"Failed to create recording: {e}")
    
    async def update_recording(
        self, 
        recording_id: str, 
        recording_update: RecordingUpdate, 
        user_id: str
    ) -> MeetingRecording:
        """Update a recording"""
        try:
            if not await self.firebase_service.verify_document_ownership("recordings", recording_id, user_id):
                raise ValueError("Recording not found or access denied")
            
            update_data = {}
            
            if recording_update.title is not None:
                update_data["title"] = recording_update.title
            if recording_update.status is not None:
                update_data["status"] = recording_update.status.value
                if recording_update.status == RecordingStatus.COMPLETED:
                    update_data["completed_at"] = datetime.utcnow()
            if recording_update.transcript is not None:
                update_data["transcript"] = recording_update.transcript
            if recording_update.summary is not None:
                update_data["summary"] = recording_update.summary
            if recording_update.action_items is not None:
                update_data["action_items"] = recording_update.action_items
            
            await self.firebase_service.update_document("recordings", recording_id, update_data)
            updated_recording = await self.firebase_service.get_document("recordings", recording_id)
            
            return MeetingRecording(**updated_recording)
            
        except Exception as e:
            raise Exception(f"Failed to update recording: {e}")
    
    async def get_user_recordings(self, user_id: str, limit: Optional[int] = None) -> List[MeetingRecording]:
        """Get user recordings"""
        try:
            recordings = await self.firebase_service.get_user_documents(
                user_id, 
                "recordings",
                limit=limit
            )
            
            return [MeetingRecording(**recording) for recording in recordings]
            
        except Exception as e:
            raise Exception(f"Failed to get recordings: {e}")
    
    # ========================================================================
    # DASHBOARD & ANALYTICS
    # ========================================================================
    
    async def get_planner_dashboard(self, user_id: str) -> PlannerDashboard:
        """Get planner dashboard data"""
        try:
            # Get today's tasks
            today_tasks = await self.get_tasks_due_today(user_id)
            
            # Get overdue tasks
            overdue_tasks = await self.get_overdue_tasks(user_id)
            
            # Get completed tasks today
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            completed_today = await self.firebase_service.query_documents(
                "tasks",
                filters=[
                    ("user_id", "==", user_id),
                    ("status", "==", TaskStatus.COMPLETED.value),
                    ("completed_at", ">=", today_start),
                    ("completed_at", "<", today_end)
                ]
            )
            
            # Get upcoming calendar events
            end_date = (datetime.now() + timedelta(days=7)).isoformat()
            upcoming_events = await self.get_calendar_events(
                user_id, 
                datetime.now().isoformat(), 
                end_date
            )
            
            # Get recent notes
            recent_notes = await self.get_notes(user_id, limit=5)
            
            # Get active recordings
            active_recordings = await self.firebase_service.query_documents(
                "recordings",
                filters=[
                    ("user_id", "==", user_id),
                    ("status", "in", [RecordingStatus.RECORDING.value, RecordingStatus.PROCESSING.value])
                ]
            )
            
            return PlannerDashboard(
                user_id=user_id,
                today_tasks=len(today_tasks),
                overdue_tasks=len(overdue_tasks),
                completed_tasks_today=len(completed_today),
                upcoming_events=upcoming_events[:5],
                recent_notes=recent_notes,
                active_recordings=len(active_recordings)
            )
            
        except Exception as e:
            raise Exception(f"Failed to get planner dashboard: {e}")
    
    async def get_planner_stats(self, user_id: str) -> PlannerStats:
        """Get planner statistics"""
        try:
            # Get all tasks
            all_tasks = await self.get_tasks(user_id)
            completed_tasks = [task for task in all_tasks if task.status == TaskStatus.COMPLETED]
            
            # Get all notes
            all_notes = await self.get_notes(user_id)
            
            # Get all recordings
            all_recordings = await self.get_user_recordings(user_id)
            
            # Calculate completion rate
            completion_rate = len(completed_tasks) / len(all_tasks) if all_tasks else 0
            
            # Get most used tags
            all_tags = []
            for task in all_tasks:
                all_tags.extend(task.tags)
            for note in all_notes:
                all_tags.extend(note.tags)
            
            tag_counts = {}
            for tag in all_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            most_used_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            most_used_tags = [tag[0] for tag in most_used_tags]
            
            # Calculate productivity score (simplified)
            productivity_score = min(completion_rate * 100, 100)
            
            return PlannerStats(
                total_tasks=len(all_tasks),
                completed_tasks=len(completed_tasks),
                completion_rate=completion_rate,
                total_notes=len(all_notes),
                total_recordings=len(all_recordings),
                most_used_tags=most_used_tags,
                productivity_score=productivity_score
            )
            
        except Exception as e:
            raise Exception(f"Failed to get planner stats: {e}")