"""
Pipeline targeting dry-run.

Edit the REQUIREMENT section below, then run:
    venv/bin/python3 tests/test_pipeline_targeting.py

NO code generation. NO GitHub PRs. Shows which files would be targeted.
"""

import os
import sys
import textwrap
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so OPENAI_API_KEY / ANTHROPIC_API_KEY etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    # Fallback: parse .env manually if python-dotenv not installed
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        for _line in open(_env_path):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ══════════════════════════════════════════════════════════════════════════════
#  ✏️  EDIT YOUR REQUIREMENT HERE
# ══════════════════════════════════════════════════════════════════════════════

TITLE = "zone level playback rung ceiling"

DESCRIPTION = """

Goal
One PIN, one endpoint, more clients.

Keep the existing POST /v2/persona/set_parental_control endpoint and its request shape — no rename, no new route.
Reuse the same stored parental PIN to gate explicit content (no second PIN column, no second endpoint).
Ship the set / update UI to CTV platforms that currently only know how to verify the PIN — that's the main net-new work.
This matches the direction already captured in an indexed Loop DD: "Reuse the existing parental PIN system. No new PIN endpoints. verify_parental_pin, set_parental_control, and POST /v3/persona/stream (which already accepts parentalPin) are extended, not replaced."
Today
Verified from the indexed corpus:

Stack	Has set/update UI?	Notes
wlb_webapp (Angular)	✅	parental-control.component.ts (4-digit OTP config, step state, ParentalControlService)
wlb_android mobile	✅	PinControlFragment.kt + PinControlViewModel.kt::updateUserPin POSTs to UrlConstants.SET_PARENTAL_CONTROL
wlb_android TV (tvapp)	✅	tvapp/.../PinControlHelper.kt::showPinControlDialog
wlb_ios (mobile)	✅	PinVC.swift, PinControlVC.swift
ott-tv-app (React)	✅	apps/web/src/components/settings/ParentalSection.tsx; already has useParentalGate hook in packages/core/src/hooks/useParentalGate.ts
wlb_paywall (Angular)	⚠️ needs check	PIN modal under settings — likely partial
wlb_stb (Lightning)	❌ verify-only	src/Components/PinControl/index.js used for validate; Views/HlsLivePlayer.js + DashLivePlayer.js call verify
wlb_stb_vimeo (Lightning)	❌ verify-only	Mirrors wlb_stb
wlb_roku	❌ verify-only	apiLogic.brs exposes PIN-related calls; no set-UI component found
wlb_tizen_lgwebos	❌ verify-only	No set-UI grounded in the corpus
Apple TV (TVApp target in wlb_ios)	❌ needs confirm	TVApp-scoped PIN-set UI not found; mobile target has it

Backend:

Storage: single column on wlb_api/models/user_profiles.js (existing parental PIN column). No schema change.
Explicit-content gate already goes through wlb_api/services/persona_access_service.js; same validation path as parental.
persona.service.js::mapRequestParams maps frontend parentalPin → backend access_pin. Keep as-is.
Verify handler: wlb_api/grpc/handlers/persona.handler.js::verifyParentalPin — reused for explicit.
Proposed
Backend — ≈ zero code change

Keep SET_PARENTAL_CONTROL endpoint + request shape unchanged.
Explicit-content gate reads the same PIN. If persona_access_service.js already resolves both flows (most signs say yes), this is a config change only: a tenant setting like explicit_pin_reuses_parental (or re-point the existing explicit_pin feature flag to the parental column). Confirm in implementation.
i18n: add (or reuse) copy keys for "Enter your parental/explicit content PIN" — single set of strings; no branching by PIN type.
No new fields in the request body. age_limit_value, access_pin, is_parental_control_enabled, device_type, locale, region, optional profile_id stay as-is.
Frontend — net-new set/update UI on CTV
Platforms below already have a verify-PIN popup. The set-PIN screen is what's missing. Each one ships:

Settings entries "Parental control" AND "Explicit content" (each gated by its tenant flag — §Feature-flag gating).
The 4-digit entry component they already have for verify, reused in set/confirm mode.
An age selector before the PIN input (see §Set-PIN UX flow below).
A POST to /v2/persona/set_parental_control with the body defined above (identical to what Android mobile sends today).
Explicit-PIN flow — distinct from Parental (admin-shared starting PIN)
Explicit content has a different starting condition from parental and so has a different UX flow. The endpoint + data layer are still the same as parental (§API endpoints to call, POST /v2/persona/set_parental_control for writes), but the verify-current-PIN step uses a different endpoint — POST /v3/persona/explicit-pincheck — which already exists in wlb_api/services/persona.service.js::explicitPinCheck.
Starting condition. For the explicit flow, an admin shares the initial PIN to the end user out-of-band (email, phone, onboarding mail). There is no "first-time set from scratch" surface in the app — the user always starts with a PIN the admin has provisioned. The app's job is to validate that starting PIN, then let the user rotate it to their own value.
Screen sequence (Explicit flow):
[Settings] → "Explicit content"
    │
    ▼
Step 1 — Enter the CURRENT PIN
         POST /v3/persona/explicit-pincheck
             { parentalPin: <entered>, profileId: <current_profile> }
         ← (do NOT send page_type here — see below)

         On 200: proceed to Step 2.
         On 422 errCodes: ['pinInvalid']     → show "Incorrect PIN" (remaining attempts).
         On 422 errCodes: ['tooManyPinAttempts'] → rate-limit state (5 attempts / 15 min).
         On 422 errCodes: ['explicitContentDisabled'] → tenant hasn't enabled the feature; hide the entry entirely.
         On 422 errCodes: ['invalidProfileId'] → bug; profile mismatch.
    │
    ▼
Step 2 — Enter a NEW PIN (4 digits) + Confirm PIN.
         POST /v2/persona/set_parental_control
             { access_pin: <newPin>,
               old_access_pin: <the PIN validated in Step 1>,
               is_parental_control_enabled: 1,
               age_limit_value: <tenant explicit-threshold default>,
               profile_id, device_type, locale, region }
    │
    ▼
Step 3 — Success screen; user now uses the new PIN everywhere (both parental + explicit, since they're the same stored PIN — §*Goal*).


page_type field — when to pass it and when not to:
explicit-pincheck accepts an optional page_type field that controls a post-validation side effect:

page_type on the request	Backend side effect	When the frontend should pass it
"content"	Creates a 15-min Redis session key explicit_access:{user.id}:{profile.id}:{deviceId} (TTL from explicitConfig.redis_expiry, default 900 s). Playback endpoints then see explicitUnlocked: 1 and skip the PIN prompt for the remaining session.	ONLY when the user just validated the PIN in a content-viewing context (an explicit video about to play). This is the "unlock explicit content for 15 min" flow.
absent / any other value (e.g. "settings" or omitted)	PIN is validated; no session key created. The response just confirms the PIN was correct.	In the Settings PIN-change flow (this DD's Step 1 above). The frontend isn't unlocking content — it's gating the "let me change the PIN" screen. Creating an explicit_access session here would accidentally unlock content for 15 min every time an admin-shared-PIN is rotated.

The frontend teams MUST make the distinction explicit:

In the Settings "change PIN" flow → call explicit-pincheck without page_type (or with page_type: "settings" if the team wants the grep-ability). The user is not entitled to 15 min of free content for logging into settings.
In the content-viewing flow (clicking an explicit title) → call explicit-pincheck with page_type: "content" so the unlock session kicks in.
These are already distinct code paths on every frontend (Settings screen vs playback-entry dialog); the ask is to not accidentally share the POST body between them.
Rate limit behaviour (both flows). 5 failed attempts per (user.id, profile.id) within 15 min lock the PIN at tooManyPinAttempts. This applies to both the content-unlock path AND the settings-change path — a user who mistypes 5 times in Settings is also locked out of content for 15 min on the same profile. Frontends should show the remaining-attempts count in both places.
Why the endpoint is named explicit-pincheck even though the same PIN serves parental:
The endpoint name dates to when explicit had a separate PIN (pre-unification); it's kept for back-compat and because it carries the explicit-specific side effect (the explicit_access session) that the parental verify path doesn't. Don't reuse POST /v2/persona/content/verify_parental_pin for the explicit flow — the rate-limit counter + the session-key TTL + the explicitContentDisabled feature-flag check only live in explicit-pincheck.
Design (CTV "Change Pin" mockup — shared 2026-04-21)
Studio shared a CTV mockup for the Settings → Change Pin flow. Six states in the mockup, left to right:

#	State	Notes
1	Settings landing — left-nav item "Change Pin" under the Parental Control group	Entry point; renders as a row in the settings list, not a toggle. Standard CTV left-nav layout.
2	Modal — "Current parental pin" — empty 4-digit input — Next / Cancel	Default keyboard variant (CTV remote number keys).
3	Modal — "Current parental pin" — typing • • • • — Next / Cancel	Virtual keyboard variant (on-screen numpad, D-pad driven).
4	Modal — "Current parental pin" — input filled, inline red error message under the input, modal stays open	Wrong-PIN response from /v3/persona/explicit-pincheck. Error text is a direct render of the pinInvalid / tooManyPinAttempts i18n string.
5	Modal — "New parental pin" — 4-digit input — Next / Cancel	After Step 1 succeeds. Step 2 entry.
6	Modal — "New parental pin" — 4-digit input — Submit / Cancel	Final state before confirming; Submit triggers POST /v2/persona/set_parental_control with access_pin + old_access_pin.

Design decisions implicit in the mockup — every frontend implementing this flow MUST follow these:

Label: the UI says "parental pin" in both Current and New screens, even though this is the Explicit flow entry. Consistent with the unified-PIN design — there's one shared PIN on user_profiles.access_pin; the label in the UI doesn't need to branch on context. Keep the string as "parental pin" (or the tenant's localised equivalent) in both Parental and Explicit Settings flows — no "Explicit PIN" string in Settings.
Two-button modal: Next (primary, right-aligned) and Cancel (secondary, left-aligned). No Back, no Save. Submit replaces Next only on the final New-PIN screen.
Error surfacing is inline, not a separate screen or toast. On pinInvalid the modal stays open, input is cleared, red text appears under the input ("Incorrect PIN. 4 attempts remaining."). On tooManyPinAttempts the modal still stays open but input is disabled + error reads "Too many failed attempts. Try again in 15 minutes."
Both keyboard input methods are first-class — default (remote number keys) and virtual (on-screen numpad) must both accept 4-digit PIN entry. D-pad focus moves: input → Next → Cancel → input. Pressing the remote's number keys enters digits regardless of which keyboard is shown.
Modal cancel: Cancel and remote-back both close the modal and return to Settings without any API call. No half-state.
Confirm-new-PIN step — platform-owner decision:
The mockup shows Current → New → Submit (two steps, no separate Confirm). That's the minimum happy path for CTV where D-pad input makes each additional step costly. Platform owners who want an extra Confirm step — specifically wlb_webapp (Angular, physical keyboard) and ott-tv-app on mobile layouts — may add a third "Confirm new PIN" screen before Submit, to guard against typo'd irrecoverable changes. The CTV stacks should stick to the 2-step shape from the mockup.
Flow summary (maps the mockup to the endpoints):
Settings list → user selects "Change Pin"
      │
      ▼
(mockup state 2/3)  Current parental pin dialog
      POST /v3/persona/explicit-pincheck
          { parentalPin, profileId }             ← no pageType (Settings context)
      ↓ 200 OK
      │
      │  ↳ on 422 / pinInvalid → (state 4) inline error, modal stays open
      │  ↳ on 422 / tooManyPinAttempts → disabled input, cooldown message
      │
      ▼
(mockup state 5/6)  New parental pin dialog
      POST /v2/persona/set_parental_control
          { access_pin: <newPin>,
            old_access_pin: <the PIN just validated>,
            is_parental_control_enabled: 1,
            age_limit_value: <tenant default>,
            profile_id, d_type, locale, region }
      ↓ 200 OK
      │
      ▼
Back to Settings; subsequent explicit-content attempts prompt for the new PIN.


Set-PIN UX flow — applies to BOTH parental AND explicit
Every set/update screen supports age OR PIN (either, or both) — not a forced bundle. The backend already supports this: wlb_api/services/persona_access_service.js::setParentalControl only hashes access_pin when it's present on the request, and age_limit is always updated from age_limit_value. So the POST can legitimately carry just the age, just the PIN, or both. The one hard rule: the request must change at least one thing (age, PIN, or toggle).
First-time setup (no PIN yet) — the user DOES need to provide both age and PIN in the same flow (because neither exists), but they're still separate fields on the form, not a coupled validator. If the user adjusts only age and submits before entering a PIN, the backend updates age and the UI leaves the "Set PIN" prompt active.
Screen sequence (both flows):
[Settings] → "Parental control" | "Explicit content"
    │
    ├─ (no PIN yet)                                  ← is_pin_already_set = 0
    │   Shown on one screen:
    │     • Age limit selector (from age_limits[])
    │     • New PIN (4 digits)
    │     • Confirm PIN
    │   Submit rule: at least one of {age_limit_value, access_pin} changed.
    │   Typical first-time submission: BOTH fields → POST /v2/persona/set_parental_control
    │
    └─ (PIN already set)                             ← is_pin_already_set = 1
        Entry requires old PIN (identity check).
        Then any of these can be updated independently:
          • Change PIN       → new PIN + confirm   → POST with { access_pin, age_limit_value (unchanged from profile) }
          • Change Age Limit → age selector        → POST with { age_limit_value } only — no access_pin
          • Toggle OFF       → switch              → POST with { is_parental_control_enabled: 0 }
        Each of these is a legal standalone request.


Age handling per flow:

Parental — user picks from age_limits[] returned in the account / platform-settings response (e.g. [7, 13, 16, 18]).
Explicit — same field (age_limit_value); default pre-selection is the tenant's explicit-threshold age (usually 18). Team MAY hide the picker behind a "default applies" link; the request still sends age_limit_value because the backend always writes it, but nothing forces the user to touch it.
Key UI rules (lifted in all stacks):

Confirm-PIN step is mandatory when a new PIN is being entered; not required when the user is only changing the age.
Old-PIN step is mandatory on update when a PIN is being changed; not required when the user is only changing the age (i.e. age updates don't need to re-enter the existing PIN — operator can revisit if desired).
Age selector surfaces only the values in age_limits[]. No free-form entry.
Submit button stays disabled until at least one field has changed from its current value.
Error surface renders backend errCodes (e.g. pinNotSet, 4031) via existing i18n in wlb_cms/resources/lang/en-US/messages.php.

Stack	What to add	Reference
wlb_roku (BrightScript)	Settings → Parental Control + Explicit Content screens. Explicit flow: Step 1 current-PIN entry → POST /v3/persona/explicit-pincheck (no pageType) → Step 2 new-PIN + confirm → POST /v2/persona/set_parental_control. Reuse existing PIN keypad component via apiLogic.brs.	Mirror PinControlFragment.kt flow.
wlb_stb (Lightning)	Settings screens (both). Explicit: reuse Components/PinControl/index.js keypad for both steps; wire to /v3/persona/explicit-pincheck then /v2/persona/set_parental_control.	Lightning Input + existing PinControl widget.
wlb_stb_vimeo (Lightning)	Same as wlb_stb.	Share a single widget if the two repos consolidate.
wlb_tizen_lgwebos	Settings screens (both). Explicit: Step 1 /v3/persona/explicit-pincheck + Step 2 /v2/persona/set_parental_control via Service.js axios helper.	Mirror parental-control.component.ts structure.
Apple TV (TVApp target in wlb_ios)	Set-PIN view controller with the two-step Explicit flow (verify current → set new); mirror PinVC.swift / PinControlVC.swift from the mobile target. Add explicitPinCheck request in APIEndpoints.swift (copy shape from personaPinValidation but point at /v3/persona/explicit-pincheck; page_type is omitted for the Settings flow, passed as "content" for the playback-unlock flow).	Reuse the same view model / API endpoint.
wlb_webapp (Angular)	Confirm/close the gap vs webapp; add explicit-content entry + the two-step Explicit flow (verify via /v3/persona/explicit-pincheck, then change via /v2/persona/set_parental_control).	Small.
wlb_android (mobile + TV)	Add the Explicit Settings entry alongside the existing Parental entry. Explicit flow: Step 1 POST /v3/persona/explicit-pincheck (without pageType — don't create a content-unlock session in Settings); Step 2 POST /v2/persona/set_parental_control with new PIN + old_access_pin. Existing PinControlHelper/PinControlFragment handles the UI; just add the second step to the ViewModel.	PinControlViewModel.kt already POSTs to SET_PARENTAL_CONTROL — add a sibling UpdatePinApi.checkExplicitPin call in front.
wlb_ios (mobile TV2ZProduct)	Same as Apple TV above; mirror the existing PinVC.swift and add the Step-1 explicit-check call before the Step-2 set call.	—
ott-tv-app (React)	apps/web/src/components/settings/ParentalSection.tsx already has the Parental flow; add an ExplicitSection.tsx sibling that uses the two-step flow. packages/api/src/endpoints/ needs a new explicitPinCheck export.	—

API endpoints to call (existing, unchanged)

Purpose	Method + Path	Handler
Set / update PIN, toggle, age limit (parental + explicit writes)	POST /v2/persona/set_parental_control	wlb_api/services/persona_access_service.js::setParentalControl
Verify PIN at playback (parental flow)	POST /v2/persona/content/verify_parental_pin	wlb_api/services/persona_access_service.js::verifyParentalPin
Stream with PIN inline (already accepts parentalPin)	POST /v3/persona/stream	Existing; accepts parental_pin in playback_preferences context
Verify PIN for the explicit flow — both "unlock content for 15 min" and "validate current PIN before the Settings change-PIN screen"	POST /v3/persona/explicit-pincheck	wlb_api/services/persona.service.js::explicitPinCheck

All four are reused as-is. No new path. CTV clients need to call /v2/persona/set_parental_control (set/update) + /v3/persona/explicit-pincheck (verify for the explicit Settings flow) in addition to the parental verify endpoint they already use.
Request / response — POST /v3/persona/explicit-pincheck
Request body:

Field	Type	Required	Notes
parentalPin	string (4 digits)	yes	The PIN the user just entered (same shared column as parental — see §Goal). Field name is historical; do NOT rename.
profileId	string (uuid or numeric)	yes	Profile context; backend validates the profile belongs to the authenticated user.
pageType	string	conditional	Pass "content" only in the content-viewing unlock flow (creates a 15-min explicit_access session key). Omit (or pass "settings") in the Settings change-PIN flow — see the flow explainer above for why.

Auth: standard JWT. Common headers (token, Content-Type: application/json) as every other wlb_api call.
Response:
// 200 — PIN valid.
// When pageType=="content": backend has ALSO created a 15-min session
// key (explicit_access:{user}:{profile}:{device}); subsequent /v3/persona/stream
// calls on the same device-profile will see explicitUnlocked: 1 and skip the prompt.
// When pageType is absent / any other value: no session key; the response
// simply confirms the PIN was correct.
{ "status": 200 }

// 422 — various failure modes
{ "status": 422, "errCodes": ["pinInvalid"] }             // wrong PIN
{ "status": 422, "errCodes": ["tooManyPinAttempts"] }     // 5 fails / 15 min per (user, profile)
{ "status": 422, "errCodes": ["explicitContentDisabled"]} // feature flag off — frontend should have hidden the entry
{ "status": 422, "errCodes": ["invalidProfileId"] }       // profile doesn't belong to caller


Rate-limit behaviour: explicit_pin_attempts:{user.id}:{profileId} in Redis, 5 attempts / 900 s. Resets on any successful validation OR after the TTL expires. The counter is shared across BOTH the content-unlock and Settings flows — so a user who mistypes 5 times in Settings is also locked out of content-unlock on the same profile for 15 min. Show the remaining attempts in both surfaces.
Request / response — POST /v2/persona/set_parental_control
Request body (every field ground-truthed from the service + current callers — Android UrlConstants.SET_PARENTAL_CONTROL, iOS Constants.APIMethods.setParentalControl = "v2/persona/set_parental_control", indexed Loop DD):

Field	Type	Required	Notes
access_pin	string (4 digits)	conditional	Required when setting/changing the PIN. Omit for "toggle only" or "age-limit-only" updates. Backend hashes via hashString(…) and stores on user_profiles.access_pin.
age_limit_value	int	conditional	Required when the age is being set or changed; MAY be omitted by clients that only toggle or only update the PIN — current client callers always include it, and the backend always writes it. Stored as age_limit.
is_parental_control_enabled	0 or 1	yes	Toggle. Stored as pin_control.
profile_id	string (uuid or numeric)	conditional	Required when the profiles feature is on.
device_type	string	yes	d_type — android, ios, web, ctv, roku, lgwebos, tizen, stb, appletv, …
locale	string	yes	e.g. en-US.
region	string	yes	e.g. int.

Auth: standard JWT (existing auth middleware). Common headers (token, Content-Type: application/json) as every other wlb_api call.
Response
// 200 OK
{ "status": 200, "message": "Parental control settings updated" }

// 422 — profile not found
{ "status": 422, "code": 4031 }

// 422 — PIN not set (user tried to update but never had one)
{ "status": 422, "errCodes": ["pinNotSet"] }


PIN-length rule: setting('parental_control_pin_bypass') sets the configured length (4 by default) — validated in wlb_api/middleware/validation/persona.js.
Request — POST /v2/persona/content/verify_parental_pin (for completeness — CTV already uses this)
Grounded in wlb_tizen_lgwebos/src/controller/Service.js (existing caller) + persona_access_service.js::verifyParentalPin:
{
  "access_pin":     "1234",
  "content_id":     "<slug>",
  "content_type":   "video",            // 'series' is coerced to 'video' in the Tizen caller
  "streaming_type": "hls",              // or "dash"
  "supports_drm":   "1",
  "profile_id":     "<uuid>",
  "d_type":         "lgwebos",
  "locale":         "en-US",
  "region":         "int"
}


Response: 200 OK on match (returns a PersonaAsset / LiveChannelContentDetails payload); 404 / 4003 user missing; 422 / 4031 profile missing; PIN mismatch surfaces as a 4xx with the standard lockout-aware shape.
The same PIN gates both

Parental — age-limited programs. Existing behaviour; no change.
Explicit content — persona_access_service.js::verifyParentalPin (+ the same hashed access_pin on user_profiles) is the single source. The explicit-content gate is config-toggled on to reuse this flow; no second column, no second endpoint.
Feature-flag gating — current state and the gap
Both parental and explicit features already have tenant-level flags on the backend, but frontend enforcement is inconsistent. If we ship CTV set-PIN without closing this, a tenant that has parental control turned OFF will still see the "Parental control" settings entry on some platforms.
What exists today
Backend flags (wlb_cms/app/Helpers/feature_flags.php):

parental_control_module_enabled() → Setting::get('parental_control') — tenant switch for parental.
explicit_content_enabled() → Setting::get('explicit_config').enabled — tenant switch for explicit (JSON-configured).
purchase_pin() → Setting::get('purchase_pin') — separate purchase-PIN flag (not in scope for this DD).
Per-user state (from wlb_api/services/user_auth_service.js::dataFromUser — lands in login / /userdata responses):

is_parental_control_enabled (0/1) — per-user toggle.
is_pin_already_set (0/1) — does this user have a PIN stored.
set_age_limit, age_limits[].
Tenant flag exposed to frontends:

docs/api/components/schemas/helper.js defines isParentalControlEnabled = "Flag indicating if parental control is enabled for the operator" — emitted as part of platform-settings / account payload.
ott-tv-app reads it as enableParentalControls in packages/core/src/store/platform/slice.ts.
Per-frontend gating — who checks what

Frontend	Tenant flag (parental_control)	User flag (is_parental_control_enabled, is_pin_already_set)	Explicit flag (explicit_config.enabled)
ott-tv-app (React)	✅ platformStore.enableParentalControls; useParentalGate hook takes enabled prop (packages/core/src/hooks/useParentalGate.ts)	✅ requiresPin(contentRatingCode, profileMaxRating) compares per-content + per-profile	⚠️ no dedicated enableExplicit flag in store today — gap
wlb_webapp (Angular)	✅ settingsService.parentalControlModuleEnabled (main-account.component.ts::pinCloseControl)	✅ parentalControl.is_pin_already_set, is_parental_control_enabled (parental-control.component.ts::ngOnInit)	⚠️ no explicit-flag check grounded — gap
wlb_android mobile	❌ no tenant-flag check grounded — PinControlHelper.kt::showPinControlDialog shows unconditionally when called; only user-level gate via isPinAlreadySet	✅ user-level (is_pin_already_set, is_parental_control_enabled) via PreferencesManager	❌ gap
wlb_android TV (tvapp)	❌ no tenant-flag check grounded — ExoLivePlayerActivity.kt::checkAndStartPlayback gates on per-content channelPersona.askAccessPin == 1	✅ backend-driven per-content	❌ gap
wlb_ios + Apple TV	❌ no tenant-flag check grounded — PinVC.swift::activatePin reads only isParentalControlOn (user-level)	✅ user-level	❌ gap
wlb_roku	❌ no set-UI anyway; verify is backend-signal-driven	⚠️ user-level via platformSettingModel.brs parsed fields	❌ gap
wlb_stb	❌ verify-only; backend-driven per-content	⚠️ user-level	❌ gap
wlb_tizen_lgwebos	❌ Profile.js reads is_parental_control_enabled + is_pin_already_set but no tenant-flag check	✅ user-level	❌ gap

Summary of the gap: ott-tv-app + wlb_webapp are the only frontends that gate the settings-UI entry on the tenant flag. Mobile Android/iOS, Tizen/LG, Roku, STB rely on the backend to refuse service per-content but still surface the settings screen — so a tenant with parental_control = 0 still sees "Parental control" in settings. No frontend has a dedicated explicit-content feature flag (there's i18n + backend support, but no exposed UI toggle like enableExplicit).
Proposed gating contract (every frontend, consistent)
Two tenant flags must be surfaced inside /v3/auth/platform_settings → frontends consume the same shape. ott-tv-app already has the pattern (enableParentalControls); extend it.

Platform-settings field	Source	Frontend use
enable_parental_control (bool)	parental_control_module_enabled()	If false → hide the settings entry entirely; skip any pin dialog; backend still the source of truth if something slips through
enable_explicit_content (bool)	explicit_content_enabled()	If false → do not show any "Explicit content" toggle, never invoke verify_parental_pin with explicit intent
explicit_uses_parental_pin (bool, default true)	NEW tenant setting (or piggyback on explicit_config)	Frontend uses this to know whether a single PIN gates both flows or if explicit was split out later

Per-user fields stay exactly as today:

is_parental_control_enabled — per-profile toggle (user chose to turn on).
is_pin_already_set — has a PIN been saved.
set_age_limit, age_limits[].
Decision matrix the UI applies (single source of truth per platform)
Every frontend's Settings > Parental / Explicit screen and every pin-prompt dialog uses the same gate:
if not tenant.enable_parental_control        -> hide entry entirely
else if not user.is_parental_control_enabled -> show toggle; PIN input disabled
else if not user.is_pin_already_set          -> "Set PIN" flow
else                                         -> "Change PIN / toggle age limit" flow

# explicit path
if not tenant.enable_explicit_content        -> no explicit toggle anywhere
else if explicit_uses_parental_pin           -> reuse parental gate + same PIN
else                                         -> out of scope (second PIN, not this DD)


This one block lifted into each platform keeps behaviour consistent without new endpoints.
Minimal code changes per frontend to close the gating gap

Frontend	Change	Effort
wlb_android mobile, TV	Read enable_parental_control / enable_explicit_content from PreferencesManager; gate settings entry + dialog trigger	S
wlb_ios + Apple TV	Same — surface the flags on AppConfiguration / UserDefaults.APIConfigObj; gate in view-model	S
wlb_roku	Parse flags in platformSettingModel.brs; gate settings-screen entry + dialog	S
wlb_stb	Same — parse flags from platform-settings response; gate entries	S
wlb_tizen_lgwebos	Add reads in Service.js/Profile.js; gate settings entry + dialog	S
ott-tv-app	Add enableExplicitContent to platform slice; plumb into explicit-content toggle	S
wlb_webapp	Add enableExplicitContent to settingsService; plumb into explicit toggle	S

Each ≤ 1 day. Bundle with the CTV set-UI work so it lands together — no separate rollout.
Edge cases

Case	Behaviour
User never set a PIN, tries to watch explicit content	Frontend opens the same "Set PIN" flow (explicit path is no-op until PIN is set).
User disables parental control (is_parental_control_enabled = 0)	Explicit-content gate still applies (kept on), OR both turn off — operator-configurable via tenant setting. Default: both toggle together.
User changes the PIN	Affects both parental and explicit immediately.
CTV device types not previously sending PIN	Accepted — device_type=ctv/roku/tizen/lgwebos/stb flow through existing handler.
Rate limit / lockout	Existing lockoutAttempts in wlb_api/services/user_auth_service.js applies per user; no per-type split.
Profiles feature on	profile_id scopes the PIN exactly as today.

Testing

Unit: backend handler unchanged — regression-test only (same fixtures).
Contract: shared 4-digit fixture exercised on every CTV platform; success + wrong-old-PIN + lockout paths.
Explicit gate: one integration test asserting "PIN set via SET_PARENTAL_CONTROL unlocks an explicit-content asset on verify".
Manual QA: set PIN on one device, log into another device of the same account, assert both parental-locked and explicit-locked content honour it.
Acceptance

POST /v2/persona/set_parental_control endpoint + request body unchanged (still accepts access_pin, age_limit_value, is_parental_control_enabled, profile_id, d_type, locale, region).
POST /v2/persona/content/verify_parental_pin continues to resolve explicit-content gating with the same stored PIN (no second column).
Set/update PIN screen lives on wlb_roku, wlb_stb, wlb_stb_vimeo, wlb_tizen_lgwebos, Apple TV (gaps filled) and posts to /v2/persona/set_parental_control.
Same user can set the PIN on mobile/web and use it on CTV, and vice versa.
Tenant toggle explicit_pin_reuses_parental (or equivalent) documented and on by default.
Every frontend gates the settings entry and any PIN dialog behind enable_parental_control (and enable_explicit_content for the explicit flow) surfaced from /v3/auth/platform_settings. Tenants with parental control off see no "Parental control" entry anywhere.
The decision matrix in §Feature-flag gating is the single source of truth on every platform — no per-stack forks.
Set/update flow supports age OR PIN (OR both) — not a forced bundle. Both parental and explicit screens expose the age-limit selector alongside the PIN input. A submission is valid if at least one of age_limit_value or access_pin has changed. Confirm-PIN is required only when a new PIN is being entered; old-PIN is required only when a PIN is being changed. Age-only updates don't require re-entering the existing PIN.
Explicit flow uses the two-step verify-then-set pattern. On every frontend that exposes the Explicit Settings screen (per the per-platform table), the user enters the admin-shared PIN as Step 1 (calling POST /v3/persona/explicit-pincheck), then the new PIN in Step 2 (calling POST /v2/persona/set_parental_control). The admin-shared PIN is never set via the app; it always arrives out-of-band.
page_type is passed correctly per context. Settings change-PIN flow: pageType omitted (or "settings") — no explicit_access Redis session created. Content-viewing unlock flow: pageType: "content" — 15-min session created. A grep across each frontend's explicit-PIN call-sites should find at most two distinct invocations (one per context); any third invocation is a bug.
Rate-limit surfacing. Both the Settings and content-unlock flows surface the remaining-attempts count on pinInvalid and show a 15-min cooldown message on tooManyPinAttempts. Shared counter across flows is documented in the error toast.
Provenance (short)

Today's set-PIN set: wlb_webapp/.../parental-control.component.ts; wlb_android/.../PinControlViewModel.kt, UpdatePinApi.kt, tvapp/.../PinControlHelper.kt; wlb_ios/.../PinVC.swift, PinControlVC.swift; ott-tv-app/.../ParentalSection.tsx.
Today's verify-only CTV: wlb_stb/src/Components/PinControl/index.js, Views/HlsLivePlayer.js, DashLivePlayer.js; Roku apiLogic.brs.
Backend — shared PIN write path: wlb_api/services/persona.service.js::mapRequestParams, services/persona_access_service.js, grpc/handlers/persona.handler.js::verifyParentalPin, models/user_profiles.js.
Backend — explicit-pincheck endpoint (verify-current flow): wlb_api/services/persona.service.js::explicitPinCheck (chunk 25/26) — URL POST /v3/persona/explicit-pincheck, gated on isExplicitContentEnabled(), rate-limited 5/15min via Redis key explicit_pin_attempts:{user.id}:{profileId}, side-effect explicit_access:{user.id}:{profileId}:{deviceId} Redis session when pageType === 'content'. Loop DD Explicit PIN Validation API confirms the /v3/persona/explicit-pincheck path.
Shared gating hook (React): ott-tv-app/packages/core/src/hooks/useParentalGate.ts.

"""

