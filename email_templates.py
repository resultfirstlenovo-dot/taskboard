"""HTML email templates for TaskBoard notifications."""

from datetime import date


def _wrap(heading, body_html):
    return f"""\
<html>
<body style="font-family: Arial, Helvetica, sans-serif; color:#31333f; line-height:1.5;">
  <h2 style="color:#ff4b4b; margin-bottom: 4px;">{heading}</h2>
  {body_html}
  <hr style="border:none;border-top:1px solid #d6d9de;margin:24px 0;">
  <p style="font-size:12px;color:#888;">
    Sent automatically by TaskBoard. You can turn these emails off in the
    app's Settings tab (Notifications section).
  </p>
</body>
</html>"""


def _task_block(task, project_name):
    due = task.get("due_date") or "No due date"
    desc = f"<p>{task['description']}</p>" if task.get("description") else ""
    return f"""\
<p>
  <b>Task:</b> {task['title']}<br>
  <b>Project:</b> {project_name}<br>
  <b>Status:</b> {task.get('status', '—')}<br>
  <b>Due:</b> {due}
</p>
{desc}"""


def render_assigned_email(task, project_name):
    subject = f"[TaskBoard] You've been assigned: {task['title']}"
    html = _wrap("New task assigned to you", _task_block(task, project_name))
    return subject, html


def render_updated_email(task, project_name, changes):
    subject = f"[TaskBoard] Task updated: {task['title']}"
    change_list = "".join(f"<li>{c}</li>" for c in changes)
    body = _task_block(task, project_name) + f"<p><b>What changed:</b></p><ul>{change_list}</ul>"
    html = _wrap("A task assigned to you was updated", body)
    return subject, html


def render_reminder_email(task, project_name):
    subject = f"[TaskBoard] Due tomorrow: {task['title']}"
    html = _wrap("Reminder — this task is due tomorrow", _task_block(task, project_name))
    return subject, html


def render_overdue_email(task, project_name):
    subject = f"[TaskBoard] Overdue: {task['title']}"
    html = _wrap("This task is now overdue", _task_block(task, project_name))
    return subject, html


def render_summary_email(tasks, projects_by_id):
    today_iso = date.today().isoformat()
    overdue = [t for t in tasks if t.get("due_date") and t["due_date"] < today_iso]
    pending = [t for t in tasks if t not in overdue]

    def rows(items):
        return "".join(
            f"<li>{t['title']} — {projects_by_id.get(t['project_id'], '?')} "
            f"(due {t.get('due_date') or 'none'})</li>"
            for t in items
        )

    body = ""
    if overdue:
        body += f"<h3>🔴 Overdue ({len(overdue)})</h3><ul>{rows(overdue)}</ul>"
    if pending:
        body += f"<h3>📋 Pending ({len(pending)})</h3><ul>{rows(pending)}</ul>"
    if not body:
        body = "<p>Nothing pending — you're all caught up!</p>"

    subject = f"[TaskBoard] Daily summary — {len(overdue)} overdue, {len(pending)} pending"
    html = _wrap("Your daily task summary", body)
    return subject, html
