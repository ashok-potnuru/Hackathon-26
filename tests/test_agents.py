"""Unit tests for PlannerAgent, CoderAgent, ReviewerAgent — mocked LLM, no API calls."""
import json
from unittest.mock import MagicMock, patch

import pytest

from core.agents.coder_agent import CoderAgent, CoderResult
from core.agents.planner_agent import PlannerAgent, PlanResult
from core.agents.reviewer_agent import ReviewerAgent, ReviewResult
from core.utils.graph_navigator import GraphNavigator


def _make_llm(response_text: str) -> MagicMock:
    """Return a mock LLM adapter whose chat_completion() returns response_text."""
    llm = MagicMock()
    llm.chat_completion.return_value = response_text
    return llm


def _make_nav() -> GraphNavigator:
    """Minimal in-memory navigator with known payment-related nodes."""
    nav = MagicMock(spec=GraphNavigator)
    from core.utils.graph_navigator import NodeMatch
    nav.search_nodes.return_value = [
        NodeMatch(
            node_id="payments_js",
            source_file="controllers/payments.js",
            community=1,
            score=2,
            norm_label="payments.js",
        )
    ]
    nav.get_related_files.return_value = [
        "controllers/payments.js",
        "services/order_service.js",
    ]
    return nav


class TestPlannerAgent:
    def test_extracts_keywords_and_returns_files(self):
        llm = _make_llm(json.dumps({"keywords": ["payment", "charge"], "change_type": "bugfix"}))
        nav = _make_nav()
        agent = PlannerAgent(llm, nav)
        result = agent.plan("Payment fails", "Credit card charge returns 500")
        assert isinstance(result, PlanResult)
        assert "payment" in result.keywords_extracted
        assert result.change_type == "bugfix"
        assert "controllers/payments.js" in result.target_files

    def test_falls_back_on_bad_json(self):
        llm = _make_llm("this is not json at all")
        nav = _make_nav()
        agent = PlannerAgent(llm, nav)
        result = agent.plan("Payment fails", "Credit card charge returns 500")
        assert isinstance(result, PlanResult)
        # Keywords should be derived from title words
        assert len(result.keywords_extracted) > 0

    def test_returns_empty_files_when_graph_finds_nothing(self):
        llm = _make_llm(json.dumps({"keywords": ["payment"], "change_type": "bugfix"}))
        nav = MagicMock(spec=GraphNavigator)
        nav.search_nodes.return_value = []
        agent = PlannerAgent(llm, nav)
        result = agent.plan("Payment fails", "Some description")
        assert result.target_files == []

    def test_excludes_md_files_from_seeds(self):
        llm = _make_llm(json.dumps({"keywords": ["readme"], "change_type": "bugfix"}))
        from core.utils.graph_navigator import NodeMatch
        nav = MagicMock(spec=GraphNavigator)
        nav.search_nodes.return_value = [
            NodeMatch(node_id="readme", source_file="README.md", community=1, score=1, norm_label="readme"),
            NodeMatch(node_id="pay_js", source_file="payments.js", community=1, score=1, norm_label="payments"),
        ]
        nav.get_related_files.return_value = ["payments.js"]
        agent = PlannerAgent(llm, nav)
        result = agent.plan("README update", "Update readme")
        # README.md excluded from seeds; get_related_files called with only payments.js
        call_args = nav.get_related_files.call_args[0][0]
        assert "README.md" not in call_args


class TestCoderAgent:
    def test_parses_valid_json_response(self):
        payload = {
            "reasoning": "Fix the null check",
            "files": {"payments.js": "const x = 1;"},
            "regression_test": "test('payment', () => {})",
            "confidence": 0.9,
        }
        llm = _make_llm(json.dumps(payload))
        agent = CoderAgent(llm)
        result = agent.generate("Fix null", "Null pointer in charge()", {"payments.js": "old"})
        assert isinstance(result, CoderResult)
        assert result.file_contents == {"payments.js": "const x = 1;"}
        assert result.confidence == 0.9
        assert result.reasoning == "Fix the null check"

    def test_returns_zero_confidence_on_bad_json(self):
        llm = _make_llm("I cannot fix this code, sorry.")
        agent = CoderAgent(llm)
        result = agent.generate("Fix null", "Null pointer", {"payments.js": "old"})
        assert result.confidence == 0.0
        assert result.file_contents == {}

    def test_injects_reviewer_feedback_in_prompt(self):
        payload = {"reasoning": "fixed", "files": {"f.js": "x"}, "regression_test": "", "confidence": 0.8}
        llm = _make_llm(json.dumps(payload))
        agent = CoderAgent(llm)
        agent.generate("T", "D", {"f.js": "old"}, reviewer_feedback="Please fix the null check")
        _, call_kwargs = llm.chat_completion.call_args
        messages = call_kwargs["messages"]
        user_content = messages[0]["content"]
        assert "Please fix the null check" in user_content


class TestReviewerAgent:
    def test_parses_approved_response(self):
        payload = {"approved": True, "verdict": "PASS", "feedback": "", "issues": [], "security_ok": True}
        llm = _make_llm(json.dumps(payload))
        agent = ReviewerAgent(llm)
        result = agent.review("Fix null", {"f.js": "old"}, {"f.js": "new"})
        assert isinstance(result, ReviewResult)
        assert result.approved is True
        assert result.verdict == "PASS"
        assert result.security_ok is True

    def test_parses_rejected_response(self):
        payload = {
            "approved": False,
            "verdict": "FAIL",
            "feedback": "The null check is missing on line 5",
            "issues": ["missing null check"],
            "security_ok": True,
        }
        llm = _make_llm(json.dumps(payload))
        agent = ReviewerAgent(llm)
        result = agent.review("Fix null", {}, {"f.js": "new"})
        assert result.approved is False
        assert result.verdict == "FAIL"
        assert "null check" in result.feedback

    def test_partial_verdict_counts_as_not_approved(self):
        payload = {"approved": True, "verdict": "PARTIAL", "feedback": "Minor issue", "issues": [], "security_ok": True}
        llm = _make_llm(json.dumps(payload))
        agent = ReviewerAgent(llm)
        result = agent.review("D", {}, {"f.js": "new"})
        assert result.approved is False  # PARTIAL → triggers retry
        assert result.verdict == "PARTIAL"

    def test_security_flag_propagated(self):
        payload = {"approved": False, "verdict": "FAIL", "feedback": "XSS risk", "issues": ["XSS"], "security_ok": False}
        llm = _make_llm(json.dumps(payload))
        agent = ReviewerAgent(llm)
        result = agent.review("D", {}, {"f.js": "new"})
        assert result.security_ok is False

    def test_defaults_to_approved_on_bad_json(self):
        llm = _make_llm("I cannot parse this as JSON")
        agent = ReviewerAgent(llm)
        result = agent.review("D", {}, {"f.js": "new"})
        assert result.approved is True
        assert result.verdict == "PASS"
        assert result.security_ok is True
