# CareCircle — Deployment Runbook

**Provider:** Vercel (free/Hobby tier). **Stack:** Python 3 stdlib only —
no dependencies, no build step, no environment variables.

## Deploy

1. Create the public GitHub repo `MSAbhishek22/carecircle` (single branch
   `main`) and push this directory's contents (see the paths manifest
   prepared with the handover; exclude `*.muse-github-snapshot-sync.json`).
2. In Vercel: New Project → import `MSAbhishek22/carecircle`.
   - Framework preset: Other.
   - Build command: none. Output directory: none.
   - `vercel.json` already routes every path to `api/index.py`
     (WSGI entrypoint, maxDuration 60).
3. Deploy. Note the production URL and the commit SHA deployed.

## Health checks (run signed-out, as a stranger)

- `GET /health` → `{"status": "ok", "service": "carecircle", ...}`
- `GET /` → login page loads, demo passcode note visible.
- Log in as caretaker with passcode `kamla123` → Today tab renders,
  adherence percentages present.
- Log the 08:00 Amlodipine dose as Taken → row shows "Logged", family
  feed gains the entry, stock drops by 1.
- Reminders tab → missed doses + Metformin refill alert + outbox entries.
- Care Assistant tab → summary text + safety flags visible.

## Rollback

Vercel → Deployments → promote the previous deployment. The app is
stateless per instance, so rollback is instant and lossless for the demo.

## Ownership / notes

- Repo must stay **under 10 MB** and **single-branch** (event rule) —
  the codebase is ~150 KB of text; keep binaries out.
- In-memory store: data resets when a serverless instance cold-starts.
  Documented in the README; acceptable for the judged demo.
