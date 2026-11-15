"""CareCircle core — data model, security, adherence, reminders, assistant.

Pure standard library. All state lives in a ``Store`` instance (in-memory;
seeded with synthetic demo data). Time is always passed in explicitly
(``now`` parameters) so every computation is deterministic and testable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

# ---------------------------------------------------------------------------
# Passcode security — salted PBKDF2-HMAC-SHA256, never plaintext.
# ---------------------------------------------------------------------------

_PBKDF2_ROUNDS = 120_000


def hash_passcode(passcode: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) for a passcode."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", passcode.encode("utf-8"), salt, _PBKDF2_ROUNDS
    )
    return salt.hex(), digest.hex()


def verify_passcode(passcode: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time check of a candidate passcode against a stored hash."""
    _, candidate = hash_passcode(passcode, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, hash_hex)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Medication:
    id: str
    name: str
    dose: str  # human label, e.g. "1 tablet"
    times: list[str]  # "HH:MM" 24h, sorted
    with_food: bool = False
    stock: int = 0  # units on hand
    per_dose: int = 1  # units consumed per dose
    category: str = ""  # therapy class, e.g. "Blood pressure"
    notes: str = ""

    def doses_per_day(self) -> int:
        return len(self.times) * self.per_dose


@dataclass
class Appointment:
    id: str
    doctor: str
    purpose: str
    when: str  # ISO date "YYYY-MM-DD"
    time: str  # "HH:MM"
    location: str = ""


@dataclass
class DoseLog:
    med_id: str
    day: str  # "YYYY-MM-DD"
    time: str  # "HH:MM" scheduled time
    status: str  # "taken" | "missed"
    logged_at: str  # ISO timestamp of the log action
    logged_by: str = ""


@dataclass
class FeedEvent:
    at: str  # ISO timestamp
    kind: str  # dose_taken | dose_missed | med_added | med_edited | appt_added | refill
    text: str


@dataclass
class OutboxMessage:
    id: str
    at: str  # ISO timestamp generated
    to_role: str  # "elder" | "caretaker" | "family"
    to_name: str
    subject: str
    body: str
    kind: str  # missed_dose | upcoming_dose | refill


@dataclass
class Profile:
    elder_name: str
    elder_age: int
    passcode_salt: str
    passcode_hash: str
    members: list[dict] = field(default_factory=list)  # {name, role}


ROLES = ("elder", "caretaker", "family")
MANAGER_ROLES = ("elder", "caretaker")  # family is read-only by design


class Store:
    """One shared care profile: medications, appointments, logs, feed, outbox."""

    def __init__(self, profile: Profile):
        self.profile = profile
        self.medications: dict[str, Medication] = {}
        self.appointments: dict[str, Appointment] = {}
        self.dose_logs: dict[tuple[str, str, str], DoseLog] = {}
        self.feed: list[FeedEvent] = []
        self.outbox: list[OutboxMessage] = []
        self._outbox_keys: set[str] = set()
        self.sessions: dict[str, dict] = {}  # token -> {name, role}

    # -- sessions -----------------------------------------------------------
    def create_session(self, name: str, role: str) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"name": name, "role": role}
        return token

    def session(self, token: str | None) -> dict | None:
        if not token:
            return None
        return self.sessions.get(token)

    def drop_session(self, token: str) -> None:
        self.sessions.pop(token, None)

    # -- dose logs ----------------------------------------------------------
    def log_dose(self, med_id: str, day: str, time_: str, status: str,
                 by: str, now: datetime) -> DoseLog:
        entry = DoseLog(
            med_id=med_id, day=day, time=time_, status=status,
            logged_at=now.isoformat(timespec="seconds"), logged_by=by,
        )
        self.dose_logs[(med_id, day, time_)] = entry
        return entry

    def get_log(self, med_id: str, day: str, time_: str) -> DoseLog | None:
        return self.dose_logs.get((med_id, day, time_))


