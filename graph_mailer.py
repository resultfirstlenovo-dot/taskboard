"""
Microsoft Graph email sender for TaskBoard.

Uses the client-credentials (app-only) flow via MSAL, which is Microsoft's
recommended approach for unattended/service scenarios (no signed-in user) —
see https://learn.microsoft.com/graph/auth-v2-service.

Required config (env vars, or Streamlit secrets under [graph]):
    MS_GRAPH_TENANT_ID      - Azure AD tenant ID
    MS_GRAPH_CLIENT_ID      - App registration (client) ID
    MS_GRAPH_CLIENT_SECRET  - App registration client secret
    MS_GRAPH_SENDER_EMAIL   - Mailbox to send from (e.g. taskboard@yourorg.com)

The app registration needs the *application* permission `Mail.Send` with
admin consent granted. To avoid granting it tenant-wide send-as rights,
scope it to only the sender mailbox with an Exchange Online application
access policy (see README.md).
"""

import os

import msal
import requests

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
_PLACEHOLDER_MARKERS = ("YOUR-", "PLACEHOLDER", "CHANGE-ME", "xxxx")


class GraphMailerError(Exception):
    """Raised when Graph auth or send fails, or config is missing/placeholder."""


def _get_setting(key):
    env_val = os.environ.get(f"MS_GRAPH_{key.upper()}")
    if env_val:
        return env_val
    try:
        import streamlit as st
        return st.secrets["graph"][key]
    except Exception:
        return None


def _is_placeholder(value):
    if not value:
        return True
    upper = value.upper()
    return any(marker in upper for marker in _PLACEHOLDER_MARKERS)


def _config():
    cfg = {
        "tenant_id": _get_setting("tenant_id"),
        "client_id": _get_setting("client_id"),
        "client_secret": _get_setting("client_secret"),
        "sender_email": _get_setting("sender_email"),
    }
    if any(_is_placeholder(v) for v in cfg.values()):
        raise GraphMailerError(
            "Microsoft Graph is not configured yet (placeholder or missing "
            "credentials) — notifications are disabled until real Azure App "
            "Registration values are provided."
        )
    return cfg


def _acquire_token(cfg):
    authority = f"https://login.microsoftonline.com/{cfg['tenant_id']}"
    app = msal.ConfidentialClientApplication(
        cfg["client_id"], authority=authority, client_credential=cfg["client_secret"]
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise GraphMailerError(
            f"Failed to acquire Graph token: {result.get('error_description', result)}"
        )
    return result["access_token"]


def send_mail(to_email, subject, html_body):
    """Send one HTML email via Microsoft Graph. Raises GraphMailerError on any failure."""
    if not to_email:
        raise GraphMailerError("No recipient email address provided.")

    cfg = _config()
    token = _acquire_token(cfg)

    url = f"https://graph.microsoft.com/v1.0/users/{cfg['sender_email']}/sendMail"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": "false",
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if resp.status_code >= 300:
        raise GraphMailerError(f"Graph sendMail failed ({resp.status_code}): {resp.text[:300]}")
