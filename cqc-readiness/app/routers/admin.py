from __future__ import annotations

import csv
import io
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response as FastAPIResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.alert import CQMAlert
from app.models.assignment import DailyAssignment
from app.models.recipient import Recipient
from app.models.response import Response as ResponseModel
from app.models.statement import WeStatement

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "web")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)


def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Auth credentials against settings."""
    settings = get_settings()
    username_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.ADMIN_USERNAME.encode("utf-8"),
    )
    try:
        password_ok = pwd_context.verify(credentials.password, settings.ADMIN_PASSWORD_HASH)
    except Exception:
        password_ok = False

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    msg: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Admin dashboard with completion stats, confidence breakdown, and open alerts."""
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    thirty_days_ago = today - timedelta(days=30)

    # ------------------------------------------------------------------
    # Completion rate this week
    # ------------------------------------------------------------------
    total_this_week_result = await db.execute(
        select(func.count(DailyAssignment.id)).where(
            DailyAssignment.assignment_date >= week_start
        )
    )
    total_this_week = total_this_week_result.scalar_one() or 0

    completed_this_week_result = await db.execute(
        select(func.count(DailyAssignment.id)).where(
            DailyAssignment.assignment_date >= week_start,
            DailyAssignment.completed_at.is_not(None),
        )
    )
    completed_this_week = completed_this_week_result.scalar_one() or 0

    completion_rate = (
        round(completed_this_week / total_this_week * 100)
        if total_this_week > 0
        else 0
    )

    # ------------------------------------------------------------------
    # Confidence by key question (last 30 days)
    # ------------------------------------------------------------------
    kq_rows = await db.execute(
        select(
            WeStatement.key_question,
            ResponseModel.answer,
            func.count(ResponseModel.id).label("cnt"),
        )
        .join(DailyAssignment, ResponseModel.assignment_id == DailyAssignment.id)
        .join(WeStatement, DailyAssignment.statement_id == WeStatement.id)
        .where(DailyAssignment.assignment_date >= thirty_days_ago)
        .group_by(WeStatement.key_question, ResponseModel.answer)
    )
    kq_raw = kq_rows.all()

    key_question_stats: dict[str, dict] = {}
    for kq, ans, cnt in kq_raw:
        if kq not in key_question_stats:
            key_question_stats[kq] = {"confident": 0, "partly": 0, "not_confident": 0, "total": 0}
        key_question_stats[kq][ans] = key_question_stats[kq].get(ans, 0) + cnt
        key_question_stats[kq]["total"] += cnt

    for kq, stats in key_question_stats.items():
        t = stats["total"]
        stats["confident_pct"] = round(stats["confident"] / t * 100) if t else 0
        stats["partly_pct"] = round(stats["partly"] / t * 100) if t else 0
        stats["not_confident_pct"] = round(stats["not_confident"] / t * 100) if t else 0

    # ------------------------------------------------------------------
    # Open alerts grouped by home
    # ------------------------------------------------------------------
    open_alerts_result = await db.execute(
        select(
            CQMAlert.home_name,
            func.count(CQMAlert.id).label("count"),
        )
        .where(CQMAlert.is_resolved.is_(False))
        .group_by(CQMAlert.home_name)
        .order_by(func.count(CQMAlert.id).desc())
    )
    open_alerts_by_home = [
        {"home_name": row.home_name or "Head Office", "count": row.count}
        for row in open_alerts_result.all()
    ]

    total_open_alerts = sum(h["count"] for h in open_alerts_by_home)

    # ------------------------------------------------------------------
    # Top 5 weakest We Statements (most low-confidence answers, last 30 days)
    # ------------------------------------------------------------------
    weak_result = await db.execute(
        select(
            WeStatement.statement_text,
            WeStatement.key_question,
            func.count(ResponseModel.id).label("low_count"),
        )
        .join(DailyAssignment, ResponseModel.assignment_id == DailyAssignment.id)
        .join(WeStatement, DailyAssignment.statement_id == WeStatement.id)
        .where(
            DailyAssignment.assignment_date >= thirty_days_ago,
            ResponseModel.answer.in_(["partly", "not_confident"]),
        )
        .group_by(WeStatement.id, WeStatement.statement_text, WeStatement.key_question)
        .order_by(func.count(ResponseModel.id).desc())
        .limit(5)
    )
    weak_statements = [
        {
            "statement_text": row.statement_text[:80] + "..."
            if len(row.statement_text) > 80
            else row.statement_text,
            "key_question": row.key_question,
            "low_count": row.low_count,
        }
        for row in weak_result.all()
    ]

    # ------------------------------------------------------------------
    # Last 20 completions
    # ------------------------------------------------------------------
    recent_result = await db.execute(
        select(DailyAssignment, Recipient, WeStatement)
        .join(Recipient, DailyAssignment.recipient_id == Recipient.id)
        .join(WeStatement, DailyAssignment.statement_id == WeStatement.id)
        .where(DailyAssignment.completed_at.is_not(None))
        .order_by(DailyAssignment.completed_at.desc())
        .limit(20)
    )
    recent_completions = [
        {
            "date": a.assignment_date,
            "recipient_name": r.full_name,
            "home_name": r.home_name or "Head Office",
            "key_question": s.key_question,
            "statement_snippet": s.statement_text[:60] + "..." if len(s.statement_text) > 60 else s.statement_text,
            "completed_at": a.completed_at,
        }
        for a, r, s in recent_result.all()
    ]

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin_username": _admin,
            "total_this_week": total_this_week,
            "completed_this_week": completed_this_week,
            "completion_rate": completion_rate,
            "key_question_stats": key_question_stats,
            "open_alerts_by_home": open_alerts_by_home,
            "total_open_alerts": total_open_alerts,
            "weak_statements": weak_statements,
            "recent_completions": recent_completions,
            "week_start": week_start,
            "today": today,
            "msg": msg,
        },
    )


