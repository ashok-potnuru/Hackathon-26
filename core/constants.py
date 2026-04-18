class IssuePriority:
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class PipelineStage:
    INTAKE = "intake"
    FIX_GENERATION = "fix_generation"
    DEPLOY = "deploy"


MAX_FILES_FOR_AUTO_FIX = 15
