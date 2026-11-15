# CareCircle — Design Constitution

**Personality:** a warm kitchen table at 8 in the morning — unhurried,
respectful, plain-spoken. The product speaks to a 74-year-old first and to
her family second; nothing on screen should ever make the elder feel like
a patient being monitored. She is the host; everyone else is a guest in
her circle.

**Visual metaphor:** the *circle* — a family gathered around one person.
The day's doses are arranged as a ring (the CSS-3D dose wheel on the Today
tab): morning at the top, night at the bottom, each dose a bead that turns
green when taken. The list beneath the wheel carries the same data in
plain form — the wheel is the glance, the list is the truth.

**Palette (semantic):**
- `--cream #FFF8EE` — page ground, morning light.
- `--paper #FFFDF8` — cards, paper on the table.
- `--terra #C4502B` — primary warmth, brand, calls to action.
- `--leaf #2E5E4E` — health, "taken", confirmations.
- `--marigold #E9A13B` — pending, gentle attention.
- `--rose #B3372F` — missed, needs care (never alarm-red; a deep rose).
- `--ink #2B2118` — text, warm black. Contrast of ink on cream ≈ 13:1.

**Typography:** Georgia serif for headings and times (familiar from print,
kind to older eyes), system sans for body. Base 18px; Elder Mode 22px.

**Layout:** single column of generous cards, max-width 1060px; tabs as
large pills; every action is a labelled button, never an icon alone.

**Motion:** one restrained transition (the wheel's tilt). Everything else
is instant. `prefers-reduced-motion` disables the wheel transition.

**3D experience:** the CSS-3D dose wheel (rotateX-tilted ring, `preserve-3d`
spokes). Purpose: give the day a spatial shape so family members can read
adherence at a glance. It is `aria-hidden` decoration layered over the
accessible list; no information exists only in the wheel. Fallback: with
reduced motion or no 3D support, the list below is complete on its own.

**Accessibility:** semantic landmarks, skip link, visible 4px focus rings,
arrow-key tab navigation, ≥52px tap targets (64px in Elder Mode), form
labels on every field, `role="alert"` errors, no colour-only status
(every status also has text).

**Distinctness check (vs. recent fleet projects):** ProofBench is a cool,
mono-spaced evidence bench; Spec Ghost is a dark haunted-house scan;
YojanaSetu is an officer-side governance console. CareCircle is the fleet's
first warm, serif-led, elder-first product — different palette, type,
layout (single-column cards vs. benches/consoles) and motion language.

**Research note (honest):** this was a same-day event build (challenge
revealed 09:00 IST, submission 17:00 IST). The formal five-reference
research pass was time-boxed out; the design instead follows the brief's
own accessibility demands and WCAG 2.2 AA principles (contrast, target
size, focus visibility, reduced motion). Gate A is therefore recorded as
condensed, not completed, in the release manifest.