@router.get("/alerts", response_class=HTMLResponse)
async def list_alerts(
    request: Request,
    home_name: str | None = None,
    key_question: str | None = None,
    resolved: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """List all CQM alerts with optional filters."""
    query = select(CQMAlert).order_by(CQMAlert.created_at.desc())

    if home_name:
        query = query.where(CQMAlert.home_name == home_name)
    if key_question:
        query = query.where(CQMAlert.key_question == key_question)
    if resolved == "true":
        query = query.where(CQMAlert.is_resolved.is_(True))
    elif resolved == "false" or resolved is None:
        query = query.where(CQMAlert.is_resolved.is_(False))

    result = await db.execute(query)
    alerts = result.scalars().all()

    # Filter options
    homes_result = await db.execute(
        select(CQMAlert.home_name).distinct().order_by(CQMAlert.home_name)
    )
    available_homes = [h for h in homes_result.scalars().all() if h]

    return templates.TemplateResponse(
        "admin/alerts.html",
        {
            "request": request,
            "admin_username": _admin,
            "alerts": alerts,
            "filter_home": home_name,
            "filter_key_question": key_question,
            "filter_resolved": resolved,
            "available_homes": available_homes,
            "key_questions": ["Safe", "Effective", "Caring", "Responsive", "Well-led"],
        },
    )


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Mark a CQM alert as resolved."""
    result = await db.execute(select(CQMAlert).where(CQMAlert.id == alert_id))
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.is_resolved:
        raise HTTPException(status_code=400, detail="Alert is already resolved")

    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = _admin
    await db.commit()

    return {"status": "resolved", "alert_id": alert_id}


@router.get("/alerts/export")
async def export_alerts_csv(
    home_name: str | None = None,
    key_question: str | None = None,
    resolved: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Export filtered alerts to CSV."""
    query = select(CQMAlert).order_by(CQMAlert.created_at.desc())

    if home_name:
        query = query.where(CQMAlert.home_name == home_name)
    if key_question:
        query = query.where(CQMAlert.key_question == key_question)
    if resolved == "true":
        query = query.where(CQMAlert.is_resolved.is_(True))
    elif resolved == "false":
        query = query.where(CQMAlert.is_resolved.is_(False))

    result = await db.execute(query)
    alerts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Created At", "Home", "Key Question", "Recipient",
        "Recipient Email", "Statement (excerpt)", "Trigger",
        "Resolved", "Resolved At", "Resolved By",
    ])

    for a in alerts:
        writer.writerow([
            a.id,
            a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            a.home_name or "",
            a.key_question,
            a.recipient_name,
            a.recipient_email,
            a.statement_text[:100],
            a.trigger_summary or "",
            "Yes" if a.is_resolved else "No",
            a.resolved_at.strftime("%Y-%m-%d %H:%M") if a.resolved_at else "",
            a.resolved_by or "",
        ])

    output.seek(0)
    filename = f"cqm_alerts_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Manual send-now trigger
# ---------------------------------------------------------------------------

