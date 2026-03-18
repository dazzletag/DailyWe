"""
Tests for email template rendering and the Graph API email service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

pytestmark = pytest.mark.asyncio

import os

_EMAIL_TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "app", "templates", "email"
)

_jinja_env = Environment(
    loader=FileSystemLoader(_EMAIL_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, context: dict) -> str:
    tmpl = _jinja_env.get_template(template_name)
    return tmpl.render(**context)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _mock_statement(
    key_question: str = "Safe",
    role_group: str = "manager",
    text: str = "We manage medicines safely.",
    evidence_types: list = None,
    guidance_notes: str = "Guidance text here.",
    inspection_tips: str = "Inspection tip here.",
) -> MagicMock:
    s = MagicMock()
    s.key_question = key_question
    s.role_group = role_group
    s.statement_text = text
    s.evidence_types = evidence_types or ["MAR charts", "Medication audits"]
    s.guidance_notes = guidance_notes
    s.inspection_tips = inspection_tips
    return s


def _mock_recipient(
    name: str = "Sarah Mitchell",
    email: str = "sarah@example.com",
    home: str = "Sunrise House",
) -> MagicMock:
    r = MagicMock()
    r.full_name = name
    r.email = email
    r.home_name = home
    return r


def _mock_assignment(token: str = None) -> MagicMock:
    a = MagicMock()
    a.token = token or str(uuid.uuid4())
    a.assignment_date = datetime.now(timezone.utc).date()
    return a


def _mock_response(question_num: int, answer: str) -> MagicMock:
    r = MagicMock()
    r.question_num = question_num
    r.answer = answer
    return r


# ── daily_check.html ──────────────────────────────────────────────────────────

class TestDailyCheckTemplate:
    def test_renders_without_error(self):
        """Template should render given valid context."""
        token = str(uuid.uuid4())
        html = _render(
            "daily_check.html",
            {
                "base_url": "http://localhost:8000",
                "token": token,
                "recipient_name": "Sarah Mitchell",
                "home_name": "Sunrise House",
                "statement": _mock_statement(),
                "today_date": "Monday 18 March 2026",
                "key_question": "Safe",
            },
        )
        assert len(html) > 100
        assert "Sarah Mitchell" in html

    def test_contains_token_urls(self):
        """All three question button URLs must include the token."""
        token = str(uuid.uuid4())
        html = _render(
            "daily_check.html",
            {
                "base_url": "http://localhost:8000",
                "token": token,
                "recipient_name": "David Okafor",
                "home_name": "Meadowbrook Lodge",
                "statement": _mock_statement(key_question="Effective"),
                "today_date": "Tuesday 19 March 2026",
                "key_question": "Effective",
            },
        )
        # All 3 questions × 3 answers = 9 links with the token
        assert html.count(token) >= 9

    def test_contains_all_three_answer_links(self):
        """Each question should have confident, partly, and not_confident links."""
        token = str(uuid.uuid4())
        html = _render(
            "daily_check.html",
            {
                "base_url": "http://localhost:8000",
                "token": token,
                "recipient_name": "Test User",
                "home_name": "Test Home",
                "statement": _mock_statement(),
                "today_date": "Monday 18 March 2026",
                "key_question": "Safe",
            },
        )
        for q in [1, 2, 3]:
            assert f"/q/{q}/confident" in html
            assert f"/q/{q}/partly" in html
            assert f"/q/{q}/not_confident" in html

    def test_key_question_badge_present(self):
        """The key question badge should appear in the header."""
        html = _render(
            "daily_check.html",
            {
                "base_url": "http://localhost:8000",
                "token": str(uuid.uuid4()),
                "recipient_name": "Test User",
                "home_name": "Test Home",
                "statement": _mock_statement(key_question="Well-led"),
                "today_date": "Monday 18 March 2026",
                "key_question": "Well-led",
            },
        )
        assert "Well-led" in html or "WELL-LED" in html


# ── support_pack.html ─────────────────────────────────────────────────────────

class TestSupportPackTemplate:
    def test_renders_without_error(self):
        html = _render(
            "support_pack.html",
            {
                "recipient_name": "Sarah Mitchell",
                "home_name": "Sunrise House",
                "statement": _mock_statement(),
                "today_date": "Monday 18 March 2026",
                "cqm_alert_email": "cqm@example.com",
            },
        )
        assert len(html) > 100
        assert "Sarah Mitchell" in html

    def test_evidence_types_list_rendered(self):
        """All evidence types should appear as checklist items."""
        evidence = ["MAR charts", "Medication audits", "Controlled drug register"]
        html = _render(
            "support_pack.html",
            {
                "recipient_name": "Test User",
                "home_name": "Test Home",
                "statement": _mock_statement(evidence_types=evidence),
                "today_date": "Monday 18 March 2026",
                "cqm_alert_email": "cqm@example.com",
            },
        )
        for item in evidence:
            assert item in html

    def test_guidance_notes_rendered(self):
        """Guidance notes should appear in the 'What Good Looks Like' section."""
        html = _render(
            "support_pack.html",
            {
                "recipient_name": "Test User",
                "home_name": "Test Home",
                "statement": _mock_statement(guidance_notes="Specific guidance text ABC123."),
                "today_date": "Monday 18 March 2026",
                "cqm_alert_email": "cqm@example.com",
            },
        )
        assert "Specific guidance text ABC123" in html

    def test_inspection_tips_rendered(self):
        """Inspection tips should appear in the tips section."""
        html = _render(
            "support_pack.html",
            {
                "recipient_name": "Test User",
                "home_name": "Test Home",
                "statement": _mock_statement(inspection_tips="Unique tip XYZ789."),
                "today_date": "Monday 18 March 2026",
                "cqm_alert_email": "cqm@example.com",
            },
        )
        assert "Unique tip XYZ789" in html


# ── cqm_alert.html ────────────────────────────────────────────────────────────

class TestCQMAlertTemplate:
    def test_renders_without_error(self):
        responses = [
            _mock_response(1, "confident"),
            _mock_response(2, "partly"),
            _mock_response(3, "not_confident"),
        ]
        html = _render(
            "cqm_alert.html",
            {
                "base_url": "http://localhost:8000",
                "recipient_name": "Sarah Mitchell",
                "recipient_email": "sarah@example.com",
                "home_name": "Sunrise House",
                "statement": _mock_statement(),
                "assignment": _mock_assignment(),
                "responses": responses,
                "today_date": "Monday 18 March 2026",
            },
        )
        assert len(html) > 100

    def test_response_summary_table_present(self):
        """All three responses should appear in the summary table."""
        responses = [
            _mock_response(1, "confident"),
            _mock_response(2, "partly"),
            _mock_response(3, "not_confident"),
        ]
        html = _render(
            "cqm_alert.html",
            {
                "base_url": "http://localhost:8000",
                "recipient_name": "Test User",
                "recipient_email": "test@example.com",
                "home_name": "Test Home",
                "statement": _mock_statement(),
                "assignment": _mock_assignment(),
                "responses": responses,
                "today_date": "Monday 18 March 2026",
            },
        )
        assert "Confident" in html
        assert "Partly Confident" in html
        assert "Not Confident" in html

    def test_dashboard_button_link_present(self):
        """The 'View Dashboard' button should link to /admin/alerts."""
        html = _render(
            "cqm_alert.html",
            {
                "base_url": "http://localhost:8000",
                "recipient_name": "Test User",
                "recipient_email": "test@example.com",
                "home_name": "Test Home",
                "statement": _mock_statement(),
                "assignment": _mock_assignment(),
                "responses": [_mock_response(1, "partly")],
                "today_date": "Monday 18 March 2026",
            },
        )
        assert "/admin/alerts" in html


# ── Graph API mock ────────────────────────────────────────────────────────────

class TestGraphAPIEmailService:
    async def test_send_email_calls_graph_api(self):
        """send_email should POST to the Graph API sendMail endpoint."""
        from app.services.email import send_email

        with patch("app.services.email.get_access_token", new_callable=AsyncMock) as mock_token, \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_token.return_value = "fake-access-token"

            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await send_email(
                to_email="test@example.com",
                to_name="Test User",
                subject="Test Subject",
                html_body="<p>Hello</p>",
            )

            assert mock_client.post.called
            call_args = mock_client.post.call_args
            assert "sendMail" in call_args[0][0] or "sendMail" in str(call_args)

    async def test_get_access_token_posts_to_token_endpoint(self):
        """get_access_token should POST to the Microsoft identity token endpoint."""
        from app.services.email import get_access_token

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"access_token": "test-token-abc"})

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            token = await get_access_token()

        assert token == "test-token-abc"
        called_url = mock_client.post.call_args[0][0]
        assert "oauth2/v2.0/token" in called_url
