from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import CQMAlert
from app.models.assignment import DailyAssignment
from app.models.response import Response

logger = logging.getLogger(__name__)

# Answers that indicate low confidence and should trigger support actions
LOW_CONFIDENCE_ANSWERS = {"partly", "not_confident"}


def _build_trigger_summary(responses: list[Response]) -> str:
    """Build a human-readable summary of which responses triggered the alert."""
    parts = []
    for r in sorted(responses, key=lambda x: x.question_num):
        if r.answer in LOW_CONFIDENCE_ANSWERS:
            label = r.answer.replace("_", " ")
            parts.append(f"Q{r.question_num}: {label}")
    return ", ".join(parts)


async def handle_completion(
    assignment: DailyAssignment,
    responses: list[Response],
    db: AsyncSession,
) -> bool:
    """
    Called when all 3 questions have been answered.

    Returns True if a low-confidence alert was raised, False if all confident.

    Side-effects:
    - Marks assignment.completed_at
    - If any low-confidence answers: creates CQMAlert, sends support pack and CQM alert emails
    - Commits nothing — caller must commit the session
    """
    # Mark the assignment as completed
    assignment.completed_at = datetime.now(timezone.utc)

    low_confidence = [r for r in responses if r.answer in LOW_CONFIDENCE_ANSWERS]
    all_confident = len(low_confidence) == 0

    if all_confident:
        logger.info(
            "Assignment %s completed with full confidence (recipient_id=%s)",
            assignment.id,
            assignment.recipient_id,
        )
        return False

    # At least one low-confidence answer — raise an alert
    recipient = assignment.recipient
    statement = assignment.statement

    trigger_summary = _build_trigger_summary(responses)
    logger.warning(
        "Low confidence detected for assignment %s (recipient=%s, home=%s): %s",
        assignment.id,
        recipient.email,
        recipient.home_name,
        trigger_summary,
    )

    alert = CQMAlert(
        assignment_id=assignment.id,
        recipient_name=recipient.full_name,
        recipient_email=recipient.email,
        home_name=recipient.home_name,
        statement_text=statement.statement_text,
        key_question=statement.key_question,
        trigger_summary=trigger_summary,
    )
    db.add(alert)
    await db.flush()

    # Send emails asynchronously — errors are logged but don't break the response
    try:
        from app.services.email import send_support_pack, send_cqm_alert

        await send_support_pack(recipient, statement, assignment)
        await send_cqm_alert(recipient, statement, assignment, responses)
    except Exception as exc:
        logger.error(
            "Failed to send alert emails for assignment %s: %s",
            assignment.id,
            exc,
            exc_info=True,
        )

    return True
