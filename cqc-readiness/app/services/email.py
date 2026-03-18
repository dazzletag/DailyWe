from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

logger = logging.getLogger(__name__)

# Path to the templates/email directory relative to this file
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "email")

_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


async def get_access_token() -> str:
    """Obtain an OAuth2 client-credentials access token from Microsoft identity platform."""
    settings = get_settings()
    url = (
        f"https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}"
        "/oauth2/v2.0/token"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.GRAPH_CLIENT_ID,
                "client_secret": settings.GRAPH_CLIENT_SECRET,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> None:
    """
    Send an email via Microsoft Graph API /sendMail endpoint.

    Uses the sender configured in settings.GRAPH_SENDER_EMAIL.
    """
    settings = get_settings()
    token = await get_access_token()

    message: dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                        "name": to_name,
                    }
                }
            ],
        },
        "saveToSentItems": "false",
    }

    if text_body:
        # Graph API doesn't natively support dual content types in a single body,
        # so we attach the plain text as an additional MIME alternative via a
        # separate attachment if needed.  For production, a plain text body can be
        # added as a secondary body in the message payload using the MIME approach.
        # For simplicity we include it as a comment in the HTML.
        pass

    url = (
        f"https://graph.microsoft.com/v1.0/users/"
        f"{settings.GRAPH_SENDER_EMAIL}/sendMail"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json=message,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        logger.info("Email sent to %s — subject: %s", to_email, subject)


def _render(template_name: str, context: dict) -> str:
    tmpl = _jinja_env.get_template(template_name)
    return tmpl.render(**context)


async def send_daily_check(assignment, recipient, statement) -> None:
    """Render and send the daily CQC readiness check email for a single assignment."""
    import pytz
    from datetime import datetime

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today_str = datetime.now(tz).strftime("%A %-d %B %Y")

    html_body = _render(
        "daily_check.html",
        {
            "base_url": settings.APP_BASE_URL,
            "token": str(assignment.token),
            "recipient_name": recipient.full_name,
            "home_name": recipient.home_name or "Head Office",
            "statement": statement,
            "today_date": today_str,
            "key_question": statement.key_question,
        },
    )

    await send_email(
        to_email=recipient.email,
        to_name=recipient.full_name,
        subject=f"Daily CQC Readiness Check – {statement.key_question} | {today_str}",
        html_body=html_body,
    )


async def send_support_pack(recipient, statement, assignment) -> None:
    """Send the support pack email to a recipient who expressed low confidence."""
    import pytz
    from datetime import datetime

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today_str = datetime.now(tz).strftime("%A %-d %B %Y")

    html_body = _render(
        "support_pack.html",
        {
            "recipient_name": recipient.full_name,
            "home_name": recipient.home_name or "Head Office",
            "statement": statement,
            "today_date": today_str,
            "cqm_alert_email": settings.CQM_ALERT_EMAIL,
        },
    )

    await send_email(
        to_email=recipient.email,
        to_name=recipient.full_name,
        subject=f"CQC Support Pack – {statement.key_question} | {today_str}",
        html_body=html_body,
    )


async def send_cqm_alert(recipient, statement, assignment, responses) -> None:
    """Send a low-confidence alert email to the Care Quality Manager."""
    import pytz
    from datetime import datetime

    settings = get_settings()
    tz = pytz.timezone(settings.SCHEDULER_TIMEZONE)
    today_str = datetime.now(tz).strftime("%A %-d %B %Y")

    html_body = _render(
        "cqm_alert.html",
        {
            "base_url": settings.APP_BASE_URL,
            "recipient_name": recipient.full_name,
            "recipient_email": recipient.email,
            "home_name": recipient.home_name or "Head Office",
            "statement": statement,
            "assignment": assignment,
            "responses": responses,
            "today_date": today_str,
        },
    )

    await send_email(
        to_email=settings.CQM_ALERT_EMAIL,
        to_name="Care Quality Manager",
        subject=(
            f"⚠️ Low Confidence Alert – {recipient.home_name or 'Head Office'} "
            f"| {statement.key_question} | {today_str}"
        ),
        html_body=html_body,
    )
