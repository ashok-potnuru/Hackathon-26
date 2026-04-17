from core.constants import ZohoStatus
from core.exceptions import IssueVagueError

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
    source = payload.get("source", "zoho")
    work_type = "feature" if source == "zoho_task" else "bugfix"

    if work_type == "feature":
        project_id = str(payload.get("projectId") or payload.get("project_id", ""))
        task_id = str(payload.get("taskId") or payload.get("task_id") or payload.get("id", ""))
        from adapters.issue_tracker.zoho_tasks import encode_task_id
        issue_id = encode_task_id(project_id, task_id)
    else:
        issue_id = str(payload.get("issue_id") or payload.get("ticketId") or payload.get("id", ""))

    issue = issue_tracker.get_issue(issue_id)
    issue.tenant = context.get("tenant", "default")

    raw_attachments = issue_tracker.get_attachments(issue.id)

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
        issue_tracker.post_comment(issue.id, comment)
        issue_tracker.update_status(issue.id, ZohoStatus.NEEDS_CLARIFICATION)
        raise IssueVagueError(f"Issue {issue.id} lacks sufficient detail")

    return {**context, "issue": issue, "work_type": work_type}
