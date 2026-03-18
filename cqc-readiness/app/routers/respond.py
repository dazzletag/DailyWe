from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.response import QUESTION_TEXT, VALID_ANSWERS, VALID_QUESTION_NUMS, Response
from app.services.response_handler import handle_completion
from app.services.token import is_token_valid, lookup_assignment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["respond"])

import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "web")
templates = Jinja2Templates(directory=_TEMPLATE_DIR)

# Answer display labels
ANSWER_LABELS = {
    "confident": "Confident",
    "partly": "Partly Confident",
    "not_confident": "Not Confident",
}

ANSWER_COLOURS = {
    "confident": "#2E7D32",
    "partly": "#F57C00",
    "not_confident": "#C62828",
}

# Tooltip hints shown next to each question on the response form
QUESTION_HINTS = {
    1: (
        "To build confidence: Read the CQC guidance for this statement. "
        "Discuss with your team what it means in practice for your home. "
        "Ask your Care Quality Manager if anything is unclear."
    ),
    2: (
        "To build confidence: Walk your home and observe practice against this standard. "
        "Review recent care plans, audits, and resident or family feedback. "
        "Talk to staff about how they apply this in their daily work."
    ),
    3: (
        "To build confidence: Identify the specific documents or records that evidence this standard. "
        "Check they are current, complete, and easy to find. "
        "Upload key evidence to your CQC tool so it is ready for inspection."
    ),
}

# Evidence hints shown per CQC key question on the response form
KEY_QUESTION_EVIDENCE = {
    "Safe": (
        "Evidence to upload to your CQC tool: risk assessments, incident & accident logs, "
        "medication records & MAR charts, safeguarding training records, DBS log, "
        "fire safety & evacuation records, infection control audits, lone-working policies."
    ),
    "Effective": (
        "Evidence to upload to your CQC tool: care plans & reviews, staff training matrix, "
        "supervision & appraisal records, MCA & DoLS documentation, multi-disciplinary meeting "
        "notes, nutrition & hydration records, outcome-based care assessments."
    ),
    "Caring": (
        "Evidence to upload to your CQC tool: resident & family satisfaction surveys, "
        "compliment & complaint records, dignity and respect training logs, "
        "activity & wellbeing records, person-centred care plan examples, "
        "staff communication records with families."
    ),
    "Responsive": (
        "Evidence to upload to your CQC tool: care plan reviews showing responsiveness to change, "
        "complaints handling records & outcomes, dependency assessments, specialist referrals, "
        "equipment provision records, end-of-life care plans, service user involvement records."
    ),
    "Well-led": (
        "Evidence to upload to your CQC tool: staff meeting minutes, quality audit reports, "
        "governance & oversight documentation, CQC action plans, staff survey results, "
        "manager walk-around notes, whistleblowing policy & logs, team development records."
    ),
}


