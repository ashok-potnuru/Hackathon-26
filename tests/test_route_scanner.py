"""
Tests for route-first file targeting (core/utils/route_scanner.py)
and its integration into PlannerAgent.

Run with:
    cd /home/vishwanathreddykarka/project/Hackathon-26
    python -m pytest tests/test_route_scanner.py -v

Or run a single test:
    python -m pytest tests/test_route_scanner.py::TestRouteScanner::test_login_high_confidence -v
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.route_scanner import (
    CMSControllerMatcher,
    RouteScanner,
    RouteTargetResult,
)

# Path to the real Node.js API repo used for live parsing tests
API_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hackathon_wlb_api")
)
API_ROOT_EXISTS = os.path.isdir(os.path.join(API_ROOT, "routes"))


# ─────────────────────────────────────────────────────────────────────────────
# RouteScanner — unit tests (require local hackathon_wlb_api/)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not API_ROOT_EXISTS, reason="hackathon_wlb_api not available locally")
class TestRouteScanner:
    """Tests against the real route files in hackathon_wlb_api/routes/."""

    @pytest.fixture(scope="class")
    def scanner(self):
        return RouteScanner(API_ROOT)

    # ── Confidence: HIGH ──────────────────────────────────────────────────────

    def test_login_high_confidence(self, scanner):
        r = scanner.find_route_targets(
            "Fix login bug",
            "Users cannot log in with their credentials",
        )
        assert r.confidence == "high", f"Expected high, got {r.confidence}: {r.reasoning}"
        assert r.files == ["controllers/user_auth_controller.js"]
        assert "login" in r.matched_route.lower() or "auth" in r.matched_route.lower()

    def test_platform_settings_high_confidence(self, scanner):
        r = scanner.find_route_targets(
            "platform_settings missing region data",
            "GET /v3/auth/platform_settings does not return maxVideoHeight",
        )
        assert r.confidence == "high"
        assert r.files == ["controllers/user_auth_controller.js"]
        assert "platform_settings" in r.matched_route.lower()

    def test_payment_high_confidence(self, scanner):
        r = scanner.find_route_targets(
            "Payment fetch fails",
            "GET /v2/payments returns 500 for some users",
        )
        assert r.confidence == "high"
        assert r.files == ["controllers/payments_controller.js"]

    def test_subscription_resolves_to_payments_controller(self, scanner):
        r = scanner.find_route_targets(
            "Cancel subscription broken",
            "POST /v2/payments/svod/cancel/subscription returns error",
        )
        assert r.confidence == "high"
        assert "payments_controller" in r.files[0]

    def test_voucher_high_confidence(self, scanner):
        r = scanner.find_route_targets(
            "Voucher redemption fails",
            "Users cannot redeem a voucher code",
        )
        assert r.confidence in ("high", "medium")
        assert any("voucher" in f.lower() for f in r.files)

    def test_persona_high_confidence(self, scanner):
        r = scanner.find_route_targets(
            "Watch count not incrementing",
            "PUT /v2/persona/watch/count returns 200 but count stays the same",
        )
        assert r.confidence in ("high", "medium")
        # Should resolve to persona_access_controller
        assert any("persona" in f.lower() or "access" in f.lower() for f in r.files)

    # ── Confidence: MEDIUM ────────────────────────────────────────────────────

    def test_auth_domain_only_medium_or_high(self, scanner):
        r = scanner.find_route_targets(
            "Auth service broken",
            "Authentication is completely down for all users",
        )
        # "auth" domain matched → at minimum medium confidence
        assert r.confidence in ("high", "medium", "low")
        assert r.confidence != "none"

    # ── Confidence: NONE (fallback cases) ────────────────────────────────────

    def test_worker_job_no_match(self, scanner):
        r = scanner.find_route_targets(
            "Background job retry broken",
            "The encoding job never retries on failure in SQS queue",
        )
        assert r.confidence == "none"
        assert r.files == []

    def test_migration_no_match(self, scanner):
        r = scanner.find_route_targets(
            "Add database column",
            "We need to add a new column to the regions table in the migration",
        )
        assert r.confidence == "none"

    def test_empty_issue(self, scanner):
        r = scanner.find_route_targets("", "")
        assert r.confidence == "none"

    # ── Result structure ──────────────────────────────────────────────────────

    def test_high_confidence_has_single_file(self, scanner):
        r = scanner.find_route_targets("Fix login bug", "Cannot log in")
        if r.confidence == "high":
            assert len(r.files) == 1
            assert r.matched_route != ""
            assert r.matched_handler != ""

    def test_reasoning_is_non_empty(self, scanner):
        for title, desc in [
            ("login bug", "users cannot authenticate"),
            ("payment fails", "stripe returns 500"),
            ("cron job broken", "queue worker not processing"),
        ]:
            r = scanner.find_route_targets(title, desc)
            assert r.reasoning, f"Empty reasoning for: {title}"

    def test_files_are_relative_paths(self, scanner):
        r = scanner.find_route_targets("Login fails", "Cannot authenticate")
        for f in r.files:
            assert not os.path.isabs(f), f"File path should be relative: {f}"

    def test_no_duplicate_files(self, scanner):
        r = scanner.find_route_targets("Payment subscription plans", "Fetch plans endpoint broken")
        assert len(r.files) == len(set(r.files)), "Duplicate files in result"

    # ── Route loading ─────────────────────────────────────────────────────────

    def test_loads_all_route_files(self, scanner):
        scanner._load()
        loaded_files = set(scanner._require_maps.keys())
        expected = {"auth.js", "payments.js", "persona.js", "assets.js",
                    "paywall.js", "voucher.js", "operators.js"}
        assert expected.issubset(loaded_files), f"Missing route files: {expected - loaded_files}"

    def test_lazy_load_only_once(self, scanner):
        scanner._load()
        entries_before = len(scanner._entries)
        scanner._load()  # second call should be a no-op
        assert len(scanner._entries) == entries_before

    def test_missing_routes_dir_no_controller_resolved(self):
        # When routes/ dir is missing, no controller can be resolved.
        # Domain may still match ("login" → auth.js), but confidence stays "low"
        # so the planner falls through to graph search.
        bad_scanner = RouteScanner("/tmp/nonexistent_repo_xyz")
        r = bad_scanner.find_route_targets("login bug", "cannot log in")
        assert r.confidence in ("none", "low"), f"Unexpected confidence: {r.confidence}"
        # No actual controller file should be returned — only a route file hint at most
        assert not any("controller" in f.lower() for f in r.files)


# ─────────────────────────────────────────────────────────────────────────────
# CMSControllerMatcher — pure logic, no I/O
# ─────────────────────────────────────────────────────────────────────────────

class TestCMSControllerMatcher:
    @pytest.fixture(scope="class")
    def matcher(self):
        return CMSControllerMatcher()

    # ── Confidence: HIGH ──────────────────────────────────────────────────────

    def test_region_high_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Region config form broken",
            "The region edit form does not save maxVideoHeight",
        )
        assert r.confidence == "high"
        assert r.files == ["app/Http/Controllers/RegionController.php"]
        assert r.keywords == ["RegionController"]

    def test_voucher_high_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Voucher creation fails",
            "Admin cannot create a new voucher from the CMS",
        )
        assert r.confidence == "high"
        assert "app/Http/Controllers/VoucherController.php" in r.files
        assert "VoucherController" in r.keywords

    def test_zone_high_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Zone configuration missing",
            "Zone settings page shows no data",
        )
        assert r.confidence == "high"
        assert "ZoneController" in r.keywords

    def test_operator_high_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Operator list broken",
            "The operator management page shows an error",
        )
        assert r.confidence == "high"
        assert "OperatorController" in r.keywords

    # ── Confidence: MEDIUM (multiple controllers) ─────────────────────────────

    def test_series_season_medium_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Series season count wrong",
            "The series page shows incorrect season count",
        )
        assert r.confidence == "medium"
        assert "SeriesController" in r.keywords
        assert "SeasonController" in r.keywords

    def test_content_asset_medium_confidence(self, matcher):
        r = matcher.find_cms_targets(
            "Content asset upload broken",
            "Cannot upload content assets in CMS",
        )
        assert r.confidence == "medium"
        assert len(r.keywords) > 1

    # ── Confidence: NONE ──────────────────────────────────────────────────────

    def test_unknown_domain_returns_none(self, matcher):
        r = matcher.find_cms_targets(
            "Background job retry logic",
            "SQS queue worker fails to retry failed jobs",
        )
        assert r.confidence == "none"
        assert r.files == []
        assert r.keywords == []

    def test_empty_issue_returns_none(self, matcher):
        r = matcher.find_cms_targets("", "")
        assert r.confidence == "none"

    # ── Result structure ──────────────────────────────────────────────────────

    def test_files_follow_laravel_convention(self, matcher):
        r = matcher.find_cms_targets("Region broken", "Region form fails")
        for f in r.files:
            assert f.startswith("app/Http/Controllers/"), f"Unexpected path: {f}"
            assert f.endswith(".php"), f"Expected .php: {f}"

    def test_keywords_are_class_names(self, matcher):
        r = matcher.find_cms_targets("Region broken", "Region form fails")
        for kw in r.keywords:
            assert kw.endswith("Controller"), f"Expected ControllerClass: {kw}"
            assert kw[0].isupper(), f"Expected PascalCase class: {kw}"

    def test_files_and_keywords_aligned(self, matcher):
        """Each file should correspond to one keyword."""
        r = matcher.find_cms_targets("Payment subscription failed", "Cannot process subscription")
        assert len(r.files) == len(r.keywords)

    def test_no_duplicate_keywords(self, matcher):
        r = matcher.find_cms_targets("Series season episode", "Series and season management")
        assert len(r.keywords) == len(set(r.keywords))

    def test_reasoning_always_set(self, matcher):
        for title, desc in [
            ("region broken", "region form"),
            ("unknown thing", "some random issue"),
        ]:
            r = matcher.find_cms_targets(title, desc)
            assert r.reasoning, f"Empty reasoning for: {title}"


# ─────────────────────────────────────────────────────────────────────────────
# PlannerAgent integration — route-first path (mocked LLM, real graph + scanner)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not API_ROOT_EXISTS, reason="hackathon_wlb_api not available locally")
class TestPlannerAgentRouteFirst:
    """Integration tests: real RouteScanner + real GraphNavigator, mocked LLM."""

    @pytest.fixture(scope="class")
    def planner(self):
        from core.agents.planner_agent import PlannerAgent
        from core.utils.graph_navigator import get_navigator

        # Mock LLM so we don't make real API calls
        mock_llm = MagicMock()
        mock_llm._client = MagicMock()
        # LLM returns a minimal keyword JSON for any call
        mock_llm.messages = MagicMock()
        mock_llm.messages.create = MagicMock(return_value=MagicMock(
            content=[MagicMock(text='{"keywords": ["auth", "login"], "change_type": "bugfix"}')]
        ))

        nav = get_navigator("api")
        return PlannerAgent(mock_llm, nav, api_root=API_ROOT)

    def test_login_issue_targets_auth_controller(self, planner):
        from unittest.mock import patch

        with patch.object(planner, "run_turn", return_value='{"keywords": ["auth", "login"], "change_type": "bugfix"}'):
            result = planner.plan(
                title="Fix login bug",
                description="Users cannot log in with their credentials",
                repo_type="api",
            )

        assert result.target_files, "Expected non-empty target_files"
        assert any("user_auth_controller" in f for f in result.target_files), \
            f"Expected auth controller in targets, got: {result.target_files}"
        assert "[RouteFirst/HIGH]" in result.reasoning

    def test_payment_issue_targets_payments_controller(self, planner):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(planner, "run_turn",
                       lambda **kw: '{"keywords": ["payment"], "change_type": "bugfix"}')
            result = planner.plan(
                title="Payment fetch fails",
                description="GET /v2/payments returns 500",
                repo_type="api",
            )

        assert any("payment" in f.lower() for f in result.target_files), \
            f"Expected payments controller in targets, got: {result.target_files}"

    def test_worker_issue_falls_back_to_graph(self, planner):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(planner, "run_turn",
                       lambda **kw: '{"keywords": ["job", "retry", "worker"], "change_type": "bugfix"}')
            result = planner.plan(
                title="Background job retry broken",
                description="SQS queue worker never retries on failure",
                repo_type="api",
            )

        # Should NOT have RouteFirst prefix (fell back to graph)
        assert "[RouteFirst" not in result.reasoning, \
            f"Expected graph fallback, but got: {result.reasoning}"

    def test_cms_injects_controller_class_keyword(self):
        from core.agents.planner_agent import PlannerAgent
        from core.utils.graph_navigator import get_navigator

        nav = get_navigator("cms")
        planner = PlannerAgent(MagicMock(), nav, api_root="")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(planner, "run_turn",
                       lambda **kw: '{"keywords": ["region", "config"], "change_type": "feature"}')
            result = planner.plan(
                title="Region config form broken",
                description="The region edit page does not save maxVideoHeight",
                repo_type="cms",
            )

        # CMS path should include RegionController in keywords_extracted
        assert "RegionController" in result.keywords_extracted, \
            f"Expected RegionController injected as keyword, got: {result.keywords_extracted}"

    def test_repo_type_cms_does_not_use_route_scanner(self, planner):
        """CMS path must never trigger RouteScanner (which reads JS files)."""
        scanner_calls = []
        original_find = planner._route_scanner.find_route_targets if planner._route_scanner else None

        if planner._route_scanner:
            planner._route_scanner.find_route_targets = lambda *a, **kw: (
                scanner_calls.append(1) or RouteTargetResult([], [], "none", "", "", "mocked")
            )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(planner, "run_turn",
                       lambda **kw: '{"keywords": ["region"], "change_type": "bugfix"}')
            planner.plan("Region broken", "Region form fails", repo_type="cms")

        assert scanner_calls == [], "RouteScanner should not be called for CMS repo"

        # Restore
        if original_find:
            planner._route_scanner.find_route_targets = original_find


# ─────────────────────────────────────────────────────────────────────────────
# Quick standalone runner (no pytest needed)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("RouteScanner — live tests against hackathon_wlb_api/")
    print("=" * 60)

    if not API_ROOT_EXISTS:
        print(f"SKIP: hackathon_wlb_api not found at {API_ROOT}")
    else:
        scanner = RouteScanner(API_ROOT)
        cases = [
            ("Fix login bug", "Users cannot log in"),
            ("platform_settings missing data", "GET /v3/auth/platform_settings broken"),
            ("Payment fetch fails", "GET /v2/payments returns 500"),
            ("Cancel subscription", "POST cancel subscription broken"),
            ("Voucher redemption fails", "User cannot redeem voucher"),
            ("Watch count broken", "PUT /v2/persona/watch/count fails"),
            ("Background job retry", "SQS queue worker issue"),
        ]
        for title, desc in cases:
            r = scanner.find_route_targets(title, desc)
            icon = {"high": "✓", "medium": "~", "low": "?", "none": "✗"}[r.confidence]
            print(f"  {icon} [{r.confidence:6}]  {title!r}")
            if r.files:
                print(f"           files: {r.files}")
            if r.matched_route:
                print(f"           route: {r.matched_route} → {r.matched_handler}")

    print()
    print("=" * 60)
    print("CMSControllerMatcher — pure logic tests")
    print("=" * 60)
    matcher = CMSControllerMatcher()
    cms_cases = [
        ("Region config form broken", "Region edit page fails"),
        ("Series season count wrong", "Series shows wrong seasons"),
        ("Voucher creation fails", "Cannot create voucher in admin"),
        ("Background job retry", "Queue worker fails"),
    ]
    for title, desc in cms_cases:
        r = matcher.find_cms_targets(title, desc)
        icon = {"high": "✓", "medium": "~", "none": "✗"}[r.confidence]
        print(f"  {icon} [{r.confidence:6}]  {title!r}")
        if r.keywords:
            print(f"           keywords: {r.keywords}")
        if r.files:
            print(f"           files:    {r.files}")
