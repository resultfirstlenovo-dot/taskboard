# TaskBoard — Kanban tool for your team

A Streamlit kanban app for one project coordinator (full control) and 7 team members (read-only).

**Features**

- Multiple projects, each with its own board
- Tasks with description, assignee, due date, **priority (🔴 Urgent / 🟠 High / 🔵 Normal / ⚪ Low)**, and subtasks with progress tracking
- **🚨 Alerts section at the top** — overdue, due-today, and urgent tasks across all projects, visible to everyone at a glance
- **Vertical list view (default, Asana-style)** — all statuses in one scrollable view; kanban with drag & drop available as a toggle (coordinator only)
- Drag & drop between To Do / In Progress / Review / Done (coordinator only)
- "My tasks" tab — each member picks their name and sees only their tasks
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
3. **Boards** tab: check the 🚨 Alerts banner first, then pick a project, add tasks (title, description, assignee, due date, priority), add subtasks. Toggle between **List** (default) and **Kanban** (drag & drop) view.
4. **Deliveries** tab: check overdue / due-today work per member each morning.

**Team members**

1. Open the link (no login).
2. **My tasks** tab → pick your name → see your tasks across all projects.
3. **Deliveries** tab → filter by your name → see your deadlines.

---

## Applying the priority feature to an existing installation

If your Supabase database was created before the priority feature existed,
just re-run the full `schema.sql` in **SQL Editor** — every statement in
it is `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`, so it's safe to run
again without touching your existing projects/tasks/members.

---

## Local testing (optional)

```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp secrets.example.toml .streamlit/secrets.toml
# edit .streamlit/secrets.toml with real values
streamlit run app.py
```
