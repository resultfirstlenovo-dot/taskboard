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
- **Email notifications via Microsoft Graph** — instant email on task assignment/update, a reminder 24h before due, an overdue alert, and a daily pending/overdue summary. Global and per-member on/off switches; every send is logged for troubleshooting. See [Notifications setup](#notifications-setup-microsoft-365--graph) below.

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

Notifications stay disabled until you complete [Notifications setup](#notifications-setup-microsoft-365--graph) below — the rest of the app works fully without it.

### Step 4 — Share

- Send the app URL + the **viewer password** to the 7 team members. They can view everything but change nothing.
- Keep the **coordinator password** to yourself. Enter it on the login screen (or via "Switch to coordinator" in the sidebar) to unlock editing.
- Nobody without a password can see any data — safe even though the Streamlit URL is public.

---

## Daily use

**Coordinator**

1. Sidebar → Coordinator login → enter password.
2. **Settings** tab: create projects, manage member names/emails, and configure notifications.
3. **Boards** tab: check the 🚨 Alerts banner first, then pick a project, add tasks (title, description, assignee, due date, priority), add subtasks. Toggle between **List** (default) and **Kanban** (drag & drop) view.
4. **Deliveries** tab: check overdue / due-today work per member each morning.

**Team members**

1. Open the link (no login).
2. **My tasks** tab → pick your name → see your tasks across all projects.
3. **Deliveries** tab → filter by your name → see your deadlines.

---

## Notifications setup (Microsoft 365 / Graph)

Notifications use Microsoft Graph's **application (app-only) permissions**
with the client-credentials flow — Microsoft's recommended pattern for
unattended services that send mail with no signed-in user. This needs a
one-time Azure setup by whoever administers your Microsoft 365 tenant.

### 1. Register an app in Microsoft Entra ID

1. [entra.microsoft.com](https://entra.microsoft.com) → **App registrations** → **New registration**.
2. Name it e.g. `TaskBoard Notifications`, leave the default single-tenant option, no redirect URI needed → **Register**.
3. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page.
4. **Certificates & secrets** → **New client secret** → copy the secret **value** immediately (it's hidden after you leave the page).

### 2. Grant Mail.Send (application permission)

1. **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions** → search `Mail.Send` → add it.
2. Click **Grant admin consent for \<your org\>** (requires a Global/Application Administrator).

### 3. Scope it to one mailbox (Microsoft's recommended hardening)

By default, `Mail.Send` as an application permission lets the app send as
*any* mailbox in the tenant. Microsoft's documented mitigation is an
Exchange Online **application access policy** that restricts it to a
single mailbox (e.g. a shared mailbox like `taskboard@yourorg.com`):

```powershell
# Run in Exchange Online PowerShell (Connect-ExchangeOnline first)
New-DistributionGroup -Name "TaskBoardMailScope" -Members taskboard@yourorg.com
New-ApplicationAccessPolicy -AppId "<client-id>" `
  -PolicyScopeGroupId "TaskBoardMailScope" -AccessRight RestrictAccess `
  -Description "Restrict TaskBoard app to only send as taskboard@yourorg.com"
```

Reference: [Limit application permissions to specific mailboxes](https://learn.microsoft.com/graph/auth-limit-mailbox-access).

### 4. Configure TaskBoard with the real values

You'll set the same 4 values in two places — they're used independently by
the live app (instant emails) and by the GitHub Actions scheduler (daily
checks):

**A. Streamlit Cloud → your app → Settings → Secrets** — add to the existing TOML:

```toml
[graph]
tenant_id = "<directory-tenant-id>"
client_id = "<application-client-id>"
client_secret = "<client-secret-value>"
sender_email = "taskboard@yourorg.com"
```

**B. GitHub repo → Settings → Secrets and variables → Actions → New repository secret** — add each of:

```
SUPABASE_URL
SUPABASE_KEY
MS_GRAPH_TENANT_ID
MS_GRAPH_CLIENT_ID
MS_GRAPH_CLIENT_SECRET
MS_GRAPH_SENDER_EMAIL
```

(`SUPABASE_URL`/`SUPABASE_KEY` are the same values from your `[supabase]` secrets — the scheduler script runs outside Streamlit so it can't read `st.secrets`.)

Until real values replace the placeholders in `secrets.example.toml` /
Streamlit secrets, every notification call fails safely with a logged
error — the board itself is unaffected.

### 5. What gets sent, and when

| Notification | Trigger | Sent by |
|---|---|---|
| Task assigned | A task is created or reassigned with an assignee | Instantly, from the running app |
| Task updated | Title/description/due date/status/priority changes on an assigned task | Instantly, from the running app |
| Due tomorrow | Task due date is tomorrow and status ≠ Done | Daily scheduled job |
| Overdue | Task due date has passed and status ≠ Done | Daily scheduled job |
| Daily summary | Once per day per member with any pending/overdue tasks | Daily scheduled job |

The daily jobs run via `.github/workflows/notifications.yml` (GitHub
Actions cron, free on public repos). Adjust the `cron:` time to your
team's morning, or trigger it manually from the repo's **Actions** tab
("Run workflow").

### 6. Notification Settings (in-app)

Coordinator → **Settings** tab → **🔔 Notifications**:

- A global on/off switch for all email notifications.
- Per-member email address and opt-in/opt-out switch — a member only gets
  email if the global switch, their own switch, and their email address
  are all set.
- A **recent notification log** (last 50 events) showing what was sent,
  skipped, or failed, with the error message for anything that failed —
  the same `notification_log` table the dedupe logic uses to guarantee no
  duplicate emails.

### Applying this to an existing installation

If your Supabase database was created before priority/notifications
existed, just re-run the full `schema.sql` in **SQL Editor** — every
statement in it is `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`, so it's
safe to run again without touching your existing projects/tasks/members.

---

## Local testing (optional)

```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp secrets.example.toml .streamlit/secrets.toml
# edit .streamlit/secrets.toml with real values
streamlit run app.py
```
