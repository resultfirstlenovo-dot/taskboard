"""
TaskBoard — Kanban project management for a coordinator + 7 team members.

- Admin (project coordinator): unlocks with password -> full add/edit/delete + drag & drop.
- Team members: open the link, pick their name -> read-only view of their tasks.
- Backend: Supabase (Postgres). Deployed on Streamlit Community Cloud.
"""

from datetime import date, datetime, timedelta

import streamlit as st
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


def priority_of(t):
    p = t.get("priority") or "Normal"
    return p if p in PRIORITIES else "Normal"


def priority_rank(t):
    return PRIORITIES.index(priority_of(t))

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


def fetch(table, **filters):
    q = sb.table(table).select("*")
    for col, val in filters.items():
        q = q.eq(col, val)
    return q.execute().data or []


def insert(table, row):
    return sb.table(table).insert(row).execute().data


def update_row(table, row_id, changes):
    sb.table(table).update(changes).eq("id", row_id).execute()


def delete_row(table, row_id):
    sb.table(table).delete().eq("id", row_id).execute()


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
    subs = subtasks_by_task.get(t["id"], [])
    if subs:
        done = sum(1 for s in subs if s["is_done"])
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


def load_project_data(project_id):
    tasks = fetch("tasks", project_id=project_id)
    tasks.sort(key=lambda t: (t.get("position") or 0, t["id"]))
    task_ids = [t["id"] for t in tasks]
    subs = []
    if task_ids:
        subs = (
            sb.table("subtasks").select("*").in_("task_id", task_ids).execute().data
            or []
        )
    subs_by_task = {}
    for s in sorted(subs, key=lambda s: s["id"]):
        subs_by_task.setdefault(s["task_id"], []).append(s)
    return tasks, subs_by_task


# ----------------------------------------------------------------------------
# Alerts banner
# ----------------------------------------------------------------------------

def render_alerts(projects):
    """Red-flag section at the very top: overdue, due today, and urgent tasks."""
    proj_by_id = {p["id"]: p["name"] for p in projects}
    open_tasks = [t for t in fetch("tasks") if t["status"] != "Done"]
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

def render_list(project, member_filter=None):
    tasks, subs_by_task = load_project_data(project["id"])
    if member_filter:
        tasks = [t for t in tasks if t.get("assignee") == member_filter]
    if not tasks:
        st.info("No tasks here yet." if not member_filter
                else f"No tasks assigned to {member_filter} in this project.")
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
                        done = sum(1 for s in subs if s["is_done"])
                        with st.expander(f"☑ Subtasks {done}/{len(subs)}"):
                            for s in subs:
                                st.caption(("✅ " if s["is_done"] else "⬜ ") + s["title"])
                with c2:
                    p = priority_of(t)
                    st.markdown(f"{PRIORITY_ICONS[p]} {p}")
                with c3:
                    st.markdown(f"👤 {t.get('assignee') or '—'}")
                with c4:
                    d = parse_date(t.get("due_date"))
                    st.markdown(due_label(d) if d else "📅 —")
        st.write("")


# ----------------------------------------------------------------------------
# Kanban board
# ----------------------------------------------------------------------------

def render_kanban(project, member_filter=None):
    tasks, subs_by_task = load_project_data(project["id"])
    if member_filter:
        tasks = [t for t in tasks if t.get("assignee") == member_filter]

    if not tasks:
        st.info("No tasks here yet." if not member_filter else f"No tasks assigned to {member_filter} in this project.")
        return

    if is_admin() and not member_filter:
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
                            done = sum(1 for s in subs if s["is_done"])
                            st.progress(done / len(subs), text=f"Subtasks {done}/{len(subs)}")
                            for s in subs:
                                st.caption(("✅ " if s["is_done"] else "⬜ ") + s["title"])


# ----------------------------------------------------------------------------
# Admin: manage projects / tasks / subtasks / members
# ----------------------------------------------------------------------------

