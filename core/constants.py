class ZohoStatus:
    OPEN = "Open"
    NEEDS_CLARIFICATION = "Needs Clarification"
    IN_PROGRESS = "In Progress"
    FIX_PROPOSED = "Fix Proposed"
    UNDER_REVIEW = "Under Review"
    VALIDATING = "Validating"
    FIXED = "Fixed"
    NEEDS_MANUAL_REVIEW = "Needs Manual Review"


class IssuePriority:
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TargetBranch:
    CRITICAL = "main"
    NORMAL = "develop"


class PipelineStage:
    INTAKE = "intake"
    TRIAGE = "triage"
    RESEARCH = "research"
    FIX_GENERATION = "fix_generation"
    PR_CREATION = "pr_creation"
    DEVELOPER_REVIEW = "developer_review"
    CI = "ci"
    CLOSURE = "closure"


MAX_FILES_FOR_AUTO_FIX = 5
STALE_PR_REMINDER_HOURS = 24
STALE_PR_ESCALATION_HOURS = 48
MAX_FIX_RETRIES = 2
