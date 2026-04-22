from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Shared data classes ───────────────────────────────────────────────────────

@dataclass
class RouteEntry:
    http_method: str
    path: str
    controller_var: str
    handler_method: str
    route_file: str


@dataclass
class RouteTargetResult:
    files: list[str]
    keywords: list[str]
    confidence: str          # "high" | "medium" | "low" | "none"
    matched_route: str
    matched_handler: str
    reasoning: str


# ── API (Express / Node.js) ───────────────────────────────────────────────────

API_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "auth": ["auth.js"],
    "login": ["auth.js"],
    "logout": ["auth.js"],
    "token": ["auth.js"],
    "session": ["auth.js"],
    "register": ["auth.js"],
    "authenticate": ["auth.js"],
    "password": ["auth.js"],
    "platform_settings": ["auth.js"],
    "user_settings": ["auth.js"],
    "payment": ["payments.js"],
    "subscription": ["payments.js"],
    "transaction": ["payments.js"],
    "voucher": ["voucher.js"],
    "coupon": ["voucher.js"],
    "persona": ["persona.js"],
    "watch": ["persona.js"],
    "asset": ["assets.js"],
    "paywall": ["paywall.js"],
    "operator": ["operators.js"],
    "telco": ["operators.js"],
}

_REQUIRE_RE = re.compile(
    r"const\s+(\w+)\s*=\s*require\s*\(\s*['\"`]([^'\"` \n]+)['\"`]\s*\)"
)
# Matches: router.METHOD('path', ...middleware, controller.method);
# The controller.method must be the final argument before the closing paren.
_ROUTE_RE = re.compile(
    r"router\.(get|post|put|patch|delete)\s*\(\s*['\"`]([^'\"` \n]+)['\"`]"
    r".*?(\w+)\.(\w+)\s*\)\s*;?\s*$",
    re.IGNORECASE,
)

_STOP_WORDS = frozenset({
    "", "the", "a", "an", "is", "in", "on", "to", "for", "of", "and", "or",
    "that", "with", "bug", "fix", "issue", "error", "not", "no",
    "user", "users",   # too generic; real matches come from "login", "auth", etc.
})


def _tokenize(text: str) -> set[str]:
    return set(re.split(r"[^a-z0-9_]+", text.lower())) - _STOP_WORDS


