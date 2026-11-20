# CareCircle — one shared care page for an elderly parent

**Live demo: https://carecircle-murex.vercel.app** — open it and sign in with passcode `kamla123` to try the demo profile.

Picture a father who takes four medicines a day, in a house in one city, while his son works in another. A dose gets missed on Tuesday. The son finds out on Friday, on a phone call, from memory. CareCircle exists so the family stops guessing: one shared page for the elder, the caretaker and the family, where everyone sees the same truth about medicines, doses and appointments.

## The problem

Elderly parents often take several medicines at set times every day. The people who love them are split across houses and cities, and the only shared record is phone calls and memory. Missed doses stay invisible until they turn into a health problem.

## Who it is for, and who would pay

For elderly people living at home, the caretakers who help them daily, and their adult children who live away. The family is the paying side: one small monthly fee per family, so that everyone — son, daughter, caretaker — sees the same medicine record instead of asking each other.

## What works today

Try it with the demo profile: elder **Kamla Devi**, passcode **`kamla123`** (shown on the login page). Pick any of the three roles; the family role is read-only, exactly as designed.

- **One care profile per elder.** Everyone joins with the same profile passcode and picks a role: elder, caretaker or family. The elder keeps full control of their own profile.
- **Medicine schedules, managed properly.** Add, edit and remove medicines with dose, multiple times of day, with-food flag, stock and therapy category — all validated on the server.
- **Adherence you can trust.** Every scheduled dose is logged taken or missed, and the app shows adherence over 7 and 30 days, counting only doses that were already due. In the demo profile's seeded history: 29 doses taken, 5 missed — 85.3%.
- **Appointments.** Add, list and remove doctor appointments; the next one sits on the dashboard.
- **Reminder centre.** It works out missed doses (after a 30-minute grace), doses due within 90 minutes, and refills running low, and drafts the exact reminder messages into an outbox addressed to the elder and the caretakers.
- **Family feed.** Every dose taken or missed, schedule change and appointment appears in one stream, as it happens.
- **Care Assistant.** A plain rule-based helper — no AI model, and it says so. It flags two medicines scheduled within 30 minutes of each other, the same medicine entered twice, and two medicines for the same condition (the demo profile shows one: Amlodipine at 08:00 and Telmisartan at 08:15, both for blood pressure). It predicts refills from stock and schedule ("Metformin — about 3 days left") and writes a short daily summary in plain words for the family. It flags concerns; it never gives medical advice.
- **Built for elderly eyes.** 18px base type, high contrast, tap targets of at least 52px, an Elder Mode with 22px+ type and 64px targets, keyboard-navigable tabs, aria labels and reduced-motion support.

## Honest notes

- **Reminders are drafted, not sent.** Messages are generated into the in-app outbox, which shows exactly what would be sent, to whom, and why. No email service is connected yet.
- **Demo data is held in memory.** The profile lives for the life of a running instance and resets after that. A paid version would store each family's profiles and history in a database, so the record is permanent and the family can look back over months.
- **Security is real, though.** The passcode is stored only as a salted PBKDF2-HMAC-SHA256 hash (120,000 rounds), checked in constant time, with HttpOnly session cookies. The plain passcode is never stored or logged.
- All data is synthetic demo data. Nothing here is real medical data. The care day is always Asia/Kolkata, wherever the host runs.

## The numbers

- 33 automated tests, all passing — passcode hashing and access control through the real HTTP layer (signed-out requests get 401, family-role changes get 403), adherence maths checked against hand-counted history, reminder windows, refill thresholds, assistant flags, and full add/edit/delete and dose-logging flows
- 3 roles, 1 shared profile, 0 dependencies — pure Python 3 standard library

## Run it

```bash
python3 run.py serve 8790     # http://127.0.0.1:8790
python3 run.py test           # full test suite
```

Open the page, enter any name, pick a role, passcode **`kamla123`**.

## How it is built

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

Deployed on Vercel (free tier): import the repo, no build command, no environment variables. See `deployment/DEPLOYMENT_RUNBOOK.md`.

## Where this can go

- Saved profiles in a database, so a family's medicine history is permanent and grows month by month.
- Real reminders — email or WhatsApp to the elder and caretakers when a dose is missed, not just drafts in an outbox.
- A clinic version: one desk watching over many elders in a neighbourhood, with the same shared page per family.

## Status and entries

Built solo by M S Abhishek for the Catalyst Solo AI Hackathon (PromptWars × Catalyst), challenge: Elderly Care & Medication Management Platform, and submitted there. Live and verified at the link above.

## Licence

MIT — see `LICENSE`.
