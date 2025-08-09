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
    from main import enhanced_planner_service  # ✅ Use the initialized one
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
    # Individual filter parameters
    status: Optional[str] = Query(None, description="Comma-separated status values"),
    priority: Optional[str] = Query(None, description="Comma-separated priority values"),
    due_date_from: Optional[date] = Query(None, description="Filter tasks due from this date"),
    due_date_to: Optional[date] = Query(None, description="Filter tasks due until this date"),
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    limit: Optional[int] = Query(default=50, le=100, description="Maximum number of tasks to return"),
    search: Optional[str] = Query(None, description="Search in task titles and descriptions"),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get user tasks with filtering options"""
    try:
        # Build TaskFilter from query parameters
        task_filter = TaskFilter()
        
        # Parse status parameter
        if status:
            try:
                status_list = [TaskStatus(s.strip()) for s in status.split(',') if s.strip()]
                task_filter.status = status_list
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid status value: {e}")
        
        # Parse priority parameter
        if priority:
            try:
                priority_list = [TaskPriority(p.strip()) for p in priority.split(',') if p.strip()]
                task_filter.priority = priority_list
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid priority value: {e}")
        
        # Set date filters
        if due_date_from:
            task_filter.due_date_from = due_date_from
        if due_date_to:
            task_filter.due_date_to = due_date_to
        
        # Set search filter
        if search:
            task_filter.search_term = search
        
        print(f"Getting tasks with filter: {task_filter}")  # Debug log
        
        # Call service method with proper parameters
        return await service.get_tasks(
            user["uid"], 
            task_filter=task_filter,
            completed=completed,
            limit=limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_tasks route: {e}")  # Debug log
        raise HTTPException(status_code=500, detail=f"Failed to get tasks: {str(e)}")


@router.get("/tasks/today", response_model=List[TaskResponse])
async def get_today_tasks(
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get today's tasks"""
    try:
        today = date.today()
        task_filter = TaskFilter(
            due_date_from=today,
            due_date_to=today
        )
        
        return await service.get_tasks(
            user["uid"],
            task_filter=task_filter
        )
    except Exception as e:
        print(f"Error getting today's tasks: {e}")
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
        
        task_filter = TaskFilter(
            due_date_from=today,
            due_date_to=end_date,
            status=[TaskStatus.TODO, TaskStatus.IN_PROGRESS]
        )
        
        return await service.get_tasks(
            user["uid"],
            task_filter=task_filter
        )
    except Exception as e:
        print(f"Error getting upcoming tasks: {e}")
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

@router.get("/calendar/events", response_model=List[CalendarEvent])
async def get_calendar_events(
    start_date: date = Query(..., description="Start date for events (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for events (YYYY-MM-DD)"),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Get calendar events for date range - IMPROVED VERSION"""
    try:
        print(f"🔄 Getting calendar events for user {user['uid']} from {start_date} to {end_date}")
        
        # Validate date range
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")
        
        # Convert dates to strings for the service
        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()
        
        # Check if user has Google credentials first
        if hasattr(service, 'google_service'):
            has_credentials = await service.google_service._check_google_credentials(user["uid"])
            
            if not has_credentials:
                print(f"⚠️ User {user['uid']} has no valid Google credentials, returning empty list")
                return []
            
            # Get calendar events from Google
            events = await service.google_service.get_calendar_events(
                user["uid"], 
                start_date_str, 
                end_date_str
            )
            
            # Convert to CalendarEvent objects
            calendar_events = []
            for event in events:
                try:
                    calendar_event = CalendarEvent(
                        id=event.get('id', ''),
                        title=event.get('title', 'No Title'),
                        description=event.get('description', ''),
                        start_time=event.get('start_time', ''),
                        end_time=event.get('end_time', ''),
                        event_type=EventType.GOOGLE_CALENDAR,
                        location=event.get('location', ''),
                        attendees=event.get('attendees', []),
                        created_at=datetime.utcnow().isoformat(),
                        updated_at=datetime.utcnow().isoformat(),
                        user_id=user["uid"],
                        google_event_id=event.get('google_event_id')
                    )
                    calendar_events.append(calendar_event)
                except Exception as e:
                    print(f"⚠️ Error converting event {event.get('id', 'unknown')}: {e}")
                    continue
            
            print(f"✅ Successfully retrieved {len(calendar_events)} calendar events")
            return calendar_events
        else:
            print("❌ Google service not available")
            return []
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in calendar events route: {e}")
        # Return empty list instead of 500 error to prevent mobile app crashes
        return []


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
        print(f"Getting dashboard for user: {user['uid']}")  # Debug log
        dashboard = await service.get_planner_dashboard(user["uid"])
        print(f"Dashboard retrieved successfully")  # Debug log
        return dashboard
    except Exception as e:
        print(f"Error in dashboard route: {e}")  # Debug log
        # Return a basic dashboard instead of 500 error
        from models.planner_models import PlannerStats
        
        return PlannerDashboard(
            stats=PlannerStats(
                total_tasks=0,
                completed_tasks=0,
                pending_tasks=0,
                overdue_tasks=0,
                completion_rate=0,
                total_notes=0
            ),
            upcoming_tasks=[],
            recent_notes=[],
            calendar_events=[],
            overdue_tasks=[]
        )

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

@router.post("/tasks/sync-calendar")
async def sync_tasks_with_calendar(
    days_ahead: int = Query(default=7, ge=1, le=90),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Sync tasks with calendar - alternative endpoint for mobile app compatibility"""
    try:
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        result = await service.sync_calendar_tasks(
            user["uid"], start_date, end_date
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/calendar/sync-google")
async def sync_google_calendar(
    days_ahead: int = Query(default=7, ge=1, le=90),
    user=Depends(get_current_user),
    service: EnhancedPlannerService = Depends(get_services)
):
    """Manually sync with Google Calendar"""
    try:
        print(f"🔄 Manual Google Calendar sync requested for user {user['uid']}")
        
        if not hasattr(service, 'google_service'):
            raise HTTPException(status_code=503, detail="Google service not available")
        
        # Check credentials
        has_credentials = await service.google_service._check_google_credentials(user["uid"])
        if not has_credentials:
            raise HTTPException(
                status_code=401, 
                detail="Google account not connected. Please connect your Google account first."
            )
        
        # Perform sync
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        events = await service.google_service.get_calendar_events(
            user["uid"], 
            start_date.isoformat(), 
            end_date.isoformat()
        )
        
        return {
            "success": True,
            "events_synced": len(events),
            "sync_date": datetime.utcnow().isoformat(),
            "message": f"Successfully synced {len(events)} events"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error syncing Google Calendar: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")