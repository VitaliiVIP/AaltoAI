"""Sends the candidate email over real SMTP.

Defaults (via backend/.env) to a disposable Ethereal Email test mailbox
(https://ethereal.email): the message is genuinely transmitted over SMTP —
this is not a stub — but Ethereal is a sandbox, so nothing ever reaches a
real inbox. Log in at https://ethereal.email with SMTP_USER / SMTP_PASS to
read everything that's been "sent". Point SMTP_* at a real provider's
credentials to deliver to real inboxes instead; nothing else changes.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from . import config  # noqa: F401  (import order matters: loads .env as a side effect)


class EmailError(RuntimeError):
    """Raised for both missing configuration and SMTP-level failures."""


def send_email(to: str, subject: str, body: str) -> dict:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM") or user
    web = os.environ.get("SMTP_WEB", "https://ethereal.email/messages")

    if not host or not user or not password:
        raise EmailError(
            "SMTP is not configured — set SMTP_HOST, SMTP_USER, SMTP_PASS in backend/.env "
            "(see .env.example)"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
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