# ---------------------------------------------------------------------------
# Schedule maths
# ---------------------------------------------------------------------------


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def scheduled_instances(med: Medication, day: date) -> list[datetime]:
    return [datetime.combine(day, _parse_hhmm(t)) for t in med.times]


def adherence(store: Store, days: int, now: datetime) -> dict:
    """Adherence over the last ``days`` days including today.

    Only instances already due (scheduled time <= now) are counted, so the
    percentage is never dragged down by doses that are still in the future.
    An instance counts as taken only with an explicit "taken" log; a due
    instance with no log or a "missed" log counts as missed.
    """
    taken = missed = 0
    today = now.date()
    for offset in range(days):
        day = today - timedelta(days=offset)
        for med in store.medications.values():
            for slot in med.times:
                when = datetime.combine(day, _parse_hhmm(slot))
                if when > now:
                    continue
                log = store.get_log(med.id, day.isoformat(), slot)
                if log and log.status == "taken":
                    taken += 1
                else:
                    missed += 1
    total = taken + missed
    pct = round(100.0 * taken / total, 1) if total else 100.0
    return {"taken": taken, "missed": missed, "total": total, "pct": pct,
            "days": days}


def refill_estimate(med: Medication, today: date) -> dict:
    """Days of stock left and the calendar date it runs out."""
    per_day = med.doses_per_day()
    if per_day <= 0:
        return {"days_left": None, "runs_out": None, "low": False}
    days_left = med.stock // per_day
    return {
        "days_left": days_left,
        "runs_out": (today + timedelta(days=days_left)).isoformat(),
        "low": days_left <= 5,
    }


# ---------------------------------------------------------------------------
# Reminder centre — computes what is due and drafts the reminder "emails".
# Messages are generated and logged in the in-app outbox; no real SMTP is
# configured (stated honestly in the UI and README).
# ---------------------------------------------------------------------------

MISSED_GRACE_MINUTES = 30  # a dose counts as missed 30 min after its slot
UPCOMING_WINDOW_MINUTES = 90  # "upcoming dose" reminder horizon


def compute_reminders(store: Store, now: datetime) -> dict:
    """Upcoming doses, missed doses and refill alerts for *right now*."""
    today = now.date()
    upcoming, missed, refills = [], [], []
    for med in store.medications.values():
        for slot in med.times:
            when = datetime.combine(today, _parse_hhmm(slot))
            log = store.get_log(med.id, today.isoformat(), slot)
            if log and log.status == "taken":
                continue
            delta_min = (when - now).total_seconds() / 60.0
            if 0 <= delta_min <= UPCOMING_WINDOW_MINUTES:
                upcoming.append({"med_id": med.id, "name": med.name,
                                 "dose": med.dose, "time": slot,
                                 "in_minutes": int(delta_min),
                                 "with_food": med.with_food})
            elif delta_min < -MISSED_GRACE_MINUTES:
                # Past due beyond the grace window and not logged taken.
                missed.append({"med_id": med.id, "name": med.name,
                                   "dose": med.dose, "time": slot,
                                   "with_food": med.with_food,
                                   "logged_missed": bool(log)})
        est = refill_estimate(med, today)
        if est["low"]:
            refills.append({"med_id": med.id, "name": med.name,
                            "stock": med.stock, **est})
    upcoming.sort(key=lambda r: r["time"])
    missed.sort(key=lambda r: r["time"])
    return {"upcoming": upcoming, "missed": missed, "refills": refills}


