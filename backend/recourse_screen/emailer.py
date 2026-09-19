"""Sends the candidate email through a real provider.

Two providers, selected automatically by what's configured in backend/.env:

- Mailgun (MAILGUN_API_KEY + MAILGUN_DOMAIN set): a real transactional email
  API — messages are delivered to real inboxes. The domain must be one
  that's actually verified in your Mailgun account, or their sandbox domain
  (which only delivers to recipients you've pre-authorized in the dashboard).
- SMTP (fallback): defaults to a disposable Ethereal Email test mailbox
  (https://ethereal.email) — genuinely sent over SMTP, but never reaches a
  real inbox. Useful when no real provider is configured.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from . import config  # noqa: F401  (import order matters: loads .env as a side effect)


class EmailError(RuntimeError):
    """Raised for both missing configuration and provider-level failures."""


def send_email(to: str, subject: str, body: str) -> dict:
    mg_key = os.environ.get("MAILGUN_API_KEY")
    mg_domain = os.environ.get("MAILGUN_DOMAIN")
    if mg_key and mg_domain:
        return _send_via_mailgun(mg_key, mg_domain, to, subject, body)
    return _send_via_smtp(to, subject, body)


def _sender() -> str:
    return os.environ.get("SMTP_FROM") or "Recourse Hiring Copilot <no-reply@example.com>"


def _send_via_mailgun(api_key: str, domain: str, to: str, subject: str, body: str) -> dict:
    base = os.environ.get("MAILGUN_API_BASE", "https://api.mailgun.net/v3")
    url = f"{base}/{domain}/messages"
    data = urllib.parse.urlencode(
        {"from": _sender(), "to": to, "subject": subject, "text": body}
    ).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    token = base64.b64encode(f"api:{api_key}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            json.loads(resp.read().decode())  # validate it's the expected JSON shape
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        # Mailgun's most common failure here: sandbox domain + an unauthorized recipient.
        raise EmailError(f"Mailgun send failed ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise EmailError(f"Mailgun send failed: {e.reason}") from e

    return {"ok": True, "web": f"https://app.mailgun.com/mg/sending/{domain}/logs"}


def _send_via_smtp(to: str, subject: str, body: str) -> dict:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    web = os.environ.get("SMTP_WEB", "https://ethereal.email/messages")

    if not host or not user or not password:
        raise EmailError(
            "Neither Mailgun (MAILGUN_API_KEY/MAILGUN_DOMAIN) nor SMTP "
            "(SMTP_HOST/SMTP_USER/SMTP_PASS) is configured in backend/.env "
            "(see .env.example)"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _sender()
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"SMTP send failed: {e}") from e

    return {"ok": True, "web": web}
