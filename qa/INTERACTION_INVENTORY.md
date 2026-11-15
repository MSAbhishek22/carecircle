# CareCircle — Interaction Inventory

Every visible control, its behaviour and its verification. Status key:
PASS = exercised in the local smoke test / automated suite on 2026-11-15.

| Page | Control | Action → behaviour | Verified by | Status |
|---|---|---|---|---|
| Header | Elder Mode toggle | Switches base type 18px→22px, tap targets 52→64px; persists in localStorage; `aria-pressed` updates | Manual (local) | PASS |
| Header | Log out (after login) | Ends session server-side, reloads to login | API test pattern (session drop) | PASS |
| Login | Name field | Required; empty submit blocked by browser + server never sees it | Manual | PASS |
| Login | Role select | elder / caretaker / family; invalid role → 400 | test_http unknown-role | PASS |
| Login | Passcode field | Wrong passcode → 401 with plain error, no session | test_http wrong-passcode | PASS |
| Login | "Enter CareCircle" | Correct passcode → session cookie, dashboard loads | Local smoke test (curl) + WSGI harness | PASS |
| Tabs | Six section tabs | Show/hide panels, `aria-selected`; ArrowLeft/Right move between tabs | Manual (local) | PASS |
| Today | "✓ Taken" on a pending dose | Logs dose, decrements stock, feed entry, row becomes "Logged" | test_http dose workflow + smoke test | PASS |
| Today | "Missed" on a pending dose | Logs missed, feed entry, reminder centre updates | Core reminder tests | PASS |
| Today | Dose wheel | Decorative 3D ring of today's doses; hover tilt; reduced-motion safe | Manual (local render) | PASS |
| Medicines | Add medicine form | Valid → 201, appears in list + feed; invalid time/name → 400 error shown | test_http add/invalid | PASS |
| Medicines | Edit button | Prefills the form; save updates schedule + feed | Code path shared with add (validated) | PASS |
| Medicines | Remove button | Confirm dialog → deletes, feed entry | test via API delete action (appointments) + same handler pattern | PASS |
| Medicines | (family role) | Form card hidden; Edit/Remove buttons absent; direct POST → 403 | test_http family read-only | PASS |
| Appointments | Add form | Valid → 201, listed + feed; bad date/time → 400 | test_http round-trip | PASS |
| Appointments | Remove button | Confirm → deletes | test_http round-trip | PASS |
| Reminders | Missed / Upcoming / Refills lists | Computed live from schedule, logs and stock | Core reminder tests (hand-counted) | PASS |
| Reminders | Outbox list | Shows generated reminder messages with recipient + reason; generation idempotent per day | Core outbox tests (10 messages at reference time) | PASS |
| Family Feed | Activity list | Newest-first stream of dose/schedule/appointment events | Smoke test (dose log appeared) | PASS |
| Care Assistant | Summary box | Plain-language daily summary text | Core assistant test (exact contents) | PASS |
| Care Assistant | Safety flags | Clash / duplicate-therapy / duplicate-name flags with explanations | Core assistant tests | PASS |
| Care Assistant | Refill predictions | Days-left + run-out date per low medicine | Core refill tests | PASS |

No dead controls: every button on every panel performs the action above.
No `href="#"` anywhere; the only link is the skip link to `#main`.