# ══════════════════════════════════════════════════════════════════════════════
#  Nothing below needs editing
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(format="  %(name)s | %(message)s", level=logging.INFO, stream=sys.stdout)
for _lib in ("httpx", "httpcore", "openai", "anthropic", "urllib3"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

from scripts._llm_loader import load_llm
from core.agents.meta_planner import MetaPlannerAgent
from core.agents.planner_agent import PlannerAgent
from core.utils.graph_navigator import get_navigator
from core.utils.route_scanner import CMSControllerMatcher, RouteScanner

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_API_ROOT = os.path.normpath(os.path.join(_PROJECT_ROOT, "..", "hackathon_wlb_api"))


def _section(title: str) -> None:
    print(f"\n{'━' * 72}")
    print(f"  {title}")
    print(f"{'━' * 72}")


def _wrap(text: str) -> str:
    return textwrap.indent(textwrap.fill(text.strip(), width=66), "    ")


def _route_first_preview(title: str, spec: str, repo_type: str) -> dict:
    """Run route-first layer without LLM — fast, no API call."""
    if repo_type == "api":
        r = RouteScanner(_API_ROOT).find_route_targets(title, spec)
        return {"confidence": r.confidence, "files": r.files,
                "route": r.matched_route, "handler": r.matched_handler,
                "reasoning": r.reasoning, "keywords": []}
    else:
        r = CMSControllerMatcher().find_cms_targets(title, spec)
        return {"confidence": r.confidence, "files": r.files,
                "route": "", "handler": r.matched_handler,
                "reasoning": r.reasoning, "keywords": r.keywords}


def run() -> None:
    title = TITLE.strip()
    description = DESCRIPTION.strip()

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║          PIPELINE TARGETING DRY-RUN (no code gen, no PR)            ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"\n  Title       : {title}")
    print(f"  Description :")
    print(_wrap(description))

    os.chdir(_PROJECT_ROOT)
    print("\n  Loading LLM …", flush=True)
    llm = load_llm()
    print("  LLM ready.\n")

    # ── STAGE 0: MetaPlannerAgent ─────────────────────────────────────────────
    _section("STAGE 0 │ MetaPlannerAgent — repo routing + specs")
    print("  Calling LLM …", flush=True)
    t0 = time.time()
    meta_plan = MetaPlannerAgent(llm).plan(title, description)
    print(f"  Done in {time.time() - t0:.1f}s\n")

    print(f"  repos (execution order) : {meta_plan.repos}")
    print(f"  reasoning               : {meta_plan.reasoning}")
    print(f"  shared_context          :")
    print(_wrap(meta_plan.shared_context or "(none)"))

    for repo in meta_plan.repos:
        print(f"\n  ── {repo.upper()} ──")
        print(f"  seed keywords : {meta_plan.keywords_for(repo)}")
        print(f"  spec          :")
        print(_wrap(meta_plan.spec_for(repo) or "(none)"))

    # ── STAGE 1 (per repo): Route-First + PlannerAgent ───────────────────────
    for repo_type in meta_plan.repos:
        spec = meta_plan.spec_for(repo_type) or description
        seed_keywords = meta_plan.keywords_for(repo_type)

        # ── Route-first (no LLM, instant) ────────────────────────────────────
        _section(f"STAGE 1 │ {repo_type.upper()} — Route-First Targeting")
        rf = _route_first_preview(title, spec, repo_type)
        icon = {"high": "✓ HIGH", "medium": "~ MEDIUM", "low": "? LOW", "none": "✗ NONE"}
        print(f"  confidence    : {icon.get(rf['confidence'])}")
        print(f"  reasoning     : {rf['reasoning']}")
        if rf["route"]:
            print(f"  matched route : {rf['route']}")
            print(f"  handler       : {rf['handler']}")
        if rf["files"]:
            print(f"  resolved files: {rf['files']}")
        if rf["keywords"]:
            print(f"  inj. keywords : {rf['keywords']}")

        # ── PlannerAgent (LLM + graph) ────────────────────────────────────────
        _section(f"STAGE 1 │ {repo_type.upper()} — PlannerAgent (LLM + Graph)")
        print("  Calling LLM + graph …", flush=True)
        t1 = time.time()

        nav = get_navigator(repo_type)
        planner = PlannerAgent(llm, nav, api_root=(_API_ROOT if repo_type == "api" else ""))
        plan = planner.plan(
            title=title,
            description=spec,
            seed_keywords=seed_keywords,
            repo_type=repo_type,
        )
        print(f"  Done in {time.time() - t1:.1f}s\n")

        print(f"  change_type  : {plan.change_type}")
        print(f"  keywords used: {plan.keywords_extracted}")
        print(f"  reasoning    : {plan.reasoning}")
        print(f"\n  TARGET FILES ({len(plan.target_files)}):")
        for i, f in enumerate(plan.target_files, 1):
            print(f"    {i:2}. {f}")
        if not plan.target_files:
            print("    (none — no graph matches; pipeline would fall back to LLM file selection)")

    print()
    print("═" * 74)


if __name__ == "__main__":
    run()