def admin_task_manager(project, members):
    tasks, subs_by_task = load_project_data(project["id"])
    member_names = [m["name"] for m in members]

    st.divider()
    left, right = st.columns(2)

    # ---- Add task ----
    with left:
        st.subheader("➕ Add task")
        with st.form(f"add_task_{project['id']}", clear_on_submit=True):
            title = st.text_input("Title *")
            description = st.text_area("Description", height=80)
            c1, c2, c3, c4 = st.columns(4)
            assignee = c1.selectbox("Assign to", ["—"] + member_names)
            due = c2.date_input("Due date", value=None)
            status = c3.selectbox("Status", STATUSES)
            prio = c4.selectbox("Priority", PRIORITIES, index=2)
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
                        "due_date": due.isoformat() if due else None,
                        "status": status,
                        "priority": prio,
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
            c1, c2, c3, c4 = st.columns(4)
            current_assignee = t.get("assignee")
            assignee_opts = ["—"] + member_names
            a_idx = assignee_opts.index(current_assignee) if current_assignee in assignee_opts else 0
            assignee = c1.selectbox("Assign to", assignee_opts, index=a_idx)
            due = c2.date_input("Due date", value=parse_date(t.get("due_date")))
            status = c3.selectbox("Status", STATUSES, index=STATUSES.index(t["status"]) if t["status"] in STATUSES else 0)
            prio = c4.selectbox("Priority", PRIORITIES, index=priority_rank(t))
            b1, b2 = st.columns(2)
            if b1.form_submit_button("Save changes", width="stretch"):
                update_row("tasks", t["id"], {
                    "title": title.strip(),
                    "description": description.strip() or None,
                    "assignee": None if assignee == "—" else assignee,
                    "due_date": due.isoformat() if due else None,
                    "status": status,
                    "priority": prio,
                })
                st.rerun()
            if b2.form_submit_button("🗑 Delete task", width="stretch"):
                delete_row("tasks", t["id"])
                st.rerun()

        # ---- Subtasks ----
        st.markdown(f"**Subtasks of #{t['id']}**")
        for s in subs_by_task.get(t["id"], []):
            c1, c2 = st.columns([6, 1])
            new_val = c1.checkbox(s["title"], value=s["is_done"], key=f"sub_{s['id']}")
            if new_val != s["is_done"]:
                update_row("subtasks", s["id"], {"is_done": new_val})
                st.rerun()
            if c2.button("🗑", key=f"del_sub_{s['id']}"):
                delete_row("subtasks", s["id"])
                st.rerun()
        c1, c2 = st.columns([5, 1])
        new_sub = c1.text_input("New subtask", key=f"new_sub_{t['id']}", label_visibility="collapsed",
                                placeholder="New subtask…")
        if c2.button("Add", key=f"add_sub_{t['id']}"):
            if new_sub.strip():
                insert("subtasks", {"task_id": t["id"], "title": new_sub.strip(), "is_done": False})
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


# ----------------------------------------------------------------------------
# Deliveries dashboard
# ----------------------------------------------------------------------------

def render_deliveries(projects, members):
    st.subheader("🚚 Deliveries by due date")
    proj_by_id = {p["id"]: p["name"] for p in projects}
    all_tasks = fetch("tasks")

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
            "Status": f"{STATUS_ICONS.get(t['status'], '')} {t['status']}",
        } for t in items]
        st.dataframe(table, width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# "My tasks" view for team members
# ----------------------------------------------------------------------------

def render_my_tasks(projects, members):
    st.subheader("🙋 My tasks")
    if not members:
        st.info("No team members configured yet.")
        return
    who = st.selectbox("I am…", [m["name"] for m in members])
    for p in projects:
        tasks, _ = load_project_data(p["id"])
        mine = [t for t in tasks if t.get("assignee") == who]
        if not mine:
            continue
        st.markdown(f"#### 📁 {p['name']}")
        render_list(p, member_filter=who)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    login_gate()
    auth_sidebar()

    projects = sorted(fetch("projects"), key=lambda p: p["id"])
    members = sorted(fetch("members"), key=lambda m: m["name"])

    tab_names = ["📋 Boards", "🙋 My tasks", "🚚 Deliveries"]
    if is_admin():
        tab_names.append("⚙️ Settings")
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_alerts(projects)
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
                render_list(project)
            else:
                render_kanban(project)
            if is_admin():
                admin_task_manager(project, members)

    with tabs[1]:
        render_my_tasks(projects, members)

    with tabs[2]:
        render_deliveries(projects, members)

    if is_admin():
        with tabs[3]:
            admin_settings(projects, members)


main()
