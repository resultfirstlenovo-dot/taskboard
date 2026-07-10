# TaskBoard — Kanban tool for your team

A Streamlit kanban app for one project coordinator (full control) and 7 team members (read-only).

**Features**

- Multiple projects, each with its own board
- Tasks with description, assignee, start date, due date, **estimated hours**, **priority (🔴 Urgent / 🟠 High / 🔵 Normal / ⚪ Low)**, and a **🔬 Research / ⚙️ Tactical category**
- **Subtasks are full work items** — each has its own assignee, status, priority, due date, and optional notes. A progress bar (e.g. 3/7 complete) shows on the parent task, and completing every subtask automatically completes the parent (undoing one reopens it).
- **📊 Bandwidth tab** — Gantt chart of scheduled tasks (daily or weekly zoom) plus a per-member bandwidth table: 8h working day starting 10:00, Mon–Fri; task hours spread evenly across each task's start→due working days; overbooked days flagged 🔴
- **Off days** — coordinator marks vacation/sick days per member in Settings; those days count as zero capacity and are skipped when spreading task hours
- **📑 Weekly report tab** — pick a week and get: total hours, Research vs Tactical split with percentages, per-task hours grouped by category, a member × category summary, and a CSV download for sharing
- **🗓 Capacity tracker tab** — Excel-style grid: rows = combined team hours, columns = Mon–Fri, one colored cell per hour of a task (blue Research / amber Tactical). Each day shows its own capacity (8h × members on duty, minus off days). Work planned beyond capacity isn't cut off — extra rows appear below a red capacity line with over-capacity cells outlined red. Filter by member or project; headroom metrics at the bottom
- **🚨 Alerts section at the top** — overdue, due-today, and urgent tasks across all projects, visible to everyone at a glance
- **Vertical list view (default, Asana-style)** — all statuses in one scrollable view; kanban with drag & drop available as a toggle (coordinator only)
- Drag & drop between To Do / In Progress / Review / Done (coordinator only)
- "My tasks" tab — each member picks their name and sees only their tasks. Once a task has subtasks, this shows the specific **subtasks** assigned to them (with the parent task as context) rather than the whole task.
- "Deliveries" tab — all tasks grouped by Overdue / Due today / This week / Later, filterable by member and project
- Two passwords: a shared **viewer password** for the 7 team members (read-only) and a **coordinator password** for full add/edit/delete. Nothing is visible without a password.

---

## Setup (one time, ~15 minutes)

### Step 1 — Create the Supabase database (free)

1. Go to [supabase.com](https://supabase.com) → sign up → **New project** (free plan is fine).
2. Pick any project name and a database password (you won't need the DB password again).
3. Once the project loads, open **SQL Editor** (left sidebar) → **New query**.
4. Paste the entire contents of `schema.sql` → click **Run**. You should see "Success".
5. Edit the member names: either change the names at the bottom of `schema.sql` before running, or fix them later in the app's **Settings** tab.
6. Get your credentials: **Project Settings → API**. Copy:
   - **Project URL** (like `https://abcd1234.supabase.co`)
   - **anon public** key

### Step 2 — Put the code on GitHub

1. Create a free account at [github.com](https://github.com) if needed.
2. Create a **new repository** (e.g. `taskboard`, can be private).
3. Upload these 3 files to it: `app.py`, `requirements.txt`, `schema.sql`.
   - Do **not** upload `secrets.example.toml` with real values filled in.

### Step 3 — Deploy on Streamlit Community Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub.
2. **Create app** → pick your repo, branch `main`, main file `app.py` → **Deploy**.
3. While it builds, open **Settings → Secrets** (⋮ menu on your app) and paste, with your real values:

```toml
[supabase]
url = "https://YOUR-PROJECT-REF.supabase.co"
key = "YOUR-ANON-PUBLIC-KEY"

[app]
admin_password = "choose-a-strong-password"
viewer_password = "shared-team-password"
```

4. Save. The app restarts and is live at `https://<your-app>.streamlit.app`.

### Step 4 — Share

- Send the app URL + the **viewer password** to the 7 team members. They can view everything but change nothing.
- Keep the **coordinator password** to yourself. Enter it on the login screen (or via "Switch to coordinator" in the sidebar) to unlock editing.
- Nobody without a password can see any data — safe even though the Streamlit URL is public.

---

## Daily use

**Coordinator**

1. Sidebar → Coordinator login → enter password.
2. **Settings** tab: create projects, manage member names.
3. **Boards** tab: check the 🚨 Alerts banner first, then pick a project, add tasks (title, description, assignee, start/due date, estimated hours, priority, category). Break a task into subtasks (each with its own assignee/status/priority/due date/notes) to divide the work across the team — the parent task's progress bar and status track automatically as subtasks are completed. Toggle between **List** (default) and **Kanban** (drag & drop) view — note that expand/collapse of subtasks is only available in List view; Kanban cards show a compact "3/7" progress count since the drag-and-drop library only supports plain-text cards.
4. **Deliveries** tab: check overdue / due-today work per member each morning.
5. **Bandwidth** tab: Gantt chart + per-member workload for a day or week — give tasks an assignee, estimated hours, and a start/due date for this to populate.
6. **Capacity** tab: hour-by-hour team capacity grid for the week, colored by category.
7. **Report** tab: weekly hours by category and by member, with a CSV export.
8. **Settings** tab: also manage team off-days (vacation/sick leave) — these are excluded from bandwidth/capacity calculations.

**Team members**

1. Open the link (no login).
2. **My tasks** tab → pick your name → see your tasks across all projects.
3. **Deliveries** tab → filter by your name → see your deadlines.

---

## Applying schema changes to an existing installation

If your Supabase database predates the priority, rich-subtask, or
bandwidth/capacity/category features, just re-run the full `schema.sql` in
**SQL Editor** — every statement in it is `IF NOT EXISTS` /
`ON CONFLICT DO NOTHING`, so it's safe to run again without touching your
existing projects/tasks/members/subtasks. It also **adds `pandas` and
`plotly`** to `requirements.txt` — redeploy after pulling the latest code
so those install.

### How bandwidth is calculated

Each member has 8 working hours per day (10:00–18:00), Monday–Friday. A
task's estimated hours are spread evenly across the working days between
its start and due date (a task with only a due date lands entirely on
that day). Off days and weekends are skipped. "Done" tasks are excluded.
Days where allocated hours exceed 8 are flagged 🔴 overbooked. For
accurate bandwidth, give tasks an assignee, estimated hours, and a
start + due date.

---

## Local testing (optional)

```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp secrets.example.toml .streamlit/secrets.toml
# edit .streamlit/secrets.toml with real values
streamlit run app.py
```