def generate_outbox(store: Store, now: datetime) -> list[OutboxMessage]:
    """Draft reminder emails into the outbox (idempotent per day/kind/med).

    Brief requirement: reminders go to the elderly user AND their designated
    caretakers; family members receive the adherence picture via the feed and
    the daily summary instead of per-dose mail.
    """
    reminders = compute_reminders(store, now)
    elder = store.profile.elder_name
    caretakers = [m["name"] for m in store.profile.members
                  if m["role"] == "caretaker"]
    recipients = [("elder", elder)] + [("caretaker", n) for n in caretakers]
    today = now.date().isoformat()
    new_messages: list[OutboxMessage] = []

    def _draft(kind: str, med_id: str, role: str, name: str,
               subject: str, body: str) -> None:
        key = f"{today}|{kind}|{med_id}|{role}|{name}"
        if key in store._outbox_keys:
            return
        store._outbox_keys.add(key)
        msg = OutboxMessage(
            id=f"msg-{len(store.outbox) + 1:04d}",
            at=now.isoformat(timespec="seconds"),
            to_role=role, to_name=name, subject=subject, body=body, kind=kind,
        )
        store.outbox.append(msg)
        new_messages.append(msg)

    for item in reminders["missed"]:
        for role, name in recipients:
            _draft(
                "missed_dose", item["med_id"], role, name,
                f"Missed dose: {item['name']} at {item['time']}",
                f"Hello {name}, {elder} has not taken {item['name']} "
                f"({item['dose']}) scheduled at {item['time']} today. "
                f"Please check in with {elder.split()[0]} when you can. "
                f"— CareCircle",
            )
    for item in reminders["upcoming"]:
        _draft(
            "upcoming_dose", item["med_id"], "elder", elder,
            f"Coming up: {item['name']} at {item['time']}",
            f"Hello {elder}, your {item['name']} ({item['dose']}) is due "
            f"at {item['time']}"
            + (" — take it with food." if item["with_food"] else ".")
            + " — CareCircle",
        )
    for item in reminders["refills"]:
        for role, name in recipients:
            _draft(
                "refill", item["med_id"], role, name,
                f"Refill soon: {item['name']}",
                f"Hello {name}, {item['name']} is running low: "
                f"{item['stock']} left, about {item['days_left']} day(s) "
                f"at the current schedule (runs out around "
                f"{item['runs_out']}). Please arrange a refill. — CareCircle",
            )
    return new_messages


# ---------------------------------------------------------------------------
# Care Assistant — deterministic, rule-based. No LLM, and never claims one.
# ---------------------------------------------------------------------------

CLASH_WINDOW_MINUTES = 30


def safety_checks(store: Store) -> list[dict]:
    """(a) Dose-time clashes within 30 minutes; (b) duplicate therapy."""
    flags: list[dict] = []
    meds = list(store.medications.values())
    # Duplicate therapy: same category prescribed under two names, or the
    # exact same medicine entered twice.
    for i, a in enumerate(meds):
        for b in meds[i + 1:]:
            if a.name.strip().lower() == b.name.strip().lower():
                flags.append({
                    "kind": "duplicate_name",
                    "severity": "high",
                    "text": f"“{a.name}” appears twice in the schedule — "
                            f"the same medicine may be double-dosed.",
                    "meds": [a.id, b.id],
                })
            elif a.category and a.category == b.category:
                flags.append({
                    "kind": "duplicate_therapy",
                    "severity": "medium",
                    "text": f"“{a.name}” and “{b.name}” are both for "
                            f"{a.category.lower()} — worth confirming with "
                            f"the doctor that both are intended.",
                    "meds": [a.id, b.id],
                })
    # Dose-time clashes across different medicines.
    slots: list[tuple[int, str, str]] = []  # (minutes, time, med_id)
    for med in meds:
        for slot in med.times:
            hh, mm = slot.split(":")
            slots.append((int(hh) * 60 + int(mm), slot, med.id))
    slots.sort()
    names = {m.id: m.name for m in meds}
    for i, (mins_a, time_a, med_a) in enumerate(slots):
        for mins_b, time_b, med_b in slots[i + 1:]:
            if med_a == med_b:
                continue
            if mins_b - mins_a <= CLASH_WINDOW_MINUTES:
                flags.append({
                    "kind": "time_clash",
                    "severity": "medium",
                    "text": f"“{names[med_a]}” ({time_a}) and "
                            f"“{names[med_b]}” ({time_b}) are scheduled "
                            f"{mins_b - mins_a} minutes apart — taking them "
                            f"together may be hard on the stomach; consider "
                            f"spacing them out with the doctor's advice.",
                    "meds": [med_a, med_b],
                })
            else:
                break
    return flags


