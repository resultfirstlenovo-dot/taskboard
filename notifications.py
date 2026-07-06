"""
Notification business logic for TaskBoard: dedupe, per-user/global opt-out,
logging, and the actual trigger conditions for each notification type.

Shared by both app.py (instant assigned/updated emails) and
scheduler/run_notifications.py (daily reminder/overdue/summary emails run
via GitHub Actions) — both pass in their own Supabase client.

Every send attempt is recorded in notification_log with a unique
dedupe_key, so re-running the app or the scheduler never sends the same
email twice.
"""

from datetime import date, datetime, timedelta

from email_templates import (
    render_assigned_email,
    render_overdue_email,
    render_reminder_email,
    render_summary_email,
    render_updated_email,
)
from graph_mailer import GraphMailerError, send_mail


def _global_notifications_enabled(sb):
    rows = sb.table("app_settings").select("notifications_enabled").eq("id", 1).execute().data
    return bool(rows and rows[0]["notifications_enabled"])


def _member_by_name(sb, name):
    if not name:
        return None
    rows = sb.table("members").select("*").eq("name", name).execute().data
    return rows[0] if rows else None


def _can_notify(sb, member):
    if not member or not member.get("email"):
        return False
    if not member.get("notifications_enabled", True):
        return False
    return _global_notifications_enabled(sb)


def _reserve(sb, dedupe_key, task_id, member_name, notif_type, recipient_email):
    """Atomically claim this notification. Returns True if we own sending it
    (i.e. it wasn't already logged), False if it's a duplicate."""
    row = {
        "dedupe_key": dedupe_key,
        "task_id": task_id,
        "member_name": member_name,
        "notification_type": notif_type,
        "recipient_email": recipient_email,
        "status": "pending",
    }
    result = (
        sb.table("notification_log")
        .upsert(row, on_conflict="dedupe_key", ignore_duplicates=True)
        .execute()
    )
    return bool(result.data)


def _mark(sb, dedupe_key, status, error_message=None):
    sb.table("notification_log").update(
        {"status": status, "error_message": error_message}
    ).eq("dedupe_key", dedupe_key).execute()


def _dispatch(sb, dedupe_key, task_id, member, notif_type, subject, html_body):
    if not _can_notify(sb, member):
        return
    if not _reserve(sb, dedupe_key, task_id, member["name"], notif_type, member["email"]):
        return  # already sent — duplicate suppressed
    try:
        send_mail(member["email"], subject, html_body)
        _mark(sb, dedupe_key, "sent")
    except GraphMailerError as e:
        _mark(sb, dedupe_key, "failed", str(e))


# ----------------------------------------------------------------------------
# Instant notifications (called from app.py on task create/edit/drag-drop)
# ----------------------------------------------------------------------------

def notify_task_assigned(sb, task, project_name, member):
    if not member:
        return
    key = f"assigned:{task['id']}:{member['name']}:{date.today().isoformat()}"
    subject, html = render_assigned_email(task, project_name)
    _dispatch(sb, key, task["id"], member, "assigned", subject, html)


def notify_task_updated(sb, task, project_name, member, changes):
    if not member or not changes:
        return
    # Minute-bucketed key: collapses accidental duplicate reruns within the
    # same minute into a single email, without needing extra session state.
    minute_bucket = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    key = f"updated:{task['id']}:{minute_bucket}"
    subject, html = render_updated_email(task, project_name, changes)
    _dispatch(sb, key, task["id"], member, "updated", subject, html)


# ----------------------------------------------------------------------------
# Scheduled notifications (called once daily by scheduler/run_notifications.py)
# ----------------------------------------------------------------------------

def _projects_by_id(sb):
    return {p["id"]: p["name"] for p in sb.table("projects").select("id,name").execute().data or []}


def send_due_reminders(sb):
    """Email assignees whose task is due tomorrow (runs once/day -> ~24h notice)."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    tasks = (
        sb.table("tasks").select("*").eq("due_date", tomorrow).neq("status", "Done").execute().data
        or []
    )
    projects = _projects_by_id(sb)
    for t in tasks:
        member = _member_by_name(sb, t.get("assignee"))
        if not member:
            continue
        key = f"reminder24:{t['id']}:{tomorrow}"
        subject, html = render_reminder_email(t, projects.get(t["project_id"], "?"))
        _dispatch(sb, key, t["id"], member, "reminder_24h", subject, html)


def send_overdue_notifications(sb):
    """Email assignees of tasks whose due date has passed and aren't Done."""
    today = date.today().isoformat()
    tasks = (
        sb.table("tasks").select("*").lt("due_date", today).neq("status", "Done").execute().data
        or []
    )
    projects = _projects_by_id(sb)
    for t in tasks:
        member = _member_by_name(sb, t.get("assignee"))
        if not member:
            continue
        key = f"overdue:{t['id']}:{today}"
        subject, html = render_overdue_email(t, projects.get(t["project_id"], "?"))
        _dispatch(sb, key, t["id"], member, "overdue", subject, html)


def send_daily_summary(sb):
    """One digest per member listing their pending + overdue tasks."""
    today = date.today().isoformat()
    members = sb.table("members").select("*").execute().data or []
    projects = _projects_by_id(sb)
    all_open = sb.table("tasks").select("*").neq("status", "Done").execute().data or []

    for member in members:
        mine = [t for t in all_open if t.get("assignee") == member["name"]]
        if not mine:
            continue
        key = f"summary:{member['name']}:{today}"
        subject, html = render_summary_email(mine, projects)
        _dispatch(sb, key, None, member, "daily_summary", subject, html)
