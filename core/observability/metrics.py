import time
from collections import defaultdict
from typing import Dict, List


class MetricsCollector:
    def __init__(self):
        self._stage_durations: Dict[str, List[float]] = defaultdict(list)
        self._stage_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})
        self._fix_confidence_scores: List[float] = []

    def record_stage_end(self, stage: str, start_time: float, success: bool) -> None:
        self._stage_durations[stage].append(time.time() - start_time)
        self._stage_counts[stage]["success" if success else "failure"] += 1

    def record_fix_confidence(self, score: float) -> None:
        self._fix_confidence_scores.append(score)

    def get_summary(self) -> dict:
        return {
            "stage_durations": {
                stage: {"avg_seconds": round(sum(v) / len(v), 3), "count": len(v)}
                for stage, v in self._stage_durations.items()
            },
            "stage_counts": {k: dict(v) for k, v in self._stage_counts.items()},
            "avg_fix_confidence": (
                round(sum(self._fix_confidence_scores) / len(self._fix_confidence_scores), 3)
                if self._fix_confidence_scores else 0.0
            ),
        }


metrics = MetricsCollector()