class RouteScanner:
    """Parses Express route files to resolve exact controller targets from issue text."""

    def __init__(self, api_root: str) -> None:
        self._api_root = Path(api_root).resolve()
        self._entries: list[RouteEntry] = []
        self._require_maps: dict[str, dict[str, str]] = {}  # filename -> {var: resolved_path}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        routes_dir = self._api_root / "routes"
        if not routes_dir.exists():
            logger.warning(f"[RouteScanner] routes/ not found at {routes_dir}")
            self._loaded = True
            return
        for js_file in sorted(routes_dir.glob("*.js")):
            try:
                self._parse_route_file(js_file)
            except Exception as exc:
                logger.debug(f"[RouteScanner] skipped {js_file.name}: {exc}")
        logger.info(
            f"[RouteScanner] loaded {len(self._entries)} routes from "
            f"{len(self._require_maps)} files in {routes_dir}"
        )
        self._loaded = True

    def _parse_route_file(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8", errors="ignore")
        file_key = path.name
        require_map: dict[str, str] = {}

        for m in _REQUIRE_RE.finditer(content):
            var_name, req_path = m.group(1), m.group(2)
            if "controller" in req_path.lower():
                try:
                    resolved = (path.parent / req_path).resolve()
                    rel = str(resolved.relative_to(self._api_root))
                    require_map[var_name] = rel
                except (ValueError, OSError):
                    # Fallback: strip leading ../ and ./
                    require_map[var_name] = re.sub(r"^(\.\./)+", "", req_path)

        self._require_maps[file_key] = require_map

        for line in content.splitlines():
            m = _ROUTE_RE.search(line)
            if m:
                self._entries.append(RouteEntry(
                    http_method=m.group(1).lower(),
                    path=m.group(2),
                    controller_var=m.group(3),
                    handler_method=m.group(4),
                    route_file=file_key,
                ))

    def find_route_targets(self, title: str, description: str) -> RouteTargetResult:
        self._load()
        tokens = _tokenize(f"{title} {description}")

        # Step 1: domain → candidate route files
        candidate_files: list[str] = []
        matched_domain = ""
        for token in sorted(tokens):  # stable order
            for kw, files in API_DOMAIN_KEYWORDS.items():
                # token.startswith(kw): "authenticate" matches kw "auth"
                # kw == token: exact match
                # NOT kw.startswith(token): avoids "user" matching "user_settings"
                if kw == token or token.startswith(kw):
                    for f in files:
                        if f not in candidate_files:
                            candidate_files.append(f)
                    if not matched_domain:
                        matched_domain = kw

        if not candidate_files:
            return RouteTargetResult(
                files=[], keywords=[], confidence="none",
                matched_route="", matched_handler="",
                reasoning="No domain keyword matched issue text — graph search will run",
            )

        # Step 2: score route entries from matched files against issue tokens
        best_entry: RouteEntry | None = None
        best_score = 0
        for entry in self._entries:
            if entry.route_file not in candidate_files:
                continue
            path_tokens = _tokenize(entry.path.replace("/", " ").replace("_", " "))
            score = len(tokens & path_tokens)
            if score > best_score:
                best_score = score
                best_entry = entry

        # Step 3: resolve controller file from require map
        controller_file: str | None = None
        if best_entry:
            rmap = self._require_maps.get(best_entry.route_file, {})
            controller_file = rmap.get(best_entry.controller_var)

        # Collect all controller files from matched route file(s) for medium fallback
        all_controllers: list[str] = []
        seen_ctrl: set[str] = set()
        for rf in candidate_files:
            for ctrl_path in self._require_maps.get(rf, {}).values():
                if ctrl_path not in seen_ctrl:
                    seen_ctrl.add(ctrl_path)
                    all_controllers.append(ctrl_path)

        if best_entry and controller_file:
            return RouteTargetResult(
                files=[controller_file],
                keywords=[],
                confidence="high",
                matched_route=f"{best_entry.http_method.upper()} {best_entry.path}",
                matched_handler=f"{best_entry.controller_var}.{best_entry.handler_method}",
                reasoning=(
                    f"Domain '{matched_domain}' → {best_entry.route_file} → "
                    f"{best_entry.http_method.upper()} {best_entry.path} → "
                    f"{best_entry.controller_var}.{best_entry.handler_method} → "
                    f"{controller_file}"
                ),
            )

        if all_controllers:
            return RouteTargetResult(
                files=all_controllers[:3],
                keywords=[],
                confidence="medium",
                matched_route="",
                matched_handler=", ".join(all_controllers[:3]),
                reasoning=(
                    f"Domain '{matched_domain}' → {', '.join(candidate_files)} → "
                    f"{len(all_controllers)} controller(s) resolved "
                    f"(no specific route path match)"
                ),
            )

        return RouteTargetResult(
            files=[f"routes/{f}" for f in candidate_files],
            keywords=[],
            confidence="low",
            matched_route="",
            matched_handler="",
            reasoning=(
                f"Domain '{matched_domain}' → {', '.join(candidate_files)} → "
                f"controller resolution failed"
            ),
        )


# ── CMS (Laravel / PHP) ───────────────────────────────────────────────────────

CMS_DOMAIN_CONTROLLERS: dict[str, list[str]] = {
    "region": ["RegionController"],
    "user": ["UserController"],
    "series": ["SeriesController", "SeasonController"],
    "content": ["ContentController", "AssetController"],
    "payment": ["PaymentController", "SubscriptionController"],
    "voucher": ["VoucherController"],
    "operator": ["OperatorController"],
    "banner": ["BannerController"],
    "category": ["CategoryController"],
    "live": ["LiveChannelController"],
    "role": ["RoleController"],
    "permission": ["PermissionController"],
    "bundle": ["BundleController"],
    "device": ["DeviceController"],
    "zone": ["ZoneController"],
}

_CMS_CTRL_PATH = "app/Http/Controllers/{}.php"


class CMSControllerMatcher:
    """Maps issue domain keywords to Laravel controller classes.

    PHP graph has class-level nodes, so injecting the controller class name as a
    priority graph keyword gives a near-exact hit without any file I/O.
    """

    def find_cms_targets(self, title: str, description: str) -> RouteTargetResult:
        tokens = _tokenize(f"{title} {description}")
        matched_classes: list[str] = []
        matched_domain = ""

        for token in sorted(tokens):
            for domain, classes in CMS_DOMAIN_CONTROLLERS.items():
                if domain == token or token.startswith(domain):
                    for cls in classes:
                        if cls not in matched_classes:
                            matched_classes.append(cls)
                    if not matched_domain:
                        matched_domain = domain

        if not matched_classes:
            return RouteTargetResult(
                files=[], keywords=[], confidence="none",
                matched_route="", matched_handler="",
                reasoning="No CMS domain keyword matched — graph search will run",
            )

        files = [_CMS_CTRL_PATH.format(cls) for cls in matched_classes]
        confidence = "high" if len(matched_classes) == 1 else "medium"
        return RouteTargetResult(
            files=files,
            keywords=matched_classes,
            confidence=confidence,
            matched_route="",
            matched_handler=", ".join(matched_classes),
            reasoning=(
                f"Domain '{matched_domain}' → {', '.join(matched_classes)} "
                f"({'1 unambiguous match' if confidence == 'high' else f'{len(matched_classes)} matches'})"
            ),
        )
