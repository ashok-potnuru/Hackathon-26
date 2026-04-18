_NEEDS_CLARIFICATION = "Needs Clarification"
from core.exceptions import IssueVagueError
from core.observability.logger import get_logger

logger = get_logger(__name__)

_VAGUE_COMMENT_BUG = (
    "This issue needs more detail for automated fixing. "
    "Please include: steps to reproduce, expected vs actual behavior, and relevant error logs."
)
_VAGUE_COMMENT_FEATURE = (
    "The PRD lacks sufficient detail for automated implementation. "
    "Please clarify: acceptance criteria, affected components, and expected API/UI changes."
)


def _extract_prd_content(attachment_info: dict, raw: bytes) -> str:
    filename = attachment_info.get("filename", "").lower()
    if filename.endswith(".pdf"):
        return _parse_pdf(raw)
    if filename.endswith(".docx"):
        return _parse_docx(raw)
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_pdf(data: bytes) -> str:
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return "[PDF content could not be extracted]"


def _parse_docx(data: bytes) -> str:
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return "[DOCX content could not be extracted]"


async def run(context: dict) -> dict:
    payload = context["payload"]
    adapters = context["adapters"]
    issue_tracker = adapters["issue_tracker"]
    llm = adapters["llm"]
    issue_id = str(payload.get("issue_id") or payload.get("itemId") or payload.get("id", ""))

    project_id = str(payload.get("projectId", ""))
    sprint_id = str(payload.get("sprintId", ""))

    # Zoho Flow fields may sit in a nested "payload" dict or at the top level
    _nested = payload.get("payload") or {}
    _p = {**_nested, **{k: v for k, v in payload.items() if k != "payload"}}

    logger.info(f"intake payload keys: {list(_p.keys())}, title={_p.get('title')!r}")

    # If Zoho Flow pushed item fields directly in the payload, use them without an API round-trip
    if _p.get("title"):
        from core.constants import IssuePriority
        _prio_map = {"high": IssuePriority.HIGH, "medium": IssuePriority.NORMAL, "low": IssuePriority.LOW}
        from core.models.issue import IssueModel
        _type_raw = _p.get("typeName", "issue")
        _tenant = "issue" if _type_raw is True or str(_type_raw).lower() not in ("task",) else "task"
        def _str(v, default=""):
            return default if (v is None or str(v).lower() == "null") else str(v)

        issue = IssueModel(
            id=issue_id,
            title=_str(_p.get("title")),
            description=_str(_p.get("description")),
            priority=_prio_map.get(_str(_p.get("priority"), "medium").lower(), IssuePriority.NORMAL),
            zoho_status=_str(_p.get("statusName"), "Open"),
            tenant=_tenant,
        )
        from_payload = True
    else:
        issue = issue_tracker.get_issue(issue_id, project_id=project_id, sprint_id=sprint_id)
        from_payload = False
    # ZohoSprintsAdapter sets issue.tenant to "task" (feature) or "issue" (bugfix)
    work_type = "feature" if issue.tenant == "task" else "bugfix"

    adapters["notification"].send_message(
        "", f"AutoFix AI picked up {work_type} [{issue.id}]: {issue.title} — analyzing..."
    )

    raw_attachments = [] if from_payload else issue_tracker.get_attachments(issue.id)

    if work_type == "feature" and raw_attachments:
        prd_parts: list[str] = []
        downloader = getattr(issue_tracker, "download_attachment", None)
        for att in raw_attachments:
            if not isinstance(att, dict):
                continue
            url = att.get("url", "")
            if url and downloader:
                try:
                    content = downloader(url)
                    text = _extract_prd_content(att, content)
                    if text.strip():
                        prd_parts.append(f"[Attachment: {att.get('filename', 'file')}]\n{text}")
                except Exception:
                    pass
        if prd_parts:
            issue.description = (issue.description or "") + "\n\n--- PRD Content ---\n" + "\n\n".join(prd_parts)
        issue.attachments = [a.get("url", "") for a in raw_attachments if isinstance(a, dict)]
    else:
        issue.attachments = raw_attachments if isinstance(raw_attachments, list) else []

    if work_type == "feature":
        quality_prompt = (
            f"Analyze this PRD/task for automated implementation eligibility.\n"
            f"Title: {issue.title}\nContent:\n{issue.description}\n\n"
            "Reply with one word: IMPLEMENTABLE or VAGUE."
        )
        verdict_match = "VAGUE"
    else:
        quality_prompt = (
            f"Analyze this bug report for auto-fix eligibility.\n"
            f"Title: {issue.title}\nDescription: {issue.description}\n\n"
            "Reply with one word: FIXABLE or VAGUE."
        )
        verdict_match = "VAGUE"

    verdict = llm.analyze(quality_prompt).strip().upper()

    if verdict_match in verdict:
        comment = _VAGUE_COMMENT_FEATURE if work_type == "feature" else _VAGUE_COMMENT_BUG
        try:
            issue_tracker.post_comment(issue.id, comment)
            issue_tracker.update_status(issue.id, _NEEDS_CLARIFICATION)
        except Exception:
            pass
        raise IssueVagueError(f"Issue {issue.id} lacks sufficient detail")

    # Override with title/description extracted directly from the Zoho webhook payload
    webhook_title = str(payload.get("title") or "").strip()
    webhook_description = str(payload.get("description") or "").strip()
    if webhook_title:
        issue.title = webhook_title
    if webhook_description:
        issue.description = webhook_description

    return {**context, "issue": issue, "work_type": work_type}
