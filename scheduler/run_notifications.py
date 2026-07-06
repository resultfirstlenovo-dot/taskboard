"""
Standalone daily notification job for TaskBoard.

Run by GitHub Actions on a cron schedule (see .github/workflows/notifications.yml),
completely independent of whether the Streamlit app happens to be awake.

Sends, in order:
  1. 24h-before due-date reminders
  2. Overdue notifications
  3. Daily summary digest per member

All dedup/opt-out/logging logic lives in notifications.py so this script and
the in-app instant notifications (app.py) share identical behavior.

Required environment variables (set as GitHub Actions secrets):
  SUPABASE_URL, SUPABASE_KEY
  MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, MS_GRAPH_SENDER_EMAIL
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

import notifications as notif


def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY environment variables are required.")
    return create_client(url, key)


def main():
    sb = get_client()

    steps = [
        ("due reminders", notif.send_due_reminders),
        ("overdue notifications", notif.send_overdue_notifications),
        ("daily summaries", notif.send_daily_summary),
    ]
    for label, fn in steps:
        try:
            fn(sb)
            print(f"[ok] {label}")
        except Exception as e:  # noqa: BLE001 - never let one step kill the others
            print(f"[error] {label}: {e}")


if __name__ == "__main__":
    main()
