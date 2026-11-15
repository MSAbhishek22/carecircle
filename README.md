# CareCircle — Elderly Care & Medication Management

**One shared care profile for an elderly person, their caretakers and their
family — medicines, appointments, adherence and reminders, with the elder at
the centre of every decision.**

Built for the **Catalyst Solo AI Hackathon (PromptWars × Catalyst)**,
challenge: *Elderly Care & Medication Management Platform*.

> **Demo profile:** elder **Kamla Devi**, passcode **`kamla123`** — shown on
> the login page so judges can enter immediately. Try all three roles; the
> family role is read-only, exactly as designed.

Pure Python 3 standard library — no dependencies, nothing to install.

---

## How it answers the brief

| Brief requirement | CareCircle implementation |
|---|---|
| Shared ecosystem: elder, caretakers, family on one profile | One care profile per elder; everyone joins with the same profile passcode and picks their role |
| Secure, passcode-based access | Passcode stored only as a **salted PBKDF2-HMAC-SHA256 hash** (120k rounds), constant-time verification, HttpOnly session cookies; plaintext is never stored or logged |
| View / add / edit / manage medication schedules | Full medicine CRUD: name, dose, multiple times of day, with-food flag, stock, therapy category — server-side validated |
| Track adherence | Dose logging (taken / missed) per scheduled slot; adherence % over 7 and 30 days, counting only doses already due |
| Doctor appointments | Add / list / remove upcoming appointments; next appointment on the dashboard |
| Email reminders for missed doses, upcoming doses, refills | A **reminder centre** computes missed doses (30-min grace), doses due within 90 minutes and refill alerts, and drafts the exact reminder messages into an **outbox** addressed to the elder **and** caretakers |
| Real-time updates to family | A **family feed** streams every dose taken/missed, schedule change and appointment as it happens |
| Go beyond a basic reminder app — AI features | **Care Assistant** (deterministic, rule-based — no LLM, and it says so): schedule-safety checks, refill prediction, and a plain-language daily summary for family |
| Intuitive and accessible for elderly users | Large type (18px base), high contrast, ≥52px tap targets, **Elder Mode** (22px+, 64px targets), keyboard-navigable tabs, semantic HTML, aria labels, visible focus, `prefers-reduced-motion` respected |
| Elder at the centre of their own decisions | The elder has full manage rights over their own profile; the family role is read-only; the assistant flags concerns but never gives medical advice |

### Care Assistant (rule-based, transparent)

1. **Schedule-safety checks** — flags two medicines scheduled within
   30 minutes of each other, the same medicine entered twice, and two
   medicines prescribed for the same condition (possible duplicate therapy).
   The seeded profile demonstrates all of this: Amlodipine 08:00 and
   Telmisartan 08:15, both for blood pressure.
2. **Refill prediction** — from stock, dose size and schedule:
   *"Metformin — about 3 day(s) left, runs out around 2026-11-18."*
3. **Daily summary for family** — *"Kamla has taken 0 of 4 doses so far
   today. Next dose is at 21:00 — Metformin 500 mg (1 tablet). Over the
   last 7 days, Kamla took 85% of scheduled doses."*

### Honest notes

- **Reminders:** messages are *generated and logged in the in-app outbox*.
  No real email is sent — no SMTP service is configured. The outbox shows
  exactly what would be sent, to whom, and why.
- **Data:** synthetic demo data only, held in memory. On serverless
  hosting the profile persists for the life of a warm instance and can
  differ across instances; a production version would move the store to
  a database. Nothing here is real medical data.
- **Time:** the care day is always Asia/Kolkata, wherever the host runs.

## Run it

```bash
python3 run.py serve 8790     # http://127.0.0.1:8790
python3 run.py test           # full test suite
```

Open the page, enter any name, pick a role, passcode **`kamla123`**.

## Tests

**33 tests, all passing** (`python3 run.py test`), covering:

- Passcode hashing: correct/wrong passcode, unique salts, no plaintext.
- Access control through the real HTTP handler: unauthenticated → 401,
  wrong passcode → 401, **family role mutations → 403**, family reads OK.
- Adherence maths against hand-counted seeded history (29 taken / 5 missed
  / 85.3% at the reference time), future doses excluded.
- Reminder computation: missed/upcoming windows, refill threshold,
  outbox recipients (elder + caretaker, not family), idempotent generation.
- Care Assistant: duplicate-therapy, duplicate-name and time-clash flags,
  clean schedules produce no flags, plain-language summary contents.
- Workflows: add/edit/delete medicine, dose logging decrements stock and
  writes the family feed, appointment round-trip, validation errors.

## Structure

```
app/core.py     — data model, passcode security, adherence, reminders, assistant
app/web.py      — transport-independent HTTP handler (all routes + validation)
app/server.py   — local stdlib server (same handler)
api/index.py    — Vercel WSGI adapter (same handler — route parity by construction)
app/static/     — single-page UI (elderly-first, Elder Mode, CSS-3D dose wheel)
tests/          — unittest suite (core + HTTP layer)
run.py          — serve / test entry point
vercel.json     — serverless config (rewrite all → api/index.py)
```

## Deployment

Vercel (free tier): import the repo, no build command, no environment
variables. `api/index.py` serves every route; see
`deployment/DEPLOYMENT_RUNBOOK.md`.

## Licence

MIT — see `LICENSE`.
