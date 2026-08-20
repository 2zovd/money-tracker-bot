# Roadmap

Evolve step by step: don't break what works, and each phase is useful on its own.

## Phase 0 — Bot + Google Sheets ✅ (now)

The Telegram bot writes structured expenses into a sheet with a budget model. Enough for
daily tracking and the first 2–3 months of data collection.

## Phase 1 — Stabilize and analyze (next)

- `/day`, `/week` commands; group and place rollups in chat.
- Export/backup of the Journal.
- More parsing tests (dining/groceries/fuel cases, currencies).
- Tags for recurring expenses (rent, subscriptions) — auto-reminders.

## Phase 1.5 — Agent mode (planned)

Tool use instead of a fixed parser: the bot answers questions about the data
("how much on groceries in September") and takes free-form instructions, with read-only
as a real boundary rather than an instruction. Plan, cost and risks:
[AGENT_MODE.md](AGENT_MODE.md).

## Phase 2 — Own DB + API (when Sheets gets tight)

Google Sheets won't power a mini app well (concurrency, speed, relations). Move to:

- **DB:** Supabase (Postgres) — quick start, auth and REST/Realtime built in.
  Tables: `expenses`, `categories`, `groups`, `assets`, `income`.
- **API:** FastAPI (Python) — reuse `parser.py` and the category logic from the bot. The
  bot and mini app hit one API. Sheets stays as an optional export/mirror.
- One-off script to migrate Journal data.

## Phase 3 — Telegram Mini App on Vue (goal)

A web app inside Telegram (Telegram WebApp SDK):

- **Vue 3 + `<script setup>` + TypeScript**, **Vite**.
- **TailwindCSS**, **Vue Router**, **Pinia**.
- Auth via Telegram `initData` (signature checked on the FastAPI backend).

**Screens (UX):**
- Expense feed with quick filters by group/place/period.
- Quick expense entry (a form with the same follow-ups as the bot).
- Dashboard: plan/actual by group, emergency-fund status, trends.
- Analytics: store vs market, cost per 100 km, share of cash.

**Principle:** the bot stays for instant capture on the go; the mini app is for viewing,
reviewing and editing. Both write to one API.

## Phase 4 — Smarts (later)

- Auto-categorization that learns from edits.
- End-of-month spend forecast, "group over budget" alerts.
- Link assets/savings for a full capital picture.

---

### Migration notes for the mini app
- Move the category logic (`bot/categories.py`) to a shared source read by both bot and API.
- `parser.py` isn't tied to Telegram — reuse it in the API as-is.
- Store `expenses` with the same axes (category/place/attributes) — the model is already right.
