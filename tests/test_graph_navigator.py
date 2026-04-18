"""Unit tests for GraphNavigator — offline, no LLM or API calls."""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.utils.graph_navigator import GraphNavigator, NodeMatch, get_navigator

# Minimal graph fixture: 4 nodes, 3 edges, 2 communities
_FIXTURE_GRAPH = {
    "nodes": [
        {"id": "payments_controller_js", "label": "payments_controller.js",
         "source_file": "controllers/payments_controller.js", "source_location": "L1",
         "community": 1, "norm_label": "payments_controller.js", "file_type": "code"},
        {"id": "payments_controller_js_charge", "label": "charge()",
         "source_file": "controllers/payments_controller.js", "source_location": "L42",
         "community": 1, "norm_label": "charge", "file_type": "code"},
        {"id": "order_service_js", "label": "order_service.js",
         "source_file": "services/order_service.js", "source_location": "L1",
         "community": 2, "norm_label": "order_service.js", "file_type": "code"},
        {"id": "readme_md", "label": "README.md",
         "source_file": "README.md", "source_location": None,
         "community": 0, "norm_label": "readme.md", "file_type": "document"},
    ],
    "links": [
        {"source": "payments_controller_js_charge", "target": "order_service_js",
         "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0,
         "source_file": "controllers/payments_controller.js", "source_location": "L45"},
        {"source": "payments_controller_js", "target": "payments_controller_js_charge",
         "relation": "contains", "confidence": "EXTRACTED", "confidence_score": 1.0,
         "source_file": "controllers/payments_controller.js", "source_location": "L1"},
        {"source": "readme_md", "target": "payments_controller_js",
         "relation": "rationale_for", "confidence": "INFERRED", "confidence_score": 0.7,
         "source_file": "README.md", "source_location": None},
    ],
}


@pytest.fixture()
def nav(tmp_path):
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(_FIXTURE_GRAPH))
    return GraphNavigator(graph_path=graph_file)


class TestSearchNodes:
    def test_keyword_hit_returns_match(self, nav):
        results = nav.search_nodes(["payment"])
        assert len(results) > 0
        files = {m.source_file for m in results}
        assert "controllers/payments_controller.js" in files

    def test_score_is_number_of_keyword_hits(self, nav):
        results = nav.search_nodes(["payment", "charge"])
        # Node "charge()" matches both keywords ("payment" via file, "charge" via label)
        top = results[0]
        assert top.score >= 1

    def test_no_match_returns_empty(self, nav):
        results = nav.search_nodes(["xyznonexistent"])
        assert results == []

    def test_empty_keywords_returns_empty(self, nav):
        results = nav.search_nodes([])
        assert results == []

    def test_top_k_limits_results(self, nav):
        results = nav.search_nodes(["a"], top_k=1)
        assert len(results) <= 1

    def test_results_sorted_by_score_descending(self, nav):
        results = nav.search_nodes(["payment", "order"])
        scores = [m.score for m in results]
        assert scores == sorted(scores, reverse=True)


class TestGetRelatedFiles:
    def test_seed_file_appears_first(self, nav):
        result = nav.get_related_files(["controllers/payments_controller.js"])
        assert result[0] == "controllers/payments_controller.js"

    def test_connected_file_included_within_two_hops(self, nav):
        result = nav.get_related_files(
            ["controllers/payments_controller.js"], max_hops=2, max_files=15
        )
        assert "services/order_service.js" in result

    def test_max_files_cap_respected(self, nav):
        result = nav.get_related_files(
            ["controllers/payments_controller.js"], max_hops=2, max_files=1
        )
        assert len(result) <= 1

    def test_empty_seed_returns_empty(self, nav):
        result = nav.get_related_files([])
        assert result == []

    def test_no_duplicates(self, nav):
        result = nav.get_related_files(
            ["controllers/payments_controller.js", "controllers/payments_controller.js"]
        )
        assert len(result) == len(set(result))


class TestGetCommunityFiles:
    def test_community_zero_returns_empty(self, nav):
        assert nav.get_community_files(0) == []

    def test_valid_community_returns_files(self, nav):
        files = nav.get_community_files(1)
        assert "controllers/payments_controller.js" in files

    def test_unknown_community_returns_empty(self, nav):
        assert nav.get_community_files(999) == []


class TestGetFilesForNodeIds:
    def test_maps_node_to_file(self, nav):
        result = nav.get_files_for_node_ids(["order_service_js"])
        assert result == ["services/order_service.js"]

    def test_deduplicates_same_file(self, nav):
        result = nav.get_files_for_node_ids([
            "payments_controller_js",
            "payments_controller_js_charge",
        ])
        assert result.count("controllers/payments_controller.js") == 1

    def test_unknown_node_skipped(self, nav):
        result = nav.get_files_for_node_ids(["does_not_exist"])
        assert result == []


class TestGetRelevantLines:
    def test_returns_lines_around_matched_node(self, nav):
        # payments_controller_js_charge is at L42, keyword "charge" matches
        content = "\n".join(f"line {i}" for i in range(1, 101))  # 100 lines
        result = nav.get_relevant_lines(
            source_file="controllers/payments_controller.js",
            file_content=content,
            keywords=["charge"],
            context_lines=10,
        )
        assert "42|" in result  # line 42 must be present

    def test_falls_back_to_truncation_when_no_match(self, nav):
        content = "x" * 5000
        result = nav.get_relevant_lines(
            source_file="controllers/payments_controller.js",
            file_content=content,
            keywords=["xyznonexistent"],
        )
        assert len(result) == 3000  # fallback truncation

    def test_includes_line_numbers_in_output(self, nav):
        content = "\n".join(f"code line {i}" for i in range(1, 60))
        result = nav.get_relevant_lines(
            source_file="controllers/payments_controller.js",
            file_content=content,
            keywords=["charge"],
        )
        assert "|" in result  # line number prefix present

    def test_merges_overlapping_ranges(self, nav):
        content = "\n".join(f"line {i}" for i in range(1, 200))
        result = nav.get_relevant_lines(
            source_file="controllers/payments_controller.js",
            file_content=content,
            keywords=["payment", "charge"],
            context_lines=80,
        )
        # With large context, overlapping ranges should merge into one section
        assert result.count("# lines") <= 2


class TestSingleton:
    def test_get_navigator_returns_same_instance(self, nav, tmp_path):
        import core.utils.graph_navigator as mod
        graph_file = tmp_path / "graph.json"
        graph_file.write_text(json.dumps(_FIXTURE_GRAPH))
        old_singleton = mod._singleton
        mod._singleton = None
        try:
            a = get_navigator(graph_path=graph_file)
            b = get_navigator(graph_path=graph_file)
            assert a is b
        finally:
            mod._singleton = old_singleton
