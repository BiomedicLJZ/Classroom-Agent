# ta/tools/calendar.py
from datetime import datetime, timedelta, timezone
from functools import cache

from googleapiclient.discovery import build
from langchain_core.tools import tool

from ta.google_auth import get_credentials
from ta.session import get_active_account


@cache
def _calendar_service(alias: str):
    creds = get_credentials(alias)
    return build("calendar", "v3", credentials=creds)


@tool
def list_calendar_events(time_min: str = "", time_max: str = "", calendar_id: str = "primary") -> str:
    """List events from a Google Calendar.
    time_min/max: RFC3339 timestamps (e.g., '2026-06-14T00:00:00Z').
    Defaults to the next 7 days if omitted."""
    svc = _calendar_service(get_active_account())
    
    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()
    if not time_max:
        time_max = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    try:
        events_result = svc.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])

        if not events:
            return "No upcoming events found."

        lines = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            lines.append(f"- [{start}] {event.get('summary', 'No Title')} (id: {event['id']})")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR listing calendar events: {e}"


@tool
def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "", calendar_id: str = "primary") -> str:
    """Create a new event in a Google Calendar.
    start_time/end_time: RFC3339 timestamps (e.g., '2026-06-14T10:00:00Z')."""
    svc = _calendar_service(get_active_account())
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    try:
        result = svc.events().insert(calendarId=calendar_id, body=event).execute()
        return f"SUCCESS: Event created (id: {result['id']})."
    except Exception as e:
        return f"ERROR creating calendar event: {e}"


@tool
def get_weekly_briefing() -> str:
    """Generate a summary of the next 7 days, including Calendar events and Classroom deadlines."""
    # This is a high-level tool that uses other tools or services.
    # For now, we'll list calendar events and Classroom coursework due dates.
    from ta.tools.classroom import _classroom_service, _collect_pages
    
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)
    
    # 1. Get Calendar Events
    try:
        cal_summary = list_calendar_events.invoke({
            "time_min": now.isoformat(),
            "time_max": week_end.isoformat()
        })
    except Exception as e:
        cal_summary = f"ERROR listing calendar events: {e}"
    
    # 2. Get Classroom Assignments
    class_svc = _classroom_service(get_active_account())
    try:
        courses = _collect_pages(
            lambda tok: class_svc.courses().list(courseStates=["ACTIVE"], pageToken=tok),
            "courses"
        )
    except Exception as e:
        courses = []
        cal_summary += f"\n[Warning: could not retrieve Google Classroom courses: {e}]"
    
    deadlines = []
    for course in courses:
        cid = course["id"]
        cname = course.get("name", "Unknown")
        try:
            coursework = _collect_pages(
                lambda tok: class_svc.courses().courseWork().list(courseId=cid, pageToken=tok),
                "courseWork"
            )
        except Exception:
            # Skip courses that cannot be listed (e.g. permission issues)
            continue
        for cw in coursework:
            if "dueDate" in cw:
                due = cw["dueDate"]
                dt = datetime(due["year"], due["month"], due["day"], tzinfo=timezone.utc)
                if now <= dt <= week_end:
                    deadlines.append(f"- [Due: {due['year']}-{due['month']:02d}-{due['day']:02d}] {cw.get('title')} ({cname})")

    briefing = [f"WEEKLY BRIEFING ({now.date()} to {week_end.date()})"]
    briefing.append("\nCALENDAR EVENTS:")
    briefing.append(cal_summary)
    briefing.append("\nCLASSROOM DEADLINES:")
    if deadlines:
        briefing += deadlines
    else:
        briefing.append("No deadlines this week.")
        
    return "\n".join(briefing)
