from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FixModel:
    files_changed: List[str]
    diff: str
    reasoning: str
    regression_test: str
    security_scan_passed: bool = False
    lint_passed: bool = False
    confidence_score: float = 0.0
    file_contents: Dict[str, str] = field(default_factory=dict)
