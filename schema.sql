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
    category text not null default 'Tactical',
    start_date date,
    estimated_hours numeric not null default 0,
    position int default 0,
    created_at timestamptz default now()
);

-- Safe to re-run: adds columns to a tasks table created before these features existed.
alter table tasks add column if not exists priority text not null default 'Normal';
alter table tasks add column if not exists category text not null default 'Tactical';
alter table tasks add column if not exists start_date date;
alter table tasks add column if not exists estimated_hours numeric not null default 0;

create table if not exists subtasks (
    id bigint generated always as identity primary key,
    task_id bigint not null references tasks(id) on delete cascade,
    title text not null,
    is_done boolean not null default false,
    created_at timestamptz default now()
);

-- Subtasks became full work items (assignee/status/priority/due date/notes)
-- instead of a plain checklist. `is_done` is kept (unused by the app going
-- forward) rather than dropped, since dropping a column is destructive.
-- Safe to re-run.
alter table subtasks add column if not exists assignee text;
alter table subtasks add column if not exists status text not null default 'To Do';
alter table subtasks add column if not exists priority text not null default 'Normal';
alter table subtasks add column if not exists due_date date;
alter table subtasks add column if not exists notes text;

-- Off days (vacation/sick leave) — zero capacity for those dates in the
-- bandwidth/capacity views.
create table if not exists time_off (
    id bigint generated always as identity primary key,
    member_name text not null,
    off_date date not null,
    reason text,
    created_at timestamptz default now(),
    unique (member_name, off_date)
);

-- The app enforces admin-vs-viewer permissions itself (admin password),
-- so allow the app's key full access to these tables:
alter table projects disable row level security;
alter table members  disable row level security;
alter table tasks    disable row level security;
alter table subtasks disable row level security;
alter table time_off disable row level security;

-- Seed the 7 team members (edit the names, or manage them later in the app's Settings tab)
insert into members (name) values
    ('Shrishti'), ('Shivam'), ('Mahendra'), ('Aman'), ('Neelee'), ('Ritu'), ('Yash')
on conflict (name) do nothing;
