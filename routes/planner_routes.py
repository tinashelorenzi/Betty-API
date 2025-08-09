# routes/planner_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, date, timedelta
from typing import Optional, List
from models.planner_models import (
    TaskCreate, TaskResponse, TaskUpdate, TaskStatus, TaskPriority,
    NoteCreate, NoteResponse, NoteUpdate, 
    CalendarEventCreate, CalendarEvent,
    QuickTaskCreate, TaskFilter, PlannerDashboard
)
from services.enhanced_planner_service import EnhancedPlannerService
from services.firebase_service import FirebaseService
from services.google_service import GoogleService
from auth import get_current_user


router = APIRouter(prefix="/planner", tags=["planner"])

# Initialize services (you'll inject these from main.py)
def get_services():
    firebase_service = FirebaseService()
    google_service = GoogleService(firebase_service)
    enhanced_planner_service = EnhancedPlannerService(firebase_service, google_service)
    return enhanced_planner_service

# ========================================================================
# TASK MANAGEMENT ROUTES
# ========================================================================

@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    task: TaskCreate, 
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Create a new task with optional calendar sync"""
    try:
        return await service.create_task(task, user["uid"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/quick", response_model=TaskResponse)
async def create_quick_task(
    quick_task: QuickTaskCreate,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Create a quick task (simplified creation)"""
    try:
        # Convert QuickTaskCreate to full TaskCreate
        due_date = None
        if quick_task.due_today:
            due_date = datetime.now().replace(hour=23, minute=59, second=59)
        
        task = TaskCreate(
            title=quick_task.title,
            priority=quick_task.priority,
            due_date=due_date,
            sync_to_calendar=quick_task.due_today
        )
        
        return await service.create_task(task, user["uid"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks", response_model=List[TaskResponse])
async def get_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
    completed: Optional[bool] = None,
    limit: Optional[int] = Query(default=50, le=100),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get user tasks with filtering options"""
    try:
        task_filter = TaskFilter(
            status=[status] if status else None,
            priority=[priority] if priority else None,
            due_date_from=due_date_from,
            due_date_to=due_date_to
        )
        
        return await service.get_tasks(
            user["uid"], 
            task_filter=task_filter,
            completed=completed,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/today", response_model=List[TaskResponse])
async def get_today_tasks(
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get today's tasks"""
    try:
        today = date.today()
        return await service.get_tasks(
            user["uid"],
            task_filter=TaskFilter(
                due_date_from=today,
                due_date_to=today
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/upcoming", response_model=List[TaskResponse])
async def get_upcoming_tasks(
    days: int = Query(default=7, ge=1, le=30),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get upcoming tasks for the next N days"""
    try:
        today = date.today()
        end_date = today + timedelta(days=days)
        
        return await service.get_tasks(
            user["uid"],
            task_filter=TaskFilter(
                due_date_from=today,
                due_date_to=end_date,
                status=[TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_update: TaskUpdate,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Update an existing task"""
    try:
        return await service.update_task(task_id, task_update, user["uid"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tasks/{task_id}/toggle")
async def toggle_task_completion(
    task_id: str,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Toggle task completion status"""
    try:
        # Get current task first
        current_task = await service.get_task(task_id, user["uid"])
        
        # Toggle status
        new_status = (TaskStatus.COMPLETED 
                     if current_task.status != TaskStatus.COMPLETED 
                     else TaskStatus.TODO)
        
        task_update = TaskUpdate(status=new_status)
        return await service.update_task(task_id, task_update, user["uid"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Delete a task and its associated calendar event"""
    try:
        success = await service.delete_task(task_id, user["uid"])
        return {"success": success, "message": "Task deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# CALENDAR INTEGRATION ROUTES
# ========================================================================

@router.get("/calendar/events")
async def get_calendar_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get calendar events with optional date range"""
    try:
        # Default to next 30 days if no range provided
        if not start_date:
            start_date = date.today().isoformat()
        if not end_date:
            end_date = (date.today() + timedelta(days=30)).isoformat()
        
        events = await service.google_service.get_calendar_events(
            user["uid"], start_date, end_date
        )
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calendar/events")
async def create_calendar_event(
    event_data: CalendarEventCreate,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Create a new calendar event"""
    try:
        result = await service.google_service.create_calendar_event(
            user["uid"], event_data.dict()
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calendar/sync")
async def sync_calendar_tasks(
    days_ahead: int = Query(default=30, ge=1, le=90),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Sync tasks with Google Calendar"""
    try:
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        result = await service.sync_calendar_tasks(
            user["uid"], start_date, end_date
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# NOTES ROUTES
# ========================================================================

@router.post("/notes", response_model=NoteResponse)
async def create_note(
    note: NoteCreate,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Create a new note"""
    try:
        return await service.create_note(note, user["uid"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notes", response_model=List[NoteResponse])
async def get_notes(
    limit: Optional[int] = Query(default=20, le=50),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get user notes"""
    try:
        return await service.get_notes(user["uid"], limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    note_update: NoteUpdate,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Update an existing note"""
    try:
        return await service.update_note(note_id, note_update, user["uid"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Delete a note"""
    try:
        success = await service.delete_note(note_id, user["uid"])
        return {"success": success, "message": "Note deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notes/{note_id}/export-google")
async def export_note_to_google_keep(
    note_id: str,
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Export note to Google Keep"""
    try:
        note = await service.get_note(note_id, user["uid"])
        result = await service.google_service.create_keep_note(
            user["uid"], note.title, note.content
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# DASHBOARD AND ANALYTICS
# ========================================================================

@router.get("/dashboard", response_model=PlannerDashboard)
async def get_planner_dashboard(
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get comprehensive planner dashboard"""
    try:
        return await service.get_planner_dashboard(user["uid"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_planner_stats(
    days: int = Query(default=30, ge=1, le=365),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get planner statistics for specified period"""
    try:
        return await service.get_planner_stats(user["uid"], days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))