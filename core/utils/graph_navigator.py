from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Optional  # noqa: F401 — kept for backward compat

_ROOT = Path(__file__).parent.parent.parent

GRAPH_API_PATH = _ROOT / "graph_api" / "graph.json"
GRAPH_CMS_PATH = _ROOT / "graph_cms" / "graph.json"

# Legacy alias — kept so any direct imports of GRAPH_PATH still resolve
GRAPH_PATH = GRAPH_API_PATH

# Community 0 is the Louvain remainder bin (239+ nodes) — not a meaningful cluster
_JUNK_COMMUNITY = 0


@dataclass
class NodeMatch:
    node_id: str
    source_file: str
    community: int
    score: int
    norm_label: str


class GraphNavigator:
    """Read-only traversal over hackathon_wlb_api/graphify-out/graph.json.

    graph.json is committed to the repo and read from local disk.
    All derived indices are built once on first access via cached_property.
    """

    def __init__(self, graph_path: Path = GRAPH_PATH):
        self._graph_path = graph_path

    @cached_property
    def _graph(self) -> dict:
        with open(self._graph_path) as f:
            return json.load(f)

    @cached_property
    def _nodes(self) -> list[dict]:
        return self._graph["nodes"]

    @cached_property
    def _links(self) -> list[dict]:
        return self._graph["links"]

    @cached_property
    def _node_map(self) -> dict[str, dict]:
        return {n["id"]: n for n in self._nodes}

    @cached_property
    def _community_to_files(self) -> dict[int, set[str]]:
        idx: dict[int, set[str]] = defaultdict(set)
        for n in self._nodes:
            comm = n.get("community")
            sf = n.get("source_file")
            if comm is not None and sf:
                idx[comm].add(sf)
        return idx

    @cached_property
    def _file_adjacency(self) -> dict[str, set[str]]:
        """Undirected file-level adjacency derived from node-level edges."""
        adj: dict[str, set[str]] = defaultdict(set)
        for link in self._links:
            src_node = self._node_map.get(link.get("source", ""), {})
            tgt_node = self._node_map.get(link.get("target", ""), {})
            sf = src_node.get("source_file")
            tf = tgt_node.get("source_file")
            if sf and tf and sf != tf:
                adj[sf].add(tf)
                adj[tf].add(sf)
        return adj

    def search_nodes(self, keywords: list[str], top_k: int = 30) -> list[NodeMatch]:
        """Score nodes by how many keywords appear as substrings in their identifiers.

        Searches id + norm_label + label + source_file concatenated.
        Returns top_k results sorted by score descending.
        """
        kws = [kw.lower() for kw in keywords if kw]
        if not kws:
            return []

        scored: list[NodeMatch] = []
        for n in self._nodes:
            search_text = " ".join(filter(None, [
                n.get("id", ""),
                n.get("norm_label", ""),
                n.get("label", ""),
                n.get("source_file", ""),
            ])).lower()
            score = sum(1 for kw in kws if kw in search_text)
            if score > 0:
                scored.append(NodeMatch(
                    node_id=n["id"],
                    source_file=n.get("source_file", ""),
                    community=n.get("community", -1),
                    score=score,
                    norm_label=n.get("norm_label", ""),
                ))

        scored.sort(key=lambda m: -m.score)
        return scored[:top_k]

    def get_related_files(
        self,
        seed_files: list[str],
        max_hops: int = 2,
        max_files: int = 15,
    ) -> list[str]:
        """BFS from seed_files through file-level adjacency.

        Seeds appear first; expansion is BFS-ordered (closer hops first).
        Result is capped at max_files to keep research context bounded.
        """
        visited: set[str] = set()
        result: list[str] = []

        for f in seed_files:
            if f and f not in visited:
                visited.add(f)
                result.append(f)

        queue: deque[tuple[str, int]] = deque((f, 0) for f in result)

        while queue and len(result) < max_files:
            current_file, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbor in sorted(self._file_adjacency.get(current_file, [])):
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(neighbor)
                    queue.append((neighbor, depth + 1))
                    if len(result) >= max_files:
                        break

        return result

    def get_community_files(self, community_id: int) -> list[str]:
        """All source_files in a community. Returns [] for community 0 (garbage bin)."""
        if community_id == _JUNK_COMMUNITY:
            return []
        return sorted(self._community_to_files.get(community_id, set()))

    def get_files_for_node_ids(self, node_ids: list[str]) -> list[str]:
        """Map node IDs to their source_files, deduped, preserving order."""
        seen: set[str] = set()
        result: list[str] = []
        for nid in node_ids:
            sf = self._node_map.get(nid, {}).get("source_file")
            if sf and sf not in seen:
                seen.add(sf)
                result.append(sf)
        return result

    def get_relevant_lines(
        self,
        source_file: str,
        file_content: str,
        keywords: list[str],
        context_lines: int = 40,
    ) -> str:
        """Extract only the lines around matched graph nodes for a given file.

        Uses source_location (e.g. "L42") from graph nodes that:
          - belong to source_file
          - match at least one keyword in their label/norm_label/id

        Returns a filtered string with line numbers prepended.
        Falls back to the full file if no nodes match (keeps first 3000 chars).

        This replaces dumb char-truncation with targeted extraction:
        instead of blindly cutting at char 3000, we send the functions
        and classes the graph says are relevant.
        """
        lines = file_content.splitlines()
        kws = [kw.lower() for kw in keywords if kw]

        # Find line numbers of matching nodes in this file
        hit_lines: set[int] = set()
        for n in self._nodes:
            if n.get("source_file") != source_file:
                continue
            loc = n.get("source_location") or ""
            if not loc.startswith("L"):
                continue
            try:
                line_num = int(loc[1:])
            except ValueError:
                continue
            node_text = " ".join(filter(None, [
                n.get("id", ""),
                n.get("norm_label", ""),
                n.get("label", ""),
            ])).lower()
            if any(kw in node_text for kw in kws):
                hit_lines.add(line_num)

        # Text-based search: scan the actual file lines for specific keywords (≥5 chars).
        # This catches functions like `platformV3Settings` that exist in the file but
        # whose graph node is at a different location than where the function is defined.
        specific_kws = [kw for kw in kws if len(kw) >= 5]
        if specific_kws:
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                if any(kw in line_lower for kw in specific_kws):
                    hit_lines.add(i)

        if not hit_lines:
            # No matches at all — send start of file capped at 3000 chars
            return file_content[:3000]

        # Build ranges: hit line ± context_lines, clamped to file bounds
        total = len(lines)
        ranges: list[tuple[int, int]] = []
        for ln in sorted(hit_lines):
            start = max(1, ln - context_lines // 4)
            end = min(total, ln + context_lines)
            ranges.append((start, end))

        # Merge overlapping ranges
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append([start, end])

        # Assemble output with line numbers and section markers
        parts: list[str] = []
        for start, end in merged:
            header = f"# lines {start}–{end}"
            section = "\n".join(
                f"{i}| {lines[i - 1]}" for i in range(start, end + 1) if i <= total
            )
            parts.append(f"{header}\n{section}")

        return "\n\n".join(parts)


_navigators: dict[str, GraphNavigator] = {}


def get_navigator(repo_type: str = "api") -> GraphNavigator:
    """Return a per-repo GraphNavigator singleton.

    repo_type: "api" → graph_api/graph.json (Node.js)
               "cms" → graph_cms/graph.json (PHP/Laravel)
    """
    if repo_type not in _navigators:
        path = GRAPH_API_PATH if repo_type == "api" else GRAPH_CMS_PATH
        _navigators[repo_type] = GraphNavigator(path)
    return _navigators[repo_type]
