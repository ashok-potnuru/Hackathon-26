import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Span:
    trace_id: str
    span_id: str
    stage: str
    issue_id: str
    start_time: str
    end_time: Optional[str] = None
    status: str = "in_progress"
    parent_span_id: Optional[str] = None


class Tracer:
    def __init__(self):
        self._traces: Dict[str, List[Span]] = {}

    def start_trace(self, issue_id: str) -> str:
        trace_id = str(uuid.uuid4())
        self._traces[trace_id] = []
        return trace_id

    def start_span(self, trace_id: str, stage: str, issue_id: str, parent_span_id: Optional[str] = None) -> Span:
        span = Span(
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
            stage=stage,
            issue_id=issue_id,
            start_time=datetime.utcnow().isoformat() + "Z",
            parent_span_id=parent_span_id,
        )
        self._traces.setdefault(trace_id, []).append(span)
        return span

    def end_span(self, span: Span, status: str = "ok") -> None:
        span.end_time = datetime.utcnow().isoformat() + "Z"
        span.status = status

    def get_trace(self, trace_id: str) -> List[dict]:
        return [
            {k: v for k, v in span.__dict__.items()}
            for span in self._traces.get(trace_id, [])
        ]


tracer = Tracer()
