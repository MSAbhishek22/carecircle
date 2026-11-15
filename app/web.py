"""CareCircle web layer — transport-independent request handler.

``handle()`` takes a method, path, query, body and cookies and returns
(status, headers, body_bytes). Both the local stdlib server
(``app/server.py``) and the Vercel WSGI adapter (``api/index.py``) call it,
so behaviour is identical locally and in production.

Security notes:
- The profile passcode is only ever checked against a salted PBKDF2 hash.
- Every /api/* route except /api/login requires a valid session cookie.
- Mutations (medicines, appointments) are restricted server-side to the
  elder and caretaker roles; the family role is read-only by design.
- All user-supplied strings are length-capped and validated server-side;
  the frontend escapes everything it renders.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

from . import core

# CareCircle serves an Indian care circle, so "today" is always the
# Asia/Kolkata day regardless of where the host runs (UTC on Vercel).
# IST has no daylight-saving changes, so the fixed offset fallback is exact.
try:
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - hosts without tzdata
    IST = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_INDEX = os.path.join(BASE_DIR, "app", "static", "index.html")

_JSON = "application/json; charset=utf-8"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# One store per process. On Vercel this lives for the warm instance only —
# an accepted, documented demo caveat (synthetic data, single profile).
STORE = core.seed_store(datetime.now(IST))


def _now() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def _json(status: int, payload: dict) -> tuple[int, list, bytes]:
    body = json.dumps(payload, indent=2).encode("utf-8")
    return status, [("Content-Type", _JSON)], body


def _err(status: int, message: str) -> tuple[int, list, bytes]:
    return _json(status, {"error": message})


def _clean(value, limit: int = 80) -> str:
    return str(value or "").strip()[:limit]


def _parse_body(body: bytes) -> dict:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _med_json(med: core.Medication, store: core.Store, now: datetime) -> dict:
    est = core.refill_estimate(med, now.date())
    today = now.date().isoformat()
    slots = []
    for slot in med.times:
        log = store.get_log(med.id, today, slot)
        slots.append({"time": slot,
                      "status": log.status if log else "pending"})
    return {
        "id": med.id, "name": med.name, "dose": med.dose,
        "times": med.times, "with_food": med.with_food, "stock": med.stock,
        "per_dose": med.per_dose, "category": med.category,
        "notes": med.notes, "today": slots, **est,
    }


def _require_session(cookies: dict) -> dict | None:
    return STORE.session(cookies.get("cc_session"))


def _require_manager(cookies: dict):
    """Return (session, error_response). Family role is read-only."""
    session = _require_session(cookies)
    if session is None:
        return None, _err(401, "Please log in first.")
    if session["role"] not in core.MANAGER_ROLES:
        return None, _err(403, "Family members have read-only access.")
    return session, None


def _feed(kind: str, text: str, now: datetime) -> None:
    STORE.feed.append(core.FeedEvent(
        at=now.isoformat(timespec="seconds"), kind=kind, text=text))


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def _login(data: dict) -> tuple[int, list, bytes]:
    passcode = str(data.get("passcode") or "")
    role = _clean(data.get("role"), 20)
    name = _clean(data.get("name"), 60)
    if role not in core.ROLES:
        return _err(400, "Choose a role: elder, caretaker or family.")
    if not name:
        return _err(400, "Please enter your name.")
    profile = STORE.profile
    if not core.verify_passcode(passcode, profile.passcode_salt,
                                profile.passcode_hash):
        return _err(401, "That passcode does not match this care profile.")
    token = STORE.create_session(name, role)
    headers = [("Content-Type", _JSON),
               ("Set-Cookie",
                f"cc_session={token}; Path=/; HttpOnly; SameSite=Lax")]
    body = json.dumps({"ok": True, "name": name, "role": role,
                       "elder_name": profile.elder_name}).encode("utf-8")
    return 200, headers, body


def _validate_med(data: dict) -> tuple[dict | None, str]:
    name = _clean(data.get("name"), 60)
    dose = _clean(data.get("dose"), 30)
    times = data.get("times") or []
    if not name or not dose:
        return None, "Medicine name and dose are required."
    if not isinstance(times, list) or not times:
        return None, "Add at least one time of day."
    times = sorted({_clean(t, 5) for t in times})
    if any(not _TIME_RE.match(t) for t in times):
        return None, "Times must look like 08:00 (24-hour)."
    try:
        stock = int(data.get("stock", 0))
        per_dose = int(data.get("per_dose", 1))
    except (TypeError, ValueError):
        return None, "Stock and per-dose amounts must be numbers."
    if stock < 0 or per_dose < 1:
        return None, "Stock cannot be negative; per-dose must be at least 1."
    return {
        "name": name, "dose": dose, "times": times,
        "with_food": bool(data.get("with_food")),
        "stock": stock, "per_dose": per_dose,
        "category": _clean(data.get("category"), 40),
        "notes": _clean(data.get("notes"), 120),
    }, ""


def handle(method: str, path: str, query: str, body: bytes,
           cookies: dict) -> tuple[int, list, bytes]:
    now = _now()
    params = parse_qs(query or "")

    if method == "GET" and path in ("/", "/index.html"):
        try:
            with open(STATIC_INDEX, "rb") as fh:
                return 200, [("Content-Type",
                              "text/html; charset=utf-8")], fh.read()
        except OSError:
            return _err(500, "UI file missing.")

    if method == "GET" and path == "/health":
        return _json(200, {"status": "ok", "service": "carecircle",
                           "llm": "none — deterministic rules only"})

    if method == "POST" and path == "/api/login":
        return _login(_parse_body(body))

    if method == "POST" and path == "/api/logout":
        STORE.drop_session(cookies.get("cc_session", ""))
        return _json(200, {"ok": True})

    # Everything below requires a session.
    if path.startswith("/api/"):
        session = _require_session(cookies)
        if session is None:
            return _err(401, "Please log in first.")

        if method == "GET" and path == "/api/state":
            core.generate_outbox(STORE, now)
            reminders = core.compute_reminders(STORE, now)
            meds = [_med_json(m, STORE, now)
                    for m in STORE.medications.values()]
            appts = sorted(
                ({"id": a.id, "doctor": a.doctor, "purpose": a.purpose,
                  "when": a.when, "time": a.time, "location": a.location}
                 for a in STORE.appointments.values()),
                key=lambda a: (a["when"], a["time"]))
            appts = [a for a in appts if a["when"] >= now.date().isoformat()]
            return _json(200, {
                "me": session,
                "elder": {"name": STORE.profile.elder_name,
                          "age": STORE.profile.elder_age},
                "members": STORE.profile.members,
                "medications": meds,
                "appointments": appts,
                "reminders": reminders,
                "adherence7": core.adherence(STORE, 7, now),
                "adherence30": core.adherence(STORE, 30, now),
                "feed": [{"at": e.at, "kind": e.kind, "text": e.text}
                         for e in reversed(STORE.feed[-40:])],
                "outbox": [{"id": m.id, "at": m.at, "to_role": m.to_role,
                            "to_name": m.to_name, "subject": m.subject,
                            "body": m.body, "kind": m.kind}
                           for m in reversed(STORE.outbox[-40:])],
                "assistant": {
                    "safety": core.safety_checks(STORE),
                    "summary": core.daily_summary(STORE, now),
                    "refills": reminders["refills"],
                },
                "server_time": now.isoformat(timespec="seconds"),
            })

        if method == "POST" and path == "/api/medications":
            session, error = _require_manager(cookies)
            if error:
                return error
            values, problem = _validate_med(_parse_body(body))
            if problem:
                return _err(400, problem)
            med = core.Medication(id="med-" + secrets.token_hex(4), **values)
            STORE.medications[med.id] = med
            _feed("med_added",
                  f"{session['name']} added {med.name} ({med.dose}) at "
                  f"{', '.join(med.times)}.", now)
            return _json(201, {"medication": _med_json(med, STORE, now)})

        if method == "POST" and path.startswith("/api/medications/"):
            session, error = _require_manager(cookies)
            if error:
                return error
            med_id = path.rsplit("/", 1)[-1]
            med = STORE.medications.get(med_id)
            if med is None:
                return _err(404, "Medicine not found.")
            data = _parse_body(body)
            if data.get("action") == "delete":
                del STORE.medications[med_id]
                _feed("med_edited",
                      f"{session['name']} removed {med.name} from the "
                      f"schedule.", now)
                return _json(200, {"ok": True})
            values, problem = _validate_med(data)
            if problem:
                return _err(400, problem)
            for key, value in values.items():
                setattr(med, key, value)
            _feed("med_edited",
                  f"{session['name']} updated {med.name} "
                  f"({med.dose}, {', '.join(med.times)}).", now)
            return _json(200, {"medication": _med_json(med, STORE, now)})

        if method == "POST" and path == "/api/dose":
            data = _parse_body(body)
            med = STORE.medications.get(_clean(data.get("med_id"), 40))
            slot = _clean(data.get("time"), 5)
            status = _clean(data.get("status"), 10)
            if med is None or not _TIME_RE.match(slot):
                return _err(400, "Unknown medicine or time.")
            if status not in ("taken", "missed"):
                return _err(400, "Status must be taken or missed.")
            if slot not in med.times:
                return _err(400, "That time is not on this medicine's "
                                   "schedule.")
            today = now.date().isoformat()
            STORE.log_dose(med.id, today, slot, status,
                           by=session["name"], now=now)
            if status == "taken" and med.stock >= med.per_dose:
                med.stock -= med.per_dose
            _feed("dose_taken" if status == "taken" else "dose_missed",
                  f"{STORE.profile.elder_name} {'took' if status == 'taken' else 'missed'} "
                  f"{med.name} ({med.dose}) — {slot} dose, logged by "
                  f"{session['name']}.", now)
            core.generate_outbox(STORE, now)
            return _json(200, {"ok": True})

        if method == "POST" and path == "/api/appointments":
            session, error = _require_manager(cookies)
            if error:
                return error
            data = _parse_body(body)
            doctor = _clean(data.get("doctor"), 60)
            purpose = _clean(data.get("purpose"), 80)
            when = _clean(data.get("when"), 10)
            at = _clean(data.get("time"), 5)
            if not doctor or not purpose:
                return _err(400, "Doctor and purpose are required.")
            if not _DATE_RE.match(when) or not _TIME_RE.match(at):
                return _err(400, "Date must be YYYY-MM-DD and time HH:MM.")
            appt = core.Appointment(
                id="appt-" + secrets.token_hex(4), doctor=doctor,
                purpose=purpose, when=when, time=at,
                location=_clean(data.get("location"), 80))
            STORE.appointments[appt.id] = appt
            _feed("appt_added",
                  f"{session['name']} added an appointment: {doctor} — "
                  f"{purpose} on {when} at {at}.", now)
            return _json(201, {"id": appt.id})

        if method == "POST" and path.startswith("/api/appointments/"):
            session, error = _require_manager(cookies)
            if error:
                return error
            appt_id = path.rsplit("/", 1)[-1]
            if appt_id not in STORE.appointments:
                return _err(404, "Appointment not found.")
            data = _parse_body(body)
            if data.get("action") == "delete":
                gone = STORE.appointments.pop(appt_id)
                _feed("appt_added",
                      f"{session['name']} removed the appointment with "
                      f"{gone.doctor} on {gone.when}.", now)
                return _json(200, {"ok": True})
            return _err(400, "Only delete is supported here.")

        return _err(404, "Not found.")

    return _err(404, "Not found.")
