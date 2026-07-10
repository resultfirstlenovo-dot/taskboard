"""
TaskBoard — Kanban project management for a coordinator + 7 team members.

- Admin (project coordinator): unlocks with password -> full add/edit/delete + drag & drop.
- Team members: open the link, pick their name -> read-only view of their tasks.
- Backend: Supabase (Postgres). Deployed on Streamlit Community Cloud.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from postgrest.exceptions import APIError
from streamlit_sortables import sort_items
from supabase import create_client

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

st.set_page_config(page_title="TaskBoard", page_icon="🗂️", layout="wide")

STATUSES = ["To Do", "In Progress", "Review", "Done"]
STATUS_ICONS = {"To Do": "📋", "In Progress": "🔨", "Review": "🔍", "Done": "✅"}

PRIORITIES = ["Urgent", "High", "Normal", "Low"]
PRIORITY_ICONS = {"Urgent": "🔴", "High": "🟠", "Normal": "🔵", "Low": "⚪"}

CATEGORIES = ["Research", "Tactical"]
CATEGORY_ICONS = {"Research": "🔬", "Tactical": "⚙️", "Uncategorized": "❔"}

DAY_HOURS = 8              # working day = 8 hours
DAY_START = "10:00"        # starting 10am
WORKWEEK = [0, 1, 2, 3, 4]  # Mon–Fri


def priority_of(t):
    p = t.get("priority") or "Normal"
    return p if p in PRIORITIES else "Normal"


def priority_rank(t):
    return PRIORITIES.index(priority_of(t))


def category_of(t):
    c = t.get("category")
    return c if c in CATEGORIES else "Uncategorized"

SORTABLE_CSS = """
.sortable-component {
    background-color: transparent;
    border: none;
    padding: 0;
}
.sortable-container {
    background-color: #f0f2f6;
    border: 1px solid #d6d9de;
    border-radius: 10px;
    padding: 8px;
    min-width: 240px;
}
.sortable-container-header {
    font-weight: 700;
    padding: 6px 8px;
    color: #31333f;
}
.sortable-item {
    background-color: #ffffff;
    color: #31333f;
    border: 1px solid #d6d9de;
    border-radius: 8px;
    padding: 10px;
    margin: 6px 4px;
    font-size: 0.85rem;
    line-height: 1.5;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.sortable-item:hover { border-color: #ff4b4b; }
"""


# ----------------------------------------------------------------------------
# Supabase helpers
# ----------------------------------------------------------------------------

@st.cache_resource
def get_client():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Supabase credentials are missing. Add them in "
            "**Streamlit Cloud → App → Settings → Secrets** (see README):\n\n"
            "```toml\n[supabase]\nurl = \"https://xxxx.supabase.co\"\n"
            "key = \"your-anon-key\"\n\n[app]\nadmin_password = \"choose-a-password\"\n```"
        )
        st.stop()
    return create_client(url, key)


sb = get_client()


def _db_error(action, table, e):
    st.error(
        f"Database error while {action} **{table}**: {e.message or e}\n\n"
        "If this mentions a missing column or table, ask your coordinator to "
        "re-run the latest `schema.sql` in Supabase's SQL Editor — it's safe "
        "to run again without touching existing data."
    )
    st.stop()


def fetch(table, **filters):
    q = sb.table(table).select("*")
    for col, val in filters.items():
        q = q.eq(col, val)
    try:
        return q.execute().data or []
    except APIError as e:
        _db_error("reading", table, e)


def insert(table, row):
    try:
        return sb.table(table).insert(row).execute().data
    except APIError as e:
        _db_error("saving to", table, e)


def update_row(table, row_id, changes):
    try:
        sb.table(table).update(changes).eq("id", row_id).execute()
    except APIError as e:
        _db_error("updating", table, e)


def delete_row(table, row_id):
    try:
        sb.table(table).delete().eq("id", row_id).execute()
    except APIError as e:
        _db_error("deleting from", table, e)


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------

def get_passwords():
    try:
        return st.secrets["app"]["admin_password"], st.secrets["app"]["viewer_password"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Passwords missing from secrets. Add to **Streamlit Cloud → App → "
            "Settings → Secrets**:\n\n```toml\n[app]\nadmin_password = \"...\"\n"
            "viewer_password = \"...\"\n```"
        )
        st.stop()


def role():
    return st.session_state.get("role")  # None | "viewer" | "admin"


def is_admin() -> bool:
    return role() == "admin"


def login_gate():
    """Block the whole app until a viewer or admin password is entered."""
    if role() in ("viewer", "admin"):
        return
    admin_pwd, viewer_pwd = get_passwords()
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.title("🗂️ TaskBoard")
        st.caption("Enter the team password to view the board. The coordinator password unlocks editing.")
        with st.form("login"):
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Enter", width="stretch"):
                if pwd == admin_pwd:
                    st.session_state["role"] = "admin"
                    st.rerun()
                elif pwd == viewer_pwd:
                    st.session_state["role"] = "viewer"
                    st.rerun()
                else:
                    st.error("Wrong password")
    st.stop()


def auth_sidebar():
    with st.sidebar:
        st.title("🗂️ TaskBoard")
        if is_admin():
            st.success("Coordinator mode — full access")
        else:
            st.info("Viewer mode — read-only")
            with st.expander("🔑 Switch to coordinator"):
                admin_pwd, _ = get_passwords()
                pwd = st.text_input("Coordinator password", type="password", key="pwd_input")
                if st.button("Unlock", width="stretch"):
                    if pwd == admin_pwd:
                        st.session_state["role"] = "admin"
                        st.rerun()
                    else:
                        st.error("Wrong password")
        if st.button("Log out", width="stretch"):
            st.session_state["role"] = None
            st.rerun()


# ----------------------------------------------------------------------------
# Data shaping
# ----------------------------------------------------------------------------

def parse_date(s):
    if not s:
        return None
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def due_label(d):
    if not d:
        return ""
    today = date.today()
    if d < today:
        return f"🔴 {d.strftime('%d %b')} (overdue)"
    if d == today:
        return f"🟠 {d.strftime('%d %b')} (today)"
    if d <= today + timedelta(days=7):
        return f"🟡 {d.strftime('%d %b')}"
    return f"📅 {d.strftime('%d %b')}"


def task_card_label(t, subtasks_by_task):
    parts = [f"#{t['id']}  {PRIORITY_ICONS[priority_of(t)]} {t['title']}"]
    meta = []
    if t.get("assignee"):
        meta.append(f"👤 {t['assignee']}")
    d = parse_date(t.get("due_date"))
    if d:
        meta.append(due_label(d))
    hrs = float(t.get("estimated_hours") or 0)
    if hrs > 0:
        meta.append(f"⏱ {hrs:g}h")
    cat = category_of(t)
    if cat != "Uncategorized":
        meta.append(f"{CATEGORY_ICONS[cat]} {cat}")
    subs = subtasks_by_task.get(t["id"], [])
    if subs:
        done = sum(1 for s in subs if subtask_status(s) == "Done")
        meta.append(f"☑ {done}/{len(subs)}")
    if meta:
        parts.append(" · ".join(meta))
    return "\n".join(parts)


def label_to_task_id(label):
    # label starts with "#<id>  "
    try:
        return int(label.split()[0].lstrip("#"))
    except (ValueError, IndexError):
        return None


def load_all_data():
    """One round trip for all tasks + subtasks, reused by every tab this run
    instead of each view re-querying (previously up to ~15+ queries per
    rerun with several projects; now a flat 2)."""
    tasks = fetch("tasks")
    task_ids = [t["id"] for t in tasks]
    subs = []
    if task_ids:
        try:
            subs = sb.table("subtasks").select("*").in_("task_id", task_ids).execute().data or []
        except APIError as e:
            _db_error("reading", "subtasks", e)
    subs_by_task = {}
    for s in sorted(subs, key=lambda s: s["id"]):
        subs_by_task.setdefault(s["task_id"], []).append(s)
    return tasks, subs_by_task


def project_tasks(project_id, all_tasks):
    tasks = [t for t in all_tasks if t["project_id"] == project_id]
    tasks.sort(key=lambda t: (t.get("position") or 0, t["id"]))
    return tasks


def subtask_status(s):
    st_ = s.get("status") or "To Do"
    return st_ if st_ in STATUSES else "To Do"


def sync_parent_status(task_id):
    """Completing every subtask auto-completes the parent; un-completing one
    while the parent is Done reopens it. No-ops when there are no subtasks —
    manual status control is untouched for tasks without a checklist."""
    subs = fetch("subtasks", task_id=task_id)
    if not subs:
        return
    all_done = all(subtask_status(s) == "Done" for s in subs)
    task_rows = fetch("tasks", id=task_id)
    if not task_rows:
        return
    task = task_rows[0]
    if all_done and task["status"] != "Done":
        update_row("tasks", task_id, {"status": "Done"})
    elif not all_done and task["status"] == "Done":
        update_row("tasks", task_id, {"status": "In Progress"})


# ----------------------------------------------------------------------------
# Alerts banner
# ----------------------------------------------------------------------------

def render_alerts(projects, all_tasks):
    """Red-flag section at the very top: overdue, due today, and urgent tasks."""
    proj_by_id = {p["id"]: p["name"] for p in projects}
    open_tasks = [t for t in all_tasks if t["status"] != "Done"]
    today = date.today()

    overdue, due_today, urgent = [], [], []
    for t in open_tasks:
        d = parse_date(t.get("due_date"))
        if d and d < today:
            overdue.append(t)
        elif d and d == today:
            due_today.append(t)
        elif priority_of(t) == "Urgent":
            urgent.append(t)  # urgent but not already listed above

    def line(t):
        d = parse_date(t.get("due_date"))
        bits = [
            f"**{t['title']}**",
            f"📁 {proj_by_id.get(t['project_id'], '?')}",
            f"👤 {t.get('assignee') or 'Unassigned'}",
            f"{PRIORITY_ICONS[priority_of(t)]} {priority_of(t)}",
        ]
        if d:
            bits.append(f"📅 {d.strftime('%d %b')}")
        return " · ".join(bits)

    n = len(overdue) + len(due_today) + len(urgent)
    if n == 0:
        st.success("✅ No overdue, due-today, or urgent items right now.")
        return

    with st.container(border=True):
        st.markdown(f"### 🚨 Alerts — {n} item{'s' if n != 1 else ''} need attention")
        for t in sorted(overdue, key=lambda t: (t.get("due_date") or "", priority_rank(t))):
            st.error(f"⏰ OVERDUE — {line(t)}")
        for t in sorted(due_today, key=priority_rank):
            st.warning(f"📌 DUE TODAY — {line(t)}")
        for t in sorted(urgent, key=lambda t: t.get("due_date") or "9999"):
            st.warning(f"🔴 URGENT — {line(t)}")


# ----------------------------------------------------------------------------
# Vertical list view (Asana-style)
# ----------------------------------------------------------------------------

def render_subtask_summary(subs):
    """Read-only progress bar + per-subtask detail line, used in List/Kanban."""
    done = sum(1 for s in subs if subtask_status(s) == "Done")
    with st.expander(f"☑ Subtasks {done}/{len(subs)}"):
        st.progress(done / len(subs))
        for s in subs:
            status = subtask_status(s)
            bits = [STATUS_ICONS.get(status, ""), f"**{s['title']}**"]
            if s.get("assignee"):
                bits.append(f"👤 {s['assignee']}")
            prio = s.get("priority") or "Normal"
            bits.append(f"{PRIORITY_ICONS.get(prio, '')} {prio}")
            d = parse_date(s.get("due_date"))
            if d:
                bits.append(due_label(d))
            st.caption(" · ".join(bits))
            if s.get("notes"):
                st.caption(f"📝 {s['notes']}")


def render_list(project, all_tasks, subs_by_task):
    tasks = project_tasks(project["id"], all_tasks)
    if not tasks:
        st.info("No tasks here yet.")
        return

    for status in STATUSES:
        group = [t for t in tasks if t["status"] == status]
        if not group:
            continue
        group.sort(key=lambda t: (priority_rank(t), t.get("due_date") or "9999", t["id"]))
        st.markdown(f"#### {STATUS_ICONS[status]} {status} ({len(group)})")
        for t in group:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([5, 2, 2, 2])
                with c1:
                    st.markdown(f"**{t['title']}**")
                    if t.get("description"):
                        st.caption(t["description"])
                    subs = subs_by_task.get(t["id"], [])
                    if subs:
                        render_subtask_summary(subs)
                with c2:
                    p = priority_of(t)
                    st.markdown(f"{PRIORITY_ICONS[p]} {p}")
                    bits = []
                    hrs = float(t.get("estimated_hours") or 0)
                    if hrs > 0:
                        bits.append(f"⏱ {hrs:g}h")
                    cat = category_of(t)
                    if cat != "Uncategorized":
                        bits.append(f"{CATEGORY_ICONS[cat]} {cat}")
                    if bits:
                        st.caption(" · ".join(bits))
                with c3:
                    st.markdown(f"👤 {t.get('assignee') or '—'}")
                with c4:
                    d = parse_date(t.get("due_date"))
                    st.markdown(due_label(d) if d else "📅 —")
        st.write("")


# ----------------------------------------------------------------------------
# Kanban board
# ----------------------------------------------------------------------------

def render_kanban(project, all_tasks, subs_by_task):
    tasks = project_tasks(project["id"], all_tasks)

    if not tasks:
        st.info("No tasks here yet.")
        return

    if is_admin():
        # Drag & drop board
        containers = [
            {
                "header": f"{STATUS_ICONS[s]} {s}",
                "items": [
                    task_card_label(t, subs_by_task) for t in tasks if t["status"] == s
                ],
            }
            for s in STATUSES
        ]
        result = sort_items(
            containers,
            multi_containers=True,
            direction="horizontal",
            custom_style=SORTABLE_CSS,
            key=f"board_{project['id']}",
        )
        # Detect moves: compare resulting containers with DB state
        changed = False
        for idx, container in enumerate(result):
            status = STATUSES[idx]
            for pos, label in enumerate(container["items"]):
                tid = label_to_task_id(label)
                if tid is None:
                    continue
                current = next((t for t in tasks if t["id"] == tid), None)
                if current and (current["status"] != status or (current.get("position") or 0) != pos):
                    update_row("tasks", tid, {"status": status, "position": pos})
                    changed = True
        if changed:
            st.rerun()
        st.caption("Drag cards between columns to update status. Changes save automatically.")
    else:
        # Read-only board
        cols = st.columns(len(STATUSES))
        for col, status in zip(cols, STATUSES):
            with col:
                st.markdown(f"**{STATUS_ICONS[status]} {status}**")
                for t in [t for t in tasks if t["status"] == status]:
                    with st.container(border=True):
                        st.markdown(f"**{t['title']}**")
                        meta = [f"{PRIORITY_ICONS[priority_of(t)]} {priority_of(t)}"]
                        if t.get("assignee"):
                            meta.append(f"👤 {t['assignee']}")
                        d = parse_date(t.get("due_date"))
                        if d:
                            meta.append(due_label(d))
                        if meta:
                            st.caption(" · ".join(meta))
                        if t.get("description"):
                            st.caption(t["description"])
                        subs = subs_by_task.get(t["id"], [])
                        if subs:
                            render_subtask_summary(subs)


# ----------------------------------------------------------------------------
# Admin: manage projects / tasks / subtasks / members
# ----------------------------------------------------------------------------

def admin_task_manager(project, members, all_tasks, subs_by_task):
    tasks = project_tasks(project["id"], all_tasks)
    member_names = [m["name"] for m in members]

    st.divider()
    left, right = st.columns(2)

    # ---- Add task ----
    with left:
        st.subheader("➕ Add task")
        with st.form(f"add_task_{project['id']}", clear_on_submit=True):
            title = st.text_input("Title *")
            description = st.text_area("Description", height=80)
            c1, c2, c3 = st.columns(3)
            assignee = c1.selectbox("Assign to", ["—"] + member_names)
            start = c2.date_input("Start date", value=None)
            due = c3.date_input("Due date", value=None)
            c4, c5, c6, c7 = st.columns(4)
            status = c4.selectbox("Status", STATUSES)
            prio = c5.selectbox("Priority", PRIORITIES, index=2)
            hours = c6.number_input("Est. hours", min_value=0.0, max_value=500.0, step=0.5, value=0.0)
            cat = c7.selectbox("Category", CATEGORIES, index=1)
            if st.form_submit_button("Add task", width="stretch"):
                if not title.strip():
                    st.error("Title is required.")
                else:
                    new_assignee = None if assignee == "—" else assignee
                    insert("tasks", {
                        "project_id": project["id"],
                        "title": title.strip(),
                        "description": description.strip() or None,
                        "assignee": new_assignee,
                        "start_date": start.isoformat() if start else None,
                        "due_date": due.isoformat() if due else None,
                        "status": status,
                        "priority": prio,
                        "estimated_hours": hours,
                        "category": cat,
                        "position": len(tasks),
                    })
                    st.rerun()

    # ---- Edit / delete task ----
    with right:
        st.subheader("✏️ Edit / delete task")
        if not tasks:
            st.caption("No tasks yet.")
            return
        options = {f"#{t['id']} — {t['title']}": t for t in tasks}
        picked = st.selectbox("Select task", list(options.keys()), key=f"edit_pick_{project['id']}")
        t = options[picked]

        with st.form(f"edit_task_{t['id']}"):
            title = st.text_input("Title", value=t["title"])
            description = st.text_area("Description", value=t.get("description") or "", height=80)
            c1, c2, c3 = st.columns(3)
            current_assignee = t.get("assignee")
            assignee_opts = ["—"] + member_names
            a_idx = assignee_opts.index(current_assignee) if current_assignee in assignee_opts else 0
            assignee = c1.selectbox("Assign to", assignee_opts, index=a_idx)
            start = c2.date_input("Start date", value=parse_date(t.get("start_date")))
            due = c3.date_input("Due date", value=parse_date(t.get("due_date")))
            c4, c5, c6, c7 = st.columns(4)
            status = c4.selectbox("Status", STATUSES, index=STATUSES.index(t["status"]) if t["status"] in STATUSES else 0)
            prio = c5.selectbox("Priority", PRIORITIES, index=priority_rank(t))
            hours = c6.number_input("Est. hours", min_value=0.0, max_value=500.0, step=0.5,
                                    value=float(t.get("estimated_hours") or 0))
            cur_cat = category_of(t)
            cat = c7.selectbox("Category", CATEGORIES,
                               index=CATEGORIES.index(cur_cat) if cur_cat in CATEGORIES else 1)
            b1, b2 = st.columns(2)
            if b1.form_submit_button("Save changes", width="stretch"):
                update_row("tasks", t["id"], {
                    "title": title.strip(),
                    "description": description.strip() or None,
                    "assignee": None if assignee == "—" else assignee,
                    "start_date": start.isoformat() if start else None,
                    "due_date": due.isoformat() if due else None,
                    "status": status,
                    "priority": prio,
                    "estimated_hours": hours,
                    "category": cat,
                })
                st.rerun()
            if b2.form_submit_button("🗑 Delete task", width="stretch"):
                delete_row("tasks", t["id"])
                st.rerun()

        # ---- Subtasks ----
        subs = subs_by_task.get(t["id"], [])
        st.markdown(f"**Subtasks of #{t['id']}**")
        if subs:
            done = sum(1 for s in subs if subtask_status(s) == "Done")
            st.progress(done / len(subs), text=f"{done}/{len(subs)} subtasks complete")

        for s in subs:
            icon = "✅" if subtask_status(s) == "Done" else STATUS_ICONS.get(subtask_status(s), "⬜")
            with st.expander(f"{icon} {s['title']} — {s.get('assignee') or 'Unassigned'}"):
                with st.form(f"sub_edit_{s['id']}"):
                    s_title = st.text_input("Title", value=s["title"])
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    s_assignee_opts = ["—"] + member_names
                    s_current = s.get("assignee")
                    s_a_idx = s_assignee_opts.index(s_current) if s_current in s_assignee_opts else 0
                    s_assignee = sc1.selectbox("Assignee", s_assignee_opts, index=s_a_idx, key=f"sub_a_{s['id']}")
                    s_status = sc2.selectbox("Status", STATUSES, index=STATUSES.index(subtask_status(s)), key=f"sub_s_{s['id']}")
                    s_priority = sc3.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(s.get("priority") or "Normal") if (s.get("priority") or "Normal") in PRIORITIES else 2, key=f"sub_p_{s['id']}")
                    s_due = sc4.date_input("Due date", value=parse_date(s.get("due_date")), key=f"sub_d_{s['id']}")
                    s_notes = st.text_area("Notes (optional)", value=s.get("notes") or "", key=f"sub_n_{s['id']}", height=68)
                    sb1, sb2 = st.columns(2)
                    if sb1.form_submit_button("Save subtask", width="stretch"):
                        update_row("subtasks", s["id"], {
                            "title": s_title.strip(),
                            "assignee": None if s_assignee == "—" else s_assignee,
                            "status": s_status,
                            "priority": s_priority,
                            "due_date": s_due.isoformat() if s_due else None,
                            "notes": s_notes.strip() or None,
                        })
                        sync_parent_status(t["id"])
                        st.rerun()
                    if sb2.form_submit_button("🗑 Delete subtask", width="stretch"):
                        delete_row("subtasks", s["id"])
                        sync_parent_status(t["id"])
                        st.rerun()

        with st.expander("➕ Add subtask"):
            with st.form(f"add_sub_{t['id']}", clear_on_submit=True):
                ns_title = st.text_input("Title")
                nc1, nc2, nc3, nc4 = st.columns(4)
                ns_assignee = nc1.selectbox("Assignee", ["—"] + member_names, key=f"new_sub_a_{t['id']}")
                ns_status = nc2.selectbox("Status", STATUSES, key=f"new_sub_s_{t['id']}")
                ns_priority = nc3.selectbox("Priority", PRIORITIES, index=2, key=f"new_sub_p_{t['id']}")
                ns_due = nc4.date_input("Due date", value=None, key=f"new_sub_d_{t['id']}")
                ns_notes = st.text_area("Notes (optional)", key=f"new_sub_n_{t['id']}", height=68)
                if st.form_submit_button("Add subtask", width="stretch"):
                    if ns_title.strip():
                        insert("subtasks", {
                            "task_id": t["id"],
                            "title": ns_title.strip(),
                            "assignee": None if ns_assignee == "—" else ns_assignee,
                            "status": ns_status,
                            "priority": ns_priority,
                            "due_date": ns_due.isoformat() if ns_due else None,
                            "notes": ns_notes.strip() or None,
                        })
                        sync_parent_status(t["id"])
                        st.rerun()


def admin_settings(projects, members):
    st.subheader("📁 Projects")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("add_project", clear_on_submit=True):
            name = st.text_input("New project name")
            if st.form_submit_button("Create project"):
                if name.strip():
                    insert("projects", {"name": name.strip()})
                    st.rerun()
    with c2:
        if projects:
            doomed = st.selectbox("Delete project (and all its tasks)", ["—"] + [p["name"] for p in projects])
            if st.button("Delete project") and doomed != "—":
                pid = next(p["id"] for p in projects if p["name"] == doomed)
                delete_row("projects", pid)
                st.rerun()

    st.divider()
    st.subheader("👥 Team members")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("add_member", clear_on_submit=True):
            name = st.text_input("New member name")
            if st.form_submit_button("Add member"):
                if name.strip():
                    insert("members", {"name": name.strip()})
                    st.rerun()
    with c2:
        if members:
            doomed = st.selectbox("Remove member", ["—"] + [m["name"] for m in members])
            if st.button("Remove member") and doomed != "—":
                mid = next(m["id"] for m in members if m["name"] == doomed)
                delete_row("members", mid)
                st.rerun()

    st.divider()
    st.subheader("🏖 Off days")
    st.caption("Marked days count as zero capacity in the bandwidth/capacity views.")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("add_off", clear_on_submit=True):
            who = st.selectbox("Member", [m["name"] for m in members] or ["—"])
            d1, d2 = st.columns(2)
            from_d = d1.date_input("From", value=date.today())
            to_d = d2.date_input("To", value=date.today())
            reason = st.text_input("Reason (optional)", placeholder="Vacation, sick leave…")
            if st.form_submit_button("Mark off days", width="stretch"):
                if who != "—" and from_d and to_d and from_d <= to_d:
                    existing = {(o["member_name"], o["off_date"][:10]) for o in fetch("time_off")}
                    new_rows, d = [], from_d
                    while d <= to_d:
                        if (who, d.isoformat()) not in existing:
                            new_rows.append({"member_name": who, "off_date": d.isoformat(),
                                             "reason": reason.strip() or None})
                        d += timedelta(days=1)
                    if new_rows:
                        insert("time_off", new_rows)
                    st.rerun()
                else:
                    st.error("Check member and date range.")
    with c2:
        offs = sorted(fetch("time_off"), key=lambda o: (o["off_date"], o["member_name"]))
        recent = [o for o in offs if parse_date(o["off_date"]) >= date.today() - timedelta(days=7)]
        if not recent:
            st.caption("No upcoming off days.")
        for o in recent:
            cc1, cc2 = st.columns([5, 1])
            d = parse_date(o["off_date"])
            reason = f" — {o['reason']}" if o.get("reason") else ""
            cc1.markdown(f"🏖 **{o['member_name']}** · {d.strftime('%a %d %b %Y')}{reason}")
            if cc2.button("🗑", key=f"del_off_{o['id']}"):
                delete_row("time_off", o["id"])
                st.rerun()


# ----------------------------------------------------------------------------
# Deliveries dashboard
# ----------------------------------------------------------------------------

def render_deliveries(projects, members, all_tasks):
    st.subheader("🚚 Deliveries by due date")
    proj_by_id = {p["id"]: p["name"] for p in projects}

    c1, c2, c3 = st.columns(3)
    member_names = ["All members"] + [m["name"] for m in members]
    who = c1.selectbox("Team member", member_names)
    proj_names = ["All projects"] + [p["name"] for p in projects]
    proj = c2.selectbox("Project", proj_names)
    hide_done = c3.toggle("Hide completed", value=True)

    rows = []
    for t in all_tasks:
        if who != "All members" and t.get("assignee") != who:
            continue
        if proj != "All projects" and proj_by_id.get(t["project_id"]) != proj:
            continue
        if hide_done and t["status"] == "Done":
            continue
        rows.append(t)

    today = date.today()
    buckets = {"🔴 Overdue": [], "🟠 Due today": [], "🟡 This week": [], "📅 Later": [], "⚪ No due date": []}
    for t in rows:
        d = parse_date(t.get("due_date"))
        if d is None:
            buckets["⚪ No due date"].append(t)
        elif d < today:
            buckets["🔴 Overdue"].append(t)
        elif d == today:
            buckets["🟠 Due today"].append(t)
        elif d <= today + timedelta(days=7):
            buckets["🟡 This week"].append(t)
        else:
            buckets["📅 Later"].append(t)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overdue", len(buckets["🔴 Overdue"]))
    m2.metric("Due today", len(buckets["🟠 Due today"]))
    m3.metric("This week", len(buckets["🟡 This week"]))
    m4.metric("Open tasks", len(rows))

    for bucket, items in buckets.items():
        if not items:
            continue
        st.markdown(f"### {bucket} ({len(items)})")
        items.sort(key=lambda t: (t.get("due_date") or "9999", priority_rank(t), t["id"]))
        table = [{
            "Priority": f"{PRIORITY_ICONS[priority_of(t)]} {priority_of(t)}",
            "Task": t["title"],
            "Project": proj_by_id.get(t["project_id"], "?"),
            "Assignee": t.get("assignee") or "—",
            "Due": t.get("due_date") or "—",
            "Hours": f"{float(t.get('estimated_hours') or 0):g}h",
            "Category": f"{CATEGORY_ICONS[category_of(t)]} {category_of(t)}",
            "Status": f"{STATUS_ICONS.get(t['status'], '')} {t['status']}",
        } for t in items]
        st.dataframe(table, width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# Gantt & bandwidth
# ----------------------------------------------------------------------------

def working_days_between(d1, d2):
    days, d = [], d1
    while d <= d2:
        if d.weekday() in WORKWEEK:
            days.append(d)
        d += timedelta(days=1)
    return days


def get_off_days():
    """{member_name: set of dates}. Off-days are supplementary — if the
    time_off table isn't there yet (pending migration), degrade to "nobody's
    off" instead of blocking the whole app via fetch()'s stop-on-error."""
    try:
        rows = sb.table("time_off").select("*").execute().data or []
    except APIError:
        return {}
    out = {}
    for o in rows:
        d = parse_date(o["off_date"])
        if d:
            out.setdefault(o["member_name"], set()).add(d)
    return out


def task_window(t):
    """(start, end) dates for scheduling, or None."""
    s = parse_date(t.get("start_date"))
    e = parse_date(t.get("due_date"))
    if s is None and e is None:
        return None
    s = s or e
    e = e or s
    return (min(s, e), max(s, e))


def compute_allocation(tasks, off_by_member):
    """Spread each open task's estimated hours evenly over its working days
    (skipping weekends and the assignee's off days).
    Returns {(member, date): hours}."""
    alloc = {}
    for t in tasks:
        if t["status"] == "Done":
            continue
        who = t.get("assignee")
        hrs = float(t.get("estimated_hours") or 0)
        win = task_window(t)
        if not who or hrs <= 0 or win is None:
            continue
        days = [d for d in working_days_between(*win) if d not in off_by_member.get(who, set())]
        if not days:
            days = [win[0]]  # everything lands on the start day (member is off/weekend)
        per = hrs / len(days)
        for d in days:
            alloc[(who, d)] = alloc.get((who, d), 0.0) + per
    return alloc


def render_bandwidth(projects, members, all_tasks, off_by_member):
    st.subheader("📊 Gantt & team bandwidth")
    st.caption(f"Working day = {DAY_HOURS}h starting {DAY_START}, Mon–Fri. "
               "Task hours are spread evenly across each task's start→due working days. "
               "Done tasks are excluded.")

    proj_by_id = {p["id"]: p["name"] for p in projects}

    c1, c2, c3 = st.columns([2, 2, 2])
    mode = c1.radio("Zoom", ["Daily", "Weekly"], horizontal=True)
    ref = c2.date_input("Date", value=date.today(),
                        help="Daily = this exact day. Weekly = the Mon–Fri week containing this day.")
    proj_pick = c3.selectbox("Project filter", ["All projects"] + [p["name"] for p in projects])

    if mode == "Daily":
        win_start = win_end = ref
    else:
        win_start = ref - timedelta(days=ref.weekday())        # Monday
        win_end = win_start + timedelta(days=4)                # Friday

    tasks = [t for t in all_tasks if t["status"] != "Done"]
    if proj_pick != "All projects":
        tasks = [t for t in tasks if proj_by_id.get(t["project_id"]) == proj_pick]

    # ---------------- Gantt ----------------
    rows = []
    for t in tasks:
        win = task_window(t)
        if win is None:
            continue
        s, e = win
        if s > win_end or e < win_start:   # outside the viewed window
            continue
        rows.append({
            "Task": t["title"],
            "Member": t.get("assignee") or "Unassigned",
            "Project": proj_by_id.get(t["project_id"], "?"),
            "Start": datetime.combine(s, datetime.min.time()),
            "Finish": datetime.combine(e + timedelta(days=1), datetime.min.time()),
            "Hours": float(t.get("estimated_hours") or 0),
            "Priority": priority_of(t),
            "Due": e.strftime("%d %b"),
        })

    if rows:
        df = pd.DataFrame(rows).sort_values(["Member", "Start"])
        fig = px.timeline(
            df, x_start="Start", x_end="Finish", y="Member", color="Project",
            text="Task", hover_data={"Hours": True, "Priority": True, "Due": True,
                                     "Start": False, "Finish": False},
        )
        fig.update_yaxes(autorange="reversed", title="")
        fig.update_traces(textposition="inside", insidetextanchor="start")
        fig.add_vline(x=datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=12),
                      line_dash="dash", line_color="red")
        fig.update_layout(height=max(260, 90 + 45 * df["Member"].nunique()),
                          margin=dict(l=10, r=10, t=30, b=10),
                          legend_title_text="")
        fig.update_xaxes(range=[datetime.combine(win_start, datetime.min.time()),
                                datetime.combine(win_end + timedelta(days=1), datetime.min.time())])
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No scheduled tasks (with a start or due date) in this window.")

    # ---------------- Bandwidth table ----------------
    st.markdown(f"#### 🔋 Bandwidth — {'day' if mode == 'Daily' else 'week'} of {win_start.strftime('%d %b %Y')}")
    alloc = compute_allocation(tasks if proj_pick != "All projects" else all_tasks, off_by_member)
    days = [win_start + timedelta(days=i) for i in range((win_end - win_start).days + 1)]

    table = []
    for m in members:
        name = m["name"]
        row = {"Member": name}
        total_free = 0.0
        for d in days:
            col = d.strftime("%a %d %b")
            if d in off_by_member.get(name, set()):
                row[col] = "🏖 Off"
            elif d.weekday() not in WORKWEEK:
                row[col] = "— weekend"
            else:
                used = alloc.get((name, d), 0.0)
                free = DAY_HOURS - used
                total_free += max(free, 0)
                if used == 0:
                    row[col] = f"🟢 {DAY_HOURS:g}h free"
                elif free >= 0:
                    row[col] = f"{used:.1f}h used · {free:.1f}h free"
                else:
                    row[col] = f"🔴 {used:.1f}h — overbooked {-free:.1f}h"
        if mode == "Weekly":
            row["Total free"] = f"{total_free:.1f}h"
        table.append(row)

    if table:
        st.dataframe(table, width="stretch", hide_index=True)
    else:
        st.info("No team members configured.")


# ----------------------------------------------------------------------------
# Capacity grid (Excel-style hour tracker)
# ----------------------------------------------------------------------------

CAT_CELL_STYLE = {
    "Research":      "background:#3D5A80;color:#ffffff;",
    "Tactical":      "background:#E9C46A;color:#412402;",
    "Uncategorized": "background:#d7d7d7;color:#2c2c2a;",
}


def task_day_allocation(tasks, off_by_member):
    """{(member, date): [(task, hours), ...]} — per-task share of each working day."""
    out = {}
    for t in tasks:
        who = t.get("assignee")
        hrs = float(t.get("estimated_hours") or 0)
        win = task_window(t)
        if not who or hrs <= 0 or win is None:
            continue
        days = [d for d in working_days_between(*win)
                if d not in off_by_member.get(who, set())]
        if not days:
            days = [win[0]]
        per = hrs / len(days)
        for d in days:
            out.setdefault((who, d), []).append((t, per))
    return out


def render_capacity_grid(projects, members, all_tasks, off_by_member):
    import html as _html

    st.subheader("🗓 Capacity tracker")
    st.caption("Rows = combined team hours for the day; columns = weekdays; each cell ≈ 1 hour "
               "of a task, colored by category. The line marks that day's capacity "
               f"({DAY_HOURS}h × members on duty, from {DAY_START}). Rows below the line = over capacity.")

    proj_by_id = {p["id"]: p["name"] for p in projects}
    c1, c2, c3 = st.columns(3)
    ref = c1.date_input("Week of", value=date.today(), key="cap_week")
    member_names = [m["name"] for m in members]
    who_pick = c2.selectbox("Team member", ["Whole team"] + member_names, key="cap_member")
    proj_pick = c3.selectbox("Project", ["All projects"] + [p["name"] for p in projects], key="cap_proj")

    week_start = ref - timedelta(days=ref.weekday())
    days = [week_start + timedelta(days=i) for i in range(5)]   # Mon–Fri

    tasks = all_tasks
    if proj_pick != "All projects":
        tasks = [t for t in tasks if proj_by_id.get(t["project_id"]) == proj_pick]
    alloc = task_day_allocation(tasks, off_by_member)

    roster = member_names if who_pick == "Whole team" else [who_pick]

    # Build the stack of 1-hour cells for each day
    day_cells, day_capacity = {}, {}
    for d in days:
        cells = []
        cap = 0
        for name in roster:
            if d.weekday() in WORKWEEK and d not in off_by_member.get(name, set()):
                cap += DAY_HOURS
            for t, h in alloc.get((name, d), []):
                n = int(round(h))
                if n <= 0 and h >= 0.5:
                    n = 1
                for _ in range(n):
                    cells.append((t, name))
        day_cells[d], day_capacity[d] = cells, cap

    n_rows = max([max(len(day_cells[d]), day_capacity[d]) for d in days] + [DAY_HOURS])

    # Legend
    st.markdown(
        "<div style='display:flex;gap:16px;font-size:0.85rem;margin:4px 0 8px'>"
        "<span><span style='display:inline-block;width:14px;height:14px;background:#3D5A80;"
        "vertical-align:-2px'></span> Research</span>"
        "<span><span style='display:inline-block;width:14px;height:14px;background:#E9C46A;"
        "vertical-align:-2px'></span> Tactical</span>"
        "<span><span style='display:inline-block;width:14px;height:14px;background:#d7d7d7;"
        "vertical-align:-2px'></span> Uncategorized</span>"
        "<span><span style='display:inline-block;width:14px;height:14px;border:2px solid #E24B4A;"
        "vertical-align:-2px'></span> Over capacity</span></div>",
        unsafe_allow_html=True,
    )

    # Table
    head = "".join(
        f"<th style='background:#2c2c2a;color:#fff;padding:8px;font-size:0.85rem'>"
        f"{d.strftime('%a %d %b')}"
        + (f"<br><span style='font-weight:400;font-size:0.75rem'>cap {day_capacity[d]}h</span>")
        + "</th>"
        for d in days
    )
    rows_html = []
    for i in range(n_rows):
        tds = []
        for d in days:
            cells = day_cells[d]
            over = i >= day_capacity[d]
            base = "padding:6px 8px;font-size:0.78rem;border:1px solid #ffffff;max-width:130px;" \
                   "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            if i < len(cells):
                t, name = cells[i]
                style = base + CAT_CELL_STYLE[category_of(t)]
                if over:
                    style += "outline:2px solid #E24B4A;outline-offset:-2px;"
                label = f"#{t['id']} {_html.escape(t['title'])}"
                if t["status"] == "Done":
                    label = "✓ " + label
                tip = _html.escape(
                    f"{t['title']} — {name} · {proj_by_id.get(t['project_id'], '?')} · "
                    f"{category_of(t)} · {t['status']}"
                )
                tds.append(f"<td style='{style}' title='{tip}'>{label}</td>")
            else:
                style = base + "background:transparent;border:1px solid #e6e6e6;"
                if over:
                    style += "background:#fcebeb33;"
                tds.append(f"<td style='{style}'></td>")
        hour_label_style = "padding:6px 10px;font-size:0.78rem;color:#5f5e5a;background:#f1efe8;" \
                           "border:1px solid #fff;white-space:nowrap;"
        rows_html.append(
            f"<tr><td style='{hour_label_style}'>Hour {i + 1}</td>{''.join(tds)}</tr>"
        )
        # capacity divider after the max capacity row
        if i + 1 == max(day_capacity.values() or [0]):
            rows_html.append(
                f"<tr><td colspan='{len(days) + 1}' style='border-top:3px solid #E24B4A;"
                "padding:2px 8px;font-size:0.72rem;color:#A32D2D'>capacity limit — rows below "
                "are over capacity</td></tr>"
            )

    st.markdown(
        "<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%'>"
        f"<tr><th style='background:#2c2c2a;color:#fff;padding:8px'></th>{head}</tr>"
        f"{''.join(rows_html)}</table></div>",
        unsafe_allow_html=True,
    )

    total_alloc = sum(len(day_cells[d]) for d in days)
    total_cap = sum(day_capacity.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Allocated this week", f"{total_alloc}h")
    m2.metric("Team capacity", f"{total_cap}h")
    m3.metric("Headroom", f"{total_cap - total_alloc}h",
              delta_color="inverse" if total_cap - total_alloc < 0 else "normal")


# ----------------------------------------------------------------------------
# Weekly report
# ----------------------------------------------------------------------------

def hours_in_window(t, off_by_member, win_start, win_end):
    """Portion of a task's estimated hours that falls inside [win_start, win_end]."""
    hrs = float(t.get("estimated_hours") or 0)
    win = task_window(t)
    if hrs <= 0 or win is None:
        return 0.0
    who = t.get("assignee")
    days = [d for d in working_days_between(*win)
            if d not in off_by_member.get(who, set())]
    if not days:
        days = [win[0]]
    per = hrs / len(days)
    return per * sum(1 for d in days if win_start <= d <= win_end)


def render_weekly_report(projects, all_tasks, off_by_member):
    st.subheader("📑 Weekly report — time by task & category")
    proj_by_id = {p["id"]: p["name"] for p in projects}

    c1, c2 = st.columns([2, 3])
    ref = c1.date_input("Pick any day in the week", value=date.today(), key="report_week")
    week_start = ref - timedelta(days=ref.weekday())          # Monday
    week_end = week_start + timedelta(days=4)                 # Friday
    c2.markdown(f"##### Week of **{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}**")
    st.caption("Hours = each task's estimated hours spread over its start→due working days "
               f"({DAY_HOURS}h day from {DAY_START}, Mon–Fri, off days skipped); "
               "only the portion falling in this week is counted. Includes Done tasks (work performed).")

    rows = []
    skipped = 0
    for t in all_tasks:
        h = hours_in_window(t, off_by_member, week_start, week_end)
        if h <= 0:
            if float(t.get("estimated_hours") or 0) > 0 and task_window(t) is None:
                skipped += 1
            continue
        cat = category_of(t)
        rows.append({
            "Category": cat,
            "Task": t["title"],
            "Project": proj_by_id.get(t["project_id"], "?"),
            "Assignee": t.get("assignee") or "Unassigned",
            "Status": t["status"],
            "Hours this week": round(h, 1),
            "Total est. hours": float(t.get("estimated_hours") or 0),
        })

    if not rows:
        st.info("No task hours fall in this week. Tasks need estimated hours and a start/due date to appear.")
        return

    df = pd.DataFrame(rows)
    total = df["Hours this week"].sum()

    # Headline totals
    cat_totals = df.groupby("Category")["Hours this week"].sum()
    cols = st.columns(len(cat_totals) + 1)
    cols[0].metric("Total hours", f"{total:g}h")
    for i, (cat, h) in enumerate(cat_totals.items(), start=1):
        pct = 100 * h / total if total else 0
        cols[i].metric(f"{CATEGORY_ICONS.get(cat, '')} {cat}", f"{h:g}h", f"{pct:.0f}% of week", delta_color="off")

    # Detail per category
    for cat in ["Research", "Tactical", "Uncategorized"]:
        part = df[df["Category"] == cat]
        if part.empty:
            continue
        st.markdown(f"### {CATEGORY_ICONS.get(cat, '')} {cat} — {part['Hours this week'].sum():g}h")
        st.dataframe(part.drop(columns=["Category"]).sort_values("Hours this week", ascending=False),
                     width="stretch", hide_index=True)

    # Member × category summary
    st.markdown("### 👥 By member")
    pivot = df.pivot_table(index="Assignee", columns="Category",
                           values="Hours this week", aggfunc="sum", fill_value=0)
    pivot["Total"] = pivot.sum(axis=1)
    st.dataframe(pivot.round(1), width="stretch")

    if skipped:
        st.caption(f"⚠ {skipped} task(s) have hours but no start/due date and can't be placed in any week.")

    st.download_button(
        "⬇ Download report (CSV)",
        df.sort_values(["Category", "Hours this week"], ascending=[True, False]).to_csv(index=False).encode(),
        file_name=f"weekly_report_{week_start.isoformat()}.csv",
        mime="text/csv",
    )


# ----------------------------------------------------------------------------
# "My tasks" view for team members
# ----------------------------------------------------------------------------

def render_my_tasks(projects, members, all_tasks, subs_by_task):
    st.subheader("🙋 My tasks")
    if not members:
        st.info("No team members configured yet.")
        return
    who = st.selectbox("I am…", [m["name"] for m in members])

    found_anything = False
    for p in projects:
        # Once a task has subtasks, individual work is assigned at the
        # subtask level — show those instead of the parent task itself.
        my_subtasks = []  # (task, subtask) pairs
        my_whole_tasks = []
        for t in project_tasks(p["id"], all_tasks):
            subs = subs_by_task.get(t["id"], [])
            if subs:
                for s in subs:
                    if s.get("assignee") == who:
                        my_subtasks.append((t, s))
            elif t.get("assignee") == who:
                my_whole_tasks.append(t)

        if not my_subtasks and not my_whole_tasks:
            continue
        found_anything = True
        st.markdown(f"#### 📁 {p['name']}")

        for t in my_whole_tasks:
            with st.container(border=True):
                st.markdown(f"**{t['title']}**")
                meta = [f"{STATUS_ICONS.get(t['status'], '')} {t['status']}",
                        f"{PRIORITY_ICONS[priority_of(t)]} {priority_of(t)}"]
                d = parse_date(t.get("due_date"))
                if d:
                    meta.append(due_label(d))
                st.caption(" · ".join(meta))
                if t.get("description"):
                    st.caption(t["description"])

        for t, s in my_subtasks:
            with st.container(border=True):
                st.caption(f"📁 {t['title']}")
                st.markdown(f"**{s['title']}**")
                status = subtask_status(s)
                prio = s.get("priority") or "Normal"
                meta = [f"{STATUS_ICONS.get(status, '')} {status}", f"{PRIORITY_ICONS.get(prio, '')} {prio}"]
                d = parse_date(s.get("due_date"))
                if d:
                    meta.append(due_label(d))
                st.caption(" · ".join(meta))
                if s.get("notes"):
                    st.caption(f"📝 {s['notes']}")

    if not found_anything:
        st.info(f"No tasks or subtasks assigned to {who} yet.")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    login_gate()
    auth_sidebar()

    projects = sorted(fetch("projects"), key=lambda p: p["id"])
    members = sorted(fetch("members"), key=lambda m: m["name"])
    all_tasks, subs_by_task = load_all_data()
    off_by_member = get_off_days()

    tab_names = ["📋 Boards", "🙋 My tasks", "🚚 Deliveries", "📊 Bandwidth", "🗓 Capacity", "📑 Report"]
    if is_admin():
        tab_names.append("⚙️ Settings")
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_alerts(projects, all_tasks)
        st.write("")
        if not projects:
            st.info("No projects yet." + (" Create one in the Settings tab." if is_admin()
                    else " Ask your coordinator to create one."))
        else:
            c1, c2 = st.columns([3, 2])
            names = [p["name"] for p in projects]
            picked = c1.selectbox("Project", names, label_visibility="collapsed")
            view = c2.radio("View", ["📃 List", "📊 Kanban"], horizontal=True,
                            label_visibility="collapsed")
            project = next(p for p in projects if p["name"] == picked)
            if view == "📃 List":
                render_list(project, all_tasks, subs_by_task)
            else:
                render_kanban(project, all_tasks, subs_by_task)
            if is_admin():
                admin_task_manager(project, members, all_tasks, subs_by_task)

    with tabs[1]:
        render_my_tasks(projects, members, all_tasks, subs_by_task)

    with tabs[2]:
        render_deliveries(projects, members, all_tasks)

    with tabs[3]:
        render_bandwidth(projects, members, all_tasks, off_by_member)

    with tabs[4]:
        render_capacity_grid(projects, members, all_tasks, off_by_member)

    with tabs[5]:
        render_weekly_report(projects, all_tasks, off_by_member)

    if is_admin():
        with tabs[6]:
            admin_settings(projects, members)


main()