def daily_summary(store: Store, now: datetime) -> str:
    """(c) One plain-language paragraph for family members."""
    elder_first = store.profile.elder_name.split()[0]
    today = now.date()
    due = taken = 0
    next_dose = None
    for med in store.medications.values():
        for slot in med.times:
            when = datetime.combine(today, _parse_hhmm(slot))
            log = store.get_log(med.id, today.isoformat(), slot)
            if when <= now:
                due += 1
                if log and log.status == "taken":
                    taken += 1
            elif next_dose is None or when < next_dose[0]:
                next_dose = (when, med, slot)
    if due:
        first = (f"{elder_first} has taken {taken} of {due} doses so far "
                 f"today.")
    else:
        first = f"No doses were due yet today for {elder_first}."
    if next_dose:
        when, med, slot = next_dose
        second = (f" Next dose is at {slot} — {med.name} ({med.dose}).")
    else:
        second = " No more doses are scheduled today."
    week = adherence(store, 7, now)
    third = (f" Over the last 7 days, {elder_first} "
             f"took {week['pct']:.0f}% of scheduled doses.")
    return first + second + third


# ---------------------------------------------------------------------------
# Demo seed — synthetic data only. History is generated deterministically so
# the demo (and the tests) see the same picture on every fresh start.
# ---------------------------------------------------------------------------

DEMO_PASSCODE = "kamla123"


def seed_store(now: datetime) -> Store:
    salt, digest = hash_passcode(DEMO_PASSCODE)
    profile = Profile(
        elder_name="Kamla Devi",
        elder_age=74,
        passcode_salt=salt,
        passcode_hash=digest,
        members=[
            {"name": "Kamla Devi", "role": "elder"},
            {"name": "Ramesh Kumar", "role": "caretaker"},
            {"name": "Priya Sharma", "role": "family"},
        ],
    )
    store = Store(profile)
    meds = [
        Medication("med-amlodipine", "Amlodipine 5 mg", "1 tablet", ["08:00"],
                   stock=24, category="Blood pressure"),
        Medication("med-telmisartan", "Telmisartan 40 mg", "1 tablet",
                   ["08:15"], stock=18, category="Blood pressure"),
        Medication("med-metformin", "Metformin 500 mg", "1 tablet",
                   ["09:00", "21:00"], with_food=True, stock=6,
                   category="Diabetes"),
        Medication("med-vitd", "Vitamin D3", "1 capsule", ["09:30"],
                   stock=30, category="Supplement"),
    ]
    for med in meds:
        store.medications[med.id] = med
    today = now.date()
    store.appointments["appt-1"] = Appointment(
        "appt-1", "Dr. Meera Joshi", "Blood pressure review",
        (today + timedelta(days=2)).isoformat(), "11:30",
        "City Clinic, MG Road")
    store.appointments["appt-2"] = Appointment(
        "appt-2", "Dr. Arvind Rao", "Diabetes check-up and blood test",
        (today + timedelta(days=6)).isoformat(), "10:00",
        "Sunrise Diagnostics")
    # Seven days of history (not including today): a realistic pattern with
    # occasional misses — deterministic on (day offset, med index, slot).
    for offset in range(1, 8):
        day = today - timedelta(days=offset)
        for mi, med in enumerate(meds):
            for si, slot in enumerate(med.times):
                missed = (offset * 7 + mi * 3 + si * 5) % 11 == 0
                store.log_dose(med.id, day.isoformat(), slot,
                               "missed" if missed else "taken",
                               by="seed", now=now)
    store.feed.append(FeedEvent(
        at=now.isoformat(timespec="seconds"), kind="med_added",
        text="Care profile created for Kamla Devi with 4 medicines."))
    return store
