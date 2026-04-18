"""Unit tests for MultiAgentOrchestrator — mocked adapters, no API calls."""
import json
from unittest.mock import MagicMock, call, patch

import pytest

from core.agents.planner_agent import PlanResult
from core.exceptions import FixGenerationError, SecurityScanError
from core.models.fix import FixModel
from core.orchestrator import MAX_REVIEW_ITERATIONS, MultiAgentOrchestrator
from core.utils.graph_navigator import GraphNavigator


def _make_issue(target_files=None):
    issue = MagicMock()
    issue.title = "Fix payment bug"
    issue.description = "Credit card charge fails with 500"
    issue.affected_repos = ["org/repo"]
    issue.target_branch = "main"
    return issue


def _make_plan(files=None):
    return PlanResult(
        target_files=files or ["controllers/payments.js"],
        change_type="bugfix",
        keywords_extracted=["payment"],
        reasoning="Graph found payment files.",
    )


def _make_vc(file_contents=None):
    vc = MagicMock()
    vc.get_file.return_value = file_contents or "function charge() { return null; }"
    return vc


def _make_nav():
    return MagicMock(spec=GraphNavigator)


_EXPLORER_RESPONSE = json.dumps({
    "files": {
        "controllers/payments.js": {
            "must_change": True,
            "relevant_lines": "1-5",
            "reason": "Contains the charge function",
        }
    },
    "summary": "Payment controller needs fixing",
})


def _make_llm(coder_response: str, reviewer_response: str):
    """Route by system prompt:
      'code review'  → reviewer
      'code explorer' → explorer
      else            → coder
    """

    def create_side_effect(*args, **kwargs):
        system = kwargs.get("system", [{}])
        system_text = system[0].get("text", "") if system else ""
        if "code review" in system_text.lower():
            response_text = reviewer_response
        elif "code explorer" in system_text.lower():
            response_text = _EXPLORER_RESPONSE
        else:
            response_text = coder_response
        mock_content = MagicMock()
        mock_content.text = response_text
        mock_resp = MagicMock()
        mock_resp.content = [mock_content]
        return mock_resp

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_side_effect
    llm = MagicMock()
    llm._client = mock_client
    llm._model = "claude-sonnet-4-6"
    return llm


_GOOD_CODER = json.dumps({
    "reasoning": "Add null check",
    "files": {"controllers/payments.js": "function charge() { return 0; }"},
    "regression_test": "test('charge', () => {})",
    "confidence": 0.85,
})
_APPROVED_REVIEWER = json.dumps({
    "approved": True, "verdict": "PASS", "feedback": "", "issues": [], "security_ok": True,
    "checks": {"correctness": "PASS", "security": "PASS", "regression_risk": "PASS",
                "boundary_values": "PASS", "error_handling": "PASS", "concurrency": "N/A"},
})
_REJECTED_REVIEWER = json.dumps({
    "approved": False, "verdict": "FAIL",
    "feedback": "Missing error handling on line 1",
    "issues": ["no error handling"],
    "security_ok": True,
    "checks": {"correctness": "PASS", "security": "PASS", "regression_risk": "PASS",
                "boundary_values": "PASS", "error_handling": "Missing try/catch", "concurrency": "N/A"},
})
_SECURITY_FAIL_REVIEWER = json.dumps({
    "approved": False, "verdict": "FAIL", "feedback": "XSS risk", "issues": ["XSS"],
    "security_ok": False,
    "checks": {"correctness": "PASS", "security": "XSS via unescaped input",
                "regression_risk": "PASS", "boundary_values": "PASS",
                "error_handling": "PASS", "concurrency": "N/A"},
})


class TestOrchestrator:
    def test_approves_on_first_attempt(self):
        llm = _make_llm(_GOOD_CODER, _APPROVED_REVIEWER)
        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        fix = orch.run(_make_issue(), _make_plan())
        assert isinstance(fix, FixModel)
        assert fix.confidence_score == pytest.approx(0.85)
        assert "controllers/payments.js" in fix.files_changed

    def test_retries_on_rejection_and_succeeds(self):
        # First reviewer call rejects, second approves
        reviewer_responses = [_REJECTED_REVIEWER, _APPROVED_REVIEWER]
        reviewer_iter = iter(reviewer_responses)

        def create_side_effect(*args, **kwargs):
            system = kwargs.get("system", [{}])
            system_text = system[0].get("text", "") if system else ""
            mock_content = MagicMock()
            if "code review" in system_text.lower():
                mock_content.text = next(reviewer_iter)
            elif "code explorer" in system_text.lower():
                mock_content.text = _EXPLORER_RESPONSE
            else:
                mock_content.text = _GOOD_CODER
            mock_resp = MagicMock()
            mock_resp.content = [mock_content]
            return mock_resp

        llm = MagicMock()
        llm._client = MagicMock()
        llm._client.messages.create.side_effect = create_side_effect
        llm._model = "claude-sonnet-4-6"

        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        fix = orch.run(_make_issue(), _make_plan())
        assert isinstance(fix, FixModel)

    def test_raises_fix_generation_error_after_max_iterations(self):
        # Reviewer always rejects
        llm = _make_llm(_GOOD_CODER, _REJECTED_REVIEWER)
        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        with pytest.raises(FixGenerationError):
            orch.run(_make_issue(), _make_plan())

    def test_raises_security_scan_error_immediately(self):
        llm = _make_llm(_GOOD_CODER, _SECURITY_FAIL_REVIEWER)
        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        with pytest.raises(SecurityScanError):
            orch.run(_make_issue(), _make_plan())

    def test_raises_fix_generation_error_when_no_files_fetched(self):
        llm = _make_llm(_GOOD_CODER, _APPROVED_REVIEWER)
        vc = _make_vc()
        vc.get_file.side_effect = Exception("404 Not Found")
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        with pytest.raises(FixGenerationError, match="No files could be fetched"):
            orch.run(_make_issue(), _make_plan())

    def test_returns_fix_model_with_correct_fields(self):
        llm = _make_llm(_GOOD_CODER, _APPROVED_REVIEWER)
        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        fix = orch.run(_make_issue(), _make_plan())
        assert fix.security_scan_passed is True
        assert fix.lint_passed is True
        assert fix.file_contents == {"controllers/payments.js": "function charge() { return 0; }"}
        assert "Graph found" in fix.reasoning

    def test_low_confidence_coder_result_triggers_retry(self):
        bad_coder = json.dumps({
            "reasoning": "uncertain",
            "files": {},
            "regression_test": "",
            "confidence": 0.1,
        })
        # First attempt is low confidence (files={}), second is good
        coder_responses = [bad_coder, _GOOD_CODER]
        coder_iter = iter(coder_responses)

        def create_side_effect(*args, **kwargs):
            system = kwargs.get("system", [{}])
            system_text = system[0].get("text", "") if system else ""
            mock_content = MagicMock()
            if "code review" in system_text.lower():
                mock_content.text = _APPROVED_REVIEWER
            elif "code explorer" in system_text.lower():
                mock_content.text = _EXPLORER_RESPONSE
            else:
                mock_content.text = next(coder_iter, _GOOD_CODER)
            mock_resp = MagicMock()
            mock_resp.content = [mock_content]
            return mock_resp

        llm = MagicMock()
        llm._client = MagicMock()
        llm._client.messages.create.side_effect = create_side_effect
        llm._model = "claude-sonnet-4-6"

        vc = _make_vc()
        orch = MultiAgentOrchestrator(llm, vc, _make_nav())
        fix = orch.run(_make_issue(), _make_plan())
        assert isinstance(fix, FixModel)