@router.get("/respond/{token}", response_class=HTMLResponse)
async def respond_form(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Show the full response form for a daily check."""
    try:
        token_uuid = uuid.UUID(token)
    except ValueError:
        return templates.TemplateResponse("expired.html", {"request": request})

    assignment = await lookup_assignment(token_uuid, db)
    if assignment is None:
        return templates.TemplateResponse("expired.html", {"request": request})

    if not is_token_valid(assignment):
        return templates.TemplateResponse("expired.html", {"request": request})

    recipient = assignment.recipient
    statement = assignment.statement
    answered = {r.question_num: r.answer for r in assignment.responses}

    if len(answered) >= 3:
        return templates.TemplateResponse(
            "complete.html",
            {
                "request": request,
                "recipient_name": recipient.full_name,
                "home_name": recipient.home_name or "Head Office",
                "statement": statement,
                "answer_summary": [
                    {
                        "question_num": q,
                        "question_text": QUESTION_TEXT[q],
                        "answer": ans,
                        "answer_label": ANSWER_LABELS.get(ans, ans),
                        "colour": ANSWER_COLOURS.get(ans, "#666"),
                    }
                    for q, ans in sorted(answered.items())
                ],
                "all_confident": all(a == "confident" for a in answered.values()),
                "alert_raised": False,
            },
        )

    questions = [
        {"num": q, "text": QUESTION_TEXT[q], "hint": QUESTION_HINTS[q]}
        for q in (1, 2, 3)
    ]

    return templates.TemplateResponse(
        "respond_form.html",
        {
            "request": request,
            "token": token,
            "recipient": recipient,
            "statement": statement,
            "questions": questions,
            "answered": answered,
            "evidence_hint": KEY_QUESTION_EVIDENCE.get(statement.key_question, ""),
            "answer_labels": ANSWER_LABELS,
            "answer_colours": ANSWER_COLOURS,
        },
    )


@router.get("/respond/{token}/q/{question_num}/{answer}", response_class=HTMLResponse)
async def record_response(
    token: str,
    question_num: int,
    answer: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a single question response from a daily check email link.

    Path parameters
    ---------------
    token       : UUID embedded in the email link
    question_num: 1, 2, or 3
    answer      : 'confident', 'partly', or 'not_confident'
    """

    # ------------------------------------------------------------------
    # 1. Validate answer value
    # ------------------------------------------------------------------
    if answer not in VALID_ANSWERS:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Invalid Answer",
                "error_message": (
                    f"'{answer}' is not a valid answer. "
                    f"Please use one of: {', '.join(VALID_ANSWERS)}."
                ),
            },
            status_code=422,
        )

    # ------------------------------------------------------------------
    # 2. Validate question number
    # ------------------------------------------------------------------
    if question_num not in VALID_QUESTION_NUMS:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Invalid Question",
                "error_message": (
                    f"Question number {question_num} is not valid. "
                    f"Questions are numbered 1 to 3."
                ),
            },
            status_code=422,
        )

    # ------------------------------------------------------------------
    # 3. Parse token UUID
    # ------------------------------------------------------------------
    try:
        token_uuid = uuid.UUID(token)
    except ValueError:
        return templates.TemplateResponse(
            "expired.html",
            {"request": request},
            status_code=200,
        )

    # ------------------------------------------------------------------
    # 4. Look up assignment
    # ------------------------------------------------------------------
    assignment = await lookup_assignment(token_uuid, db)
    if assignment is None:
        logger.warning("Token not found: %s", token)
        return templates.TemplateResponse(
            "expired.html",
            {"request": request},
            status_code=200,
        )

    # ------------------------------------------------------------------
    # 5. Check token is valid (today's date)
    # ------------------------------------------------------------------
    if not is_token_valid(assignment):
        logger.info(
            "Expired token used: %s (assignment_date=%s)",
            token,
            assignment.assignment_date,
        )
        return templates.TemplateResponse(
            "expired.html",
            {"request": request},
            status_code=200,
        )

    recipient = assignment.recipient
    statement = assignment.statement

    # ------------------------------------------------------------------
    # 6. Check if this question has already been answered
    # ------------------------------------------------------------------
    existing_for_question = next(
        (r for r in assignment.responses if r.question_num == question_num),
        None,
    )
    if existing_for_question is not None:
        logger.info(
            "Duplicate answer attempt: assignment=%s question=%s",
            assignment.id,
            question_num,
        )
        return templates.TemplateResponse(
            "already_answered.html",
            {
                "request": request,
                "recipient_name": recipient.full_name,
                "question_num": question_num,
                "question_text": QUESTION_TEXT[question_num],
                "previous_answer": ANSWER_LABELS.get(
                    existing_for_question.answer, existing_for_question.answer
                ),
            },
            status_code=200,
        )

    # ------------------------------------------------------------------
    # 7. Record the response
    # ------------------------------------------------------------------
    client_ip = request.client.host if request.client else None
    new_response = Response(
        assignment_id=assignment.id,
        question_num=question_num,
        answer=answer,
        respondent_ip=client_ip,
        answered_at=datetime.now(timezone.utc),
    )
    db.add(new_response)
    await db.flush()

    # Reload all responses for this assignment (including the new one)
    all_responses = list(assignment.responses) + [new_response]
    answered_questions = {r.question_num for r in all_responses}

    # ------------------------------------------------------------------
    # 8. Check if all 3 questions answered
    # ------------------------------------------------------------------
    if len(answered_questions) >= 3:
        # All done — run completion handler
        alert_raised = await handle_completion(assignment, all_responses, db)
        await db.commit()

        # Build answer summary for the complete page
        answer_summary = []
        for q in sorted(all_responses, key=lambda r: r.question_num):
            answer_summary.append(
                {
                    "question_num": q.question_num,
                    "question_text": QUESTION_TEXT[q.question_num],
                    "answer": q.answer,
                    "answer_label": ANSWER_LABELS.get(q.answer, q.answer),
                    "colour": ANSWER_COLOURS.get(q.answer, "#666"),
                }
            )

        return templates.TemplateResponse(
            "complete.html",
            {
                "request": request,
                "recipient_name": recipient.full_name,
                "home_name": recipient.home_name or "Head Office",
                "statement": statement,
                "answer_summary": answer_summary,
                "all_confident": not alert_raised,
                "alert_raised": alert_raised,
            },
            status_code=200,
        )

    # Not yet complete — redirect back to the form to answer remaining questions
    await db.commit()
    return RedirectResponse(f"/respond/{token}", status_code=303)
