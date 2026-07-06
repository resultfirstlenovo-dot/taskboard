-- TaskBoard schema — run this once in Supabase: SQL Editor -> New query -> paste -> Run

create table if not exists projects (
    id bigint generated always as identity primary key,
    name text not null,
    created_at timestamptz default now()
);

create table if not exists members (
    id bigint generated always as identity primary key,
    name text not null unique,
    created_at timestamptz default now()
);

create table if not exists tasks (
    id bigint generated always as identity primary key,
    project_id bigint not null references projects(id) on delete cascade,
    title text not null,
    description text,
    assignee text,
    due_date date,
    status text not null default 'To Do',
    priority text not null default 'Normal',
    position int default 0,
    created_at timestamptz default now()
);

-- Safe to re-run: adds priority to a tasks table created before this feature existed.
alter table tasks add column if not exists priority text not null default 'Normal';

create table if not exists subtasks (
    id bigint generated always as identity primary key,
    task_id bigint not null references tasks(id) on delete cascade,
    title text not null,
    is_done boolean not null default false,
    created_at timestamptz default now()
);

-- The app enforces admin-vs-viewer permissions itself (admin password),
-- so allow the app's key full access to these tables:
alter table projects disable row level security;
alter table members  disable row level security;
alter table tasks    disable row level security;
alter table subtasks disable row level security;

-- Seed the 7 team members (edit the names, or manage them later in the app's Settings tab)
insert into members (name) values
    ('Shrishti'), ('Shivam'), ('Mahendra'), ('Aman'), ('Neelee'), ('Ritu'), ('Yash')
on conflict (name) do nothing;

-- ----------------------------------------------------------------------------
-- Notifications (Microsoft Graph email) — safe to re-run on an existing database
-- ----------------------------------------------------------------------------

alter table members add column if not exists email text;
alter table members add column if not exists notifications_enabled boolean not null default true;

-- Single-row table holding the global on/off switch
create table if not exists app_settings (
    id bigint primary key,
    notifications_enabled boolean not null default true,
    constraint app_settings_single_row check (id = 1)
);
insert into app_settings (id, notifications_enabled) values (1, true)
on conflict (id) do nothing;

-- Every notification attempt is logged here. dedupe_key has a unique
-- constraint so the same event (task+type+day/minute bucket) can only ever
-- be recorded — and therefore sent — once.
create table if not exists notification_log (
    id bigint generated always as identity primary key,
    dedupe_key text not null unique,
    task_id bigint references tasks(id) on delete cascade,
    member_name text,
    notification_type text not null,
    recipient_email text,
    status text not null default 'pending',
    error_message text,
    created_at timestamptz default now()
);

alter table app_settings     disable row level security;
alter table notification_log disable row level security;