@router.post("/send-now")
async def send_now(
    _admin: str = Depends(get_current_admin),
):
    """Manually trigger the daily email job (for testing)."""
    from app.services.scheduler import _run_daily_job
    try:
        await _run_daily_job()
        return RedirectResponse("/admin/dashboard?msg=sent", status_code=303)
    except Exception as exc:
        logger.error("Manual send-now failed: %s", exc, exc_info=True)
        return RedirectResponse("/admin/dashboard?msg=error", status_code=303)


# ---------------------------------------------------------------------------
# Recipients management
# ---------------------------------------------------------------------------

ROLES = ["HomeManager", "DeputyManager", "OperationsManager", "CareQualityManager"]


@router.get("/recipients", response_class=HTMLResponse)
async def list_recipients(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    result = await db.execute(
        select(Recipient).order_by(Recipient.home_name.nulls_last(), Recipient.full_name)
    )
    recipients = result.scalars().all()
    return templates.TemplateResponse(
        "admin/recipients.html",
        {"request": request, "admin_username": _admin, "recipients": recipients, "roles": ROLES},
    )


@router.get("/recipients/new", response_class=HTMLResponse)
async def new_recipient_form(
    request: Request,
    _admin: str = Depends(get_current_admin),
):
    return templates.TemplateResponse(
        "admin/recipient_form.html",
        {"request": request, "admin_username": _admin, "roles": ROLES, "recipient": None, "error": None},
    )


@router.post("/recipients/new")
async def create_recipient(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    home_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    email = email.strip().lower()
    existing = await db.execute(select(Recipient).where(Recipient.email == email))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            "admin/recipient_form.html",
            {
                "request": request,
                "admin_username": _admin,
                "roles": ROLES,
                "recipient": None,
                "error": f"A recipient with email {email} already exists.",
                "form": {"full_name": full_name, "email": email, "role": role, "home_name": home_name},
            },
            status_code=400,
        )
    db.add(Recipient(
        full_name=full_name.strip(),
        email=email,
        role=role,
        home_name=home_name.strip() or None,
        is_active=True,
    ))
    await db.commit()
    return RedirectResponse("/admin/recipients", status_code=303)


@router.get("/recipients/{recipient_id}/edit", response_class=HTMLResponse)
async def edit_recipient_form(
    recipient_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    result = await db.execute(select(Recipient).where(Recipient.id == recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return templates.TemplateResponse(
        "admin/recipient_form.html",
        {"request": request, "admin_username": _admin, "roles": ROLES, "recipient": recipient, "error": None},
    )


@router.post("/recipients/{recipient_id}/edit")
async def update_recipient(
    recipient_id: int,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    home_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    result = await db.execute(select(Recipient).where(Recipient.id == recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    email = email.strip().lower()
    clash = await db.execute(
        select(Recipient).where(Recipient.email == email, Recipient.id != recipient_id)
    )
    if clash.scalar_one_or_none():
        return templates.TemplateResponse(
            "admin/recipient_form.html",
            {
                "request": request,
                "admin_username": _admin,
                "roles": ROLES,
                "recipient": recipient,
                "error": f"Another recipient already uses {email}.",
                "form": {"full_name": full_name, "email": email, "role": role, "home_name": home_name},
            },
            status_code=400,
        )

    recipient.full_name = full_name.strip()
    recipient.email = email
    recipient.role = role
    recipient.home_name = home_name.strip() or None
    await db.commit()
    return RedirectResponse("/admin/recipients", status_code=303)


@router.post("/recipients/{recipient_id}/toggle")
async def toggle_recipient(
    recipient_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    result = await db.execute(select(Recipient).where(Recipient.id == recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    recipient.is_active = not recipient.is_active
    await db.commit()
    return RedirectResponse("/admin/recipients", status_code=303)


@router.post("/clear-test-data")
async def clear_test_data(
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    """Delete all responses, assignments, and alerts (for testing resets)."""
    from sqlalchemy import delete
    await db.execute(delete(ResponseModel))
    await db.execute(delete(CQMAlert))
    await db.execute(delete(DailyAssignment))
    await db.commit()
    logger.info("Test data cleared by %s", _admin)
    return RedirectResponse("/admin/dashboard?msg=cleared", status_code=303)


@router.post("/recipients/{recipient_id}/delete")
async def delete_recipient(
    recipient_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_current_admin),
):
    result = await db.execute(select(Recipient).where(Recipient.id == recipient_id))
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    await db.delete(recipient)
    await db.commit()
    return RedirectResponse("/admin/recipients", status_code=303)
