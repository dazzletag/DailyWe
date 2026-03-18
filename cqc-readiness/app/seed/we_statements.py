"""
Seed script: inserts all 30 We Statements into the database.

Run with:
    python -m app.seed.we_statements
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_engine, get_session_factory
from app.models.statement import WeStatement

logger = logging.getLogger(__name__)

WE_STATEMENTS_DATA = [
    # ── SAFE ──────────────────────────────────────────────────────────────────
    {
        "key_question": "Safe",
        "role_group": "manager",
        "statement_text": (
            "We manage medicines safely — people receive their medicines as prescribed, "
            "and records are accurate and up to date."
        ),
        "evidence_types": [
            "MAR charts",
            "Medication audits",
            "Controlled drug register",
            "Staff competency records",
        ],
        "guidance_notes": (
            "Inspectors will scrutinise MAR charts for gaps, late doses, and signatures. "
            "Ensure all stock counts are reconciled and PRN protocols are in place."
        ),
        "inspection_tips": (
            "Inspectors will ask to see a named individual's MAR chart and may ask you "
            "to walk them through it."
        ),
        "sort_order": 1,
    },
    {
        "key_question": "Safe",
        "role_group": "deputy",
        "statement_text": (
            "We safeguard people from abuse and neglect — staff know how to recognise "
            "and report concerns, and we act on them swiftly."
        ),
        "evidence_types": [
            "Safeguarding policy",
            "Training records",
            "Incident logs",
            "Referral evidence",
        ],
        "guidance_notes": (
            "All staff must know the local safeguarding threshold and how to make a "
            "referral. Evidence of prompt action and multi-agency working is key."
        ),
        "inspection_tips": (
            "Be ready to describe a recent safeguarding concern and what you did next."
        ),
        "sort_order": 2,
    },
    {
        "key_question": "Safe",
        "role_group": "manager",
        "statement_text": (
            "We assess and manage risks to people's safety in a personalised way — "
            "risk assessments are current and inform care plans."
        ),
        "evidence_types": [
            "Risk assessments",
            "Care plans",
            "DNAR forms",
            "Falls logs",
        ],
        "guidance_notes": (
            "Risk assessments must be dated, reviewed after incidents, and reflected "
            "in care plans. Generic risk assessments are a red flag."
        ),
        "inspection_tips": (
            "Inspectors may ask to cross-reference a care plan with its risk "
            "assessments for a specific resident."
        ),
        "sort_order": 3,
    },
    {
        "key_question": "Safe",
        "role_group": "deputy",
        "statement_text": (
            "We prevent and control infection effectively — our environment is clean, "
            "and staff follow IPC procedures consistently."
        ),
        "evidence_types": [
            "IPC audit",
            "Cleaning schedules",
            "PPE records",
            "Outbreak management logs",
        ],
        "guidance_notes": (
            "IPC lead must be identifiable. Audits must be acted on. "
            "PPE must be available at point of care."
        ),
        "inspection_tips": (
            "Inspectors may do a walk-round to check environmental cleanliness "
            "and PPE availability."
        ),
        "sort_order": 4,
    },
    {
        "key_question": "Safe",
        "role_group": "manager",
        "statement_text": (
            "We learn when things go wrong — incidents and near-misses are reported, "
            "investigated, and improvements made."
        ),
        "evidence_types": [
            "Incident reports",
            "Learning logs",
            "Team meeting minutes",
            "Policy updates",
        ],
        "guidance_notes": (
            "Learning must be demonstrable: show how an incident led to a change "
            "in practice or policy."
        ),
        "inspection_tips": (
            "Expect questions about a specific incident and what changed as a result."
        ),
        "sort_order": 5,
    },
    {
        "key_question": "Safe",
        "role_group": "deputy",
        "statement_text": (
            "We ensure safe staffing levels — rotas reflect the needs of the people "
            "we support at all times."
        ),
        "evidence_types": [
            "Staffing rotas",
            "Dependency tools",
            "Agency usage logs",
        ],
        "guidance_notes": (
            "Dependency scoring should drive the rota. Agency use must not "
            "compromise continuity of care."
        ),
        "inspection_tips": (
            "Inspectors may ask residents and relatives whether there are enough staff."
        ),
        "sort_order": 6,
    },
    {
        "key_question": "Safe",
        "role_group": "manager",
        "statement_text": (
            "We use equipment safely — aids and assistive technology are maintained, "
            "checked, and used correctly."
        ),
        "evidence_types": [
            "Equipment maintenance logs",
            "LOLER/PUWER records",
            "Moving & handling assessments",
        ],
        "guidance_notes": (
            "All lifting equipment must have a current LOLER certificate. Staff using "
            "hoists must be trained and competency-checked."
        ),
        "inspection_tips": (
            "An inspector may ask to see the LOLER certificate for a specific hoist."
        ),
        "sort_order": 7,
    },
    {
        "key_question": "Safe",
        "role_group": "deputy",
        "statement_text": (
            "We manage and respond to emergencies effectively — staff know what to do "
            "and can act confidently in a crisis."
        ),
        "evidence_types": [
            "Business continuity plan",
            "Fire drill records",
            "Emergency contacts",
            "Staff training records",
        ],
        "guidance_notes": (
            "Fire drills must occur twice yearly including a night drill. "
            "BCP must be reviewed annually."
        ),
        "inspection_tips": (
            "Staff on shift must be able to describe their role in a fire evacuation "
            "without prompting."
        ),
        "sort_order": 8,
    },
    # ── EFFECTIVE ─────────────────────────────────────────────────────────────
    {
        "key_question": "Effective",
        "role_group": "manager",
        "statement_text": (
            "We assess people's needs thoroughly at the start of their care and keep "
            "assessments up to date."
        ),
        "evidence_types": [
            "Pre-admission assessments",
            "Care plan reviews",
            "MDT notes",
        ],
        "guidance_notes": (
            "Admission assessments must be completed before or on the day of admission. "
            "Reviews must be triggered by change in need, not just on a calendar schedule."
        ),
        "inspection_tips": (
            "Inspectors may look for evidence that care plans were updated after a "
            "hospital admission or health change."
        ),
        "sort_order": 9,
    },
    {
        "key_question": "Effective",
        "role_group": "deputy",
        "statement_text": (
            "We ensure staff have the skills, training and knowledge to deliver "
            "effective care."
        ),
        "evidence_types": [
            "Training matrix",
            "Supervision records",
            "Appraisals",
            "Professional registrations",
        ],
        "guidance_notes": (
            "Training matrix must be up to date. Mandatory training must be completed "
            "within required timescales. Supervision should be monthly for new staff."
        ),
        "inspection_tips": (
            "Be prepared to show training compliance figures and describe how gaps "
            "are managed."
        ),
        "sort_order": 10,
    },
    {
        "key_question": "Effective",
        "role_group": "manager",
        "statement_text": (
            "We support people to eat and drink well, in line with their assessed "
            "needs and preferences."
        ),
        "evidence_types": [
            "Nutrition assessments",
            "MUST scores",
            "Food & fluid charts",
            "Menu records",
        ],
        "guidance_notes": (
            "MUST scores must be completed on admission and monthly. Fluid charts "
            "must be completed same-day."
        ),
        "inspection_tips": (
            "Inspectors will look at fluid charts and may ask kitchen staff about "
            "dietary needs."
        ),
        "sort_order": 11,
    },
    {
        "key_question": "Effective",
        "role_group": "deputy",
        "statement_text": (
            "We work with health professionals to ensure people's health needs are met."
        ),
        "evidence_types": [
            "GP referral records",
            "Hospital passports",
            "Medication reviews",
            "Specialist correspondence",
        ],
        "guidance_notes": (
            "Referrals must be timely and followed up. Hospital passports must be "
            "ready to send at all times."
        ),
        "inspection_tips": (
            "Be ready to describe how you escalate a health concern out of hours."
        ),
        "sort_order": 12,
    },
    {
        "key_question": "Effective",
        "role_group": "manager",
        "statement_text": (
            "We support people to live as healthily as possible, including maintaining "
            "independence."
        ),
        "evidence_types": [
            "Wellbeing plans",
            "Activity records",
            "Occupational therapy involvement",
        ],
        "guidance_notes": (
            "Activities must be meaningful and person-centred, not just group "
            "entertainment. Independence in daily living tasks must be supported."
        ),
        "inspection_tips": (
            "Ask a resident about their activities — their experience is the evidence."
        ),
        "sort_order": 13,
    },
    {
        "key_question": "Effective",
        "role_group": "deputy",
        "statement_text": (
            "We follow evidence-based practice — our policies reflect current guidance "
            "and legislation."
        ),
        "evidence_types": [
            "Policy review dates",
            "NICE guideline references",
            "Regulatory update processes",
        ],
        "guidance_notes": (
            "Policies must be reviewed at least annually and aligned to NICE, CQC, "
            "and Skills for Care guidance."
        ),
        "inspection_tips": (
            "Inspectors may ask how you keep up with changes in guidance."
        ),
        "sort_order": 14,
    },
    # ── CARING ────────────────────────────────────────────────────────────────
    {
        "key_question": "Caring",
        "role_group": "manager",
        "statement_text": (
            "We treat people with kindness, dignity and respect at all times — "
            "including in how we speak about them."
        ),
        "evidence_types": [
            "Dignity audits",
            "Care plan language review",
            "Observation records",
            "Feedback forms",
        ],
        "guidance_notes": (
            "Care plan language must be respectful and person-centred. Observations "
            "of care practice are the strongest evidence."
        ),
        "inspection_tips": (
            "Inspectors will observe interactions between staff and residents "
            "throughout their visit."
        ),
        "sort_order": 15,
    },
    {
        "key_question": "Caring",
        "role_group": "deputy",
        "statement_text": (
            "We involve people in decisions about their care and support them to "
            "understand their choices."
        ),
        "evidence_types": [
            "Care plan sign-off",
            "Best interest meeting records",
            "Mental Capacity Act documentation",
        ],
        "guidance_notes": (
            "MCA assessments must be decision-specific and time-specific. Best "
            "interest decisions must involve the person as far as possible."
        ),
        "inspection_tips": (
            "Be ready to walk through a best interest decision and explain who "
            "was involved."
        ),
        "sort_order": 16,
    },
    {
        "key_question": "Caring",
        "role_group": "manager",
        "statement_text": (
            "We respect people's privacy — including in personal care, communications, "
            "and record keeping."
        ),
        "evidence_types": [
            "Privacy policies",
            "Room observation notes",
            "Confidentiality training records",
        ],
        "guidance_notes": (
            "Doors must be closed during personal care. Records must be stored "
            "securely. Conversations about residents must not occur in public areas."
        ),
        "inspection_tips": (
            "Inspectors may check whether care records are visible in communal areas."
        ),
        "sort_order": 17,
    },
    {
        "key_question": "Caring",
        "role_group": "deputy",
        "statement_text": (
            "We provide compassionate end-of-life care that respects each person's "
            "wishes."
        ),
        "evidence_types": [
            "RESPECT/DNACPR forms",
            "End-of-life care plans",
            "Staff training",
            "Gold Standards Framework evidence",
        ],
        "guidance_notes": (
            "EOL care plans must reflect the person's wishes documented when they "
            "were able to express them. Anticipatory medicines must be in place."
        ),
        "inspection_tips": (
            "Inspectors will review EOL care plans and may speak with recently "
            "bereaved relatives."
        ),
        "sort_order": 18,
    },
    {
        "key_question": "Caring",
        "role_group": "manager",
        "statement_text": (
            "We support people to maintain important relationships and connections "
            "with family and community."
        ),
        "evidence_types": [
            "Visitor records",
            "Activity logs",
            "Communication plans",
            "Family feedback",
        ],
        "guidance_notes": (
            "Visiting must be encouraged and facilitated. Digital communication "
            "support should be available for those who want it."
        ),
        "inspection_tips": (
            "Inspectors may ask residents and families about their experience of "
            "visiting and involvement."
        ),
        "sort_order": 19,
    },
    # ── RESPONSIVE ────────────────────────────────────────────────────────────
    {
        "key_question": "Responsive",
        "role_group": "deputy",
        "statement_text": (
            "We provide personalised care — each person's care reflects their "
            "individual needs, history, and preferences."
        ),
        "evidence_types": [
            "Life history documents",
            "Person-centred care plans",
            "One-page profiles",
        ],
        "guidance_notes": (
            "One-page profiles must be visible to all staff, not buried in care "
            "records. Life history must actively inform care."
        ),
        "inspection_tips": (
            "Ask a staff member what they know about a resident's life before care "
            "— their answer shows whether personalisation is real."
        ),
        "sort_order": 20,
    },
    {
        "key_question": "Responsive",
        "role_group": "manager",
        "statement_text": (
            "We respond quickly when people's needs change — reviews are triggered "
            "and care is adjusted promptly."
        ),
        "evidence_types": [
            "Unplanned review records",
            "Escalation logs",
            "Handover notes",
        ],
        "guidance_notes": (
            "An unplanned review should be initiated within 24 hours of a "
            "significant change. Handover notes must document changes."
        ),
        "inspection_tips": (
            "Inspectors may trace a change in condition through handover notes to "
            "a care plan update."
        ),
        "sort_order": 21,
    },
    {
        "key_question": "Responsive",
        "role_group": "deputy",
        "statement_text": (
            "We listen to and act on feedback from people and their families, "
            "including complaints."
        ),
        "evidence_types": [
            "Complaints log",
            "Compliments file",
            "Resident/family meeting minutes",
            "Survey results",
        ],
        "guidance_notes": (
            "Every complaint must have a written acknowledgement within 3 days and "
            "a full response within 28 days."
        ),
        "inspection_tips": (
            "Be ready to describe a complaint and what changed as a result."
        ),
        "sort_order": 22,
    },
    {
        "key_question": "Responsive",
        "role_group": "manager",
        "statement_text": (
            "We make reasonable adjustments to ensure care is accessible and inclusive."
        ),
        "evidence_types": [
            "Equality assessments",
            "Communication support plans",
            "Accessible information evidence",
        ],
        "guidance_notes": (
            "Communication needs must be assessed and met — this includes dementia, "
            "sensory impairments, and language."
        ),
        "inspection_tips": (
            "Inspectors will look for evidence that accessible information was "
            "provided proactively."
        ),
        "sort_order": 23,
    },
    {
        "key_question": "Responsive",
        "role_group": "deputy",
        "statement_text": (
            "We support people to access activities and community involvement that "
            "matter to them."
        ),
        "evidence_types": [
            "Activity programme",
            "Community engagement logs",
            "Individual interest records",
        ],
        "guidance_notes": (
            "Activities must reflect individual preferences, not just group schedules. "
            "Community outings should be documented."
        ),
        "inspection_tips": (
            "Ask residents what they enjoy doing and how supported they feel to do it."
        ),
        "sort_order": 24,
    },
    # ── WELL-LED ──────────────────────────────────────────────────────────────
    {
        "key_question": "Well-led",
        "role_group": "manager",
        "statement_text": (
            "We have a clear vision and values — staff understand them and they are "
            "reflected in daily practice."
        ),
        "evidence_types": [
            "Staff handbook",
            "Team meeting records",
            "Induction materials",
        ],
        "guidance_notes": (
            "Values must be more than a poster on the wall — inspectors will ask "
            "staff and residents to describe them."
        ),
        "inspection_tips": (
            "Ask three different staff members what the home's values are. "
            "Can they tell you?"
        ),
        "sort_order": 25,
    },
    {
        "key_question": "Well-led",
        "role_group": "deputy",
        "statement_text": (
            "We have a positive, open culture — staff feel safe to raise concerns "
            "and are supported when they do."
        ),
        "evidence_types": [
            "Whistleblowing policy",
            "Staff survey results",
            "Supervision records",
            "HR logs",
        ],
        "guidance_notes": (
            "Whistleblowing policy must be accessible to all staff. Staff surveys "
            "must show action was taken on findings."
        ),
        "inspection_tips": (
            "Inspectors will speak to staff privately about the culture of the home."
        ),
        "sort_order": 26,
    },
    {
        "key_question": "Well-led",
        "role_group": "manager",
        "statement_text": (
            "We monitor quality effectively and use what we learn to make improvements."
        ),
        "evidence_types": [
            "Audit schedule",
            "Quality improvement plans",
            "Action trackers",
            "Governance meeting notes",
        ],
        "guidance_notes": (
            "Governance meetings must have minutes and action owners. Audits must "
            "drive improvement, not just measure it."
        ),
        "inspection_tips": (
            "Bring your quality dashboard or audit schedule to hand — inspectors "
            "may ask to see it."
        ),
        "sort_order": 27,
    },
    {
        "key_question": "Well-led",
        "role_group": "deputy",
        "statement_text": (
            "We manage information securely and use data to drive improvement."
        ),
        "evidence_types": [
            "Data protection policy",
            "DPIA records",
            "Dashboard reports",
            "IG training records",
        ],
        "guidance_notes": (
            "GDPR compliance must be evidenced. Staff must have completed IG "
            "training. DPIAs must be in place for new systems."
        ),
        "inspection_tips": (
            "Inspectors may ask how you ensure resident data is protected when "
            "sharing with health partners."
        ),
        "sort_order": 28,
    },
    {
        "key_question": "Well-led",
        "role_group": "manager",
        "statement_text": (
            "We work in partnership with the local authority, ICB, and other stakeholders."
        ),
        "evidence_types": [
            "Partnership meeting records",
            "Commissioner correspondence",
            "CQC notifications log",
        ],
        "guidance_notes": (
            "CQC notifications (DoLS, safeguarding, deaths) must be submitted on "
            "time. Commissioner relationships must be proactive."
        ),
        "inspection_tips": (
            "Be ready to name your commissioner contact and describe your last "
            "interaction."
        ),
        "sort_order": 29,
    },
    {
        "key_question": "Well-led",
        "role_group": "deputy",
        "statement_text": (
            "We have robust recruitment and retention practices — staff are "
            "well-supported and feel valued."
        ),
        "evidence_types": [
            "Safer recruitment files",
            "Turnover data",
            "Staff recognition programmes",
            "Exit interview evidence",
        ],
        "guidance_notes": (
            "Safer recruitment must include DBS, references, and right-to-work "
            "checks. Exit interviews must inform retention strategy."
        ),
        "inspection_tips": (
            "Inspectors will check that all safer recruitment checks are complete "
            "and documented."
        ),
        "sort_order": 30,
    },
]


async def seed_statements(session: AsyncSession) -> None:
    """Insert all We Statements. Skips any that already exist (by statement_text)."""
    from sqlalchemy import select

    existing_result = await session.execute(select(WeStatement.statement_text))
    existing_texts = {row for row in existing_result.scalars().all()}

    inserted = 0
    skipped = 0

    for data in WE_STATEMENTS_DATA:
        if data["statement_text"] in existing_texts:
            skipped += 1
            continue
        stmt = WeStatement(**data)
        session.add(stmt)
        inserted += 1

    await session.commit()
    logger.info("We Statements seeded: %d inserted, %d skipped", inserted, skipped)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    factory = get_session_factory(engine)

    async with factory() as session:
        await seed_statements(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
