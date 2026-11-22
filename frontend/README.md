# LeadFlow dashboard

Next.js 16 (App Router) + React 19 + Tailwind 4. Talks to the FastAPI backend in `../backend`.

## Run

```bash
cd frontend
cp .env.example .env.local     # BACKEND_URL, defaults to http://localhost:8000
npm install
npm run dev                    # http://localhost:3000   (the backend must be running)
```

Needs Node 22+ (built and tested on Node 26).

## Checks

```bash
npm run typecheck && npm run lint
npm test                       # unit tests for the security logic (fast)
npm run e2e                    # browser tests against a throwaway backend + a real production build
```

`npm run e2e` starts its own backend on a fresh SQLite file (migrated with Alembic) and its own
production build, so it never touches your dev data. It uses no real API keys and runs no AI calls.

## How it is put together

```
browser  ->  Next.js server  ->  FastAPI
```

- **The browser never holds the API token.** Sign-in goes through `/api/auth/*`, which stores the
  backend's JWT in an `httpOnly`, `SameSite=Lax` cookie. Page scripts can't read it, so an XSS bug
  can't steal it.
- **`/api/proxy/*` forwards API calls and attaches the token.** It is not an open relay:
  `lib/proxyRules.ts` allow-lists the exact method + path combinations the dashboard uses, and
  state-changing calls must carry an `Origin` header from our own host (CSRF defence in depth).
- **`proxy.ts` only does an optimistic check** (no cookie: go to `/login`). Real authorization
  happens in the backend on every call; a bad token gets a 401 and the cookie is cleared.
- Lead websites come from CSV uploads, so they are untrusted: only `http(s)` links are rendered
  as links (`lib/url.ts`). Everything else is shown as plain text.
- Sending is two steps in the UI: a dry-run preview of exactly which emails would go, then a
  separate confirm button. The backend also defaults to dry-run.

## Design: plain on purpose

The look follows the restraint of vercel.com / ai-sdk.dev: a near-white page, white cards with 1px
borders, no shadows or gradients, one near-black primary button, one typeface family (Geist), and
no decoration. Headings are medium weight with tight tracking; body is 15px.

Layout follows ai-sdk.dev: a borderless header (logo, a slash, the name, who you are on the right),
a docs-style left sidebar listing your campaigns on wide screens (the same two links move into the
header on phones), a large light page title, one divided strip for the six pipeline steps, pill tabs,
and a centred sign-in page. Radii are about 8px for controls and 12px for cards.

Minimal by default: on a campaign page only the one step worth doing next gets the dark button
(`lib/nextStep.ts`, tested for every state); the rest are quiet grey. Notices are plain text unless they
need attention (warnings and errors keep a box), badges have no outline, and tables have no filled header.

Circuit Teal (kit v1, locked) shows up quietly. The five values live once in `app/globals.css`,
copied exactly from the kit, and are available to Tailwind as `bg-brand-ink`, `text-brand-ink/65`, etc.

| Token | Where it is used |
|---|---|
| Ink | Text, and the primary button (Surface text on Ink: 15.8:1) |
| Surface / Base | Hover states, links (Deep Teal text, 14.5:1 on white) |
| Accent (lime) | **Only the logo mark** |
| Primary (Signal Teal) | Focus rings, link underlines, faint badge tints. Never small text: Surface on Primary is only 4.26:1, fine for large bold text only |

The kit lists safe/avoid pairings but no contrast numbers; `tests/brand.test.ts` measures them,
locks the token values, and fails if lime is used as text or a UI colour, if opaque Signal Teal sits
behind small text, or if muted text drops below AA.

Not in the kit, so added by us:
- white cards, and red/amber for errors, warnings and the "send for real" button (a destructive
  action should not look like a normal one);
- `--brand-page`: Surface lightened 55% toward white (`#F8FDFB`), derived from a kit token and locked by a test;
- **Geist instead of the kit's IBM Plex.** A deliberate departure chosen by the owner after pointing
  at the Vercel AI SDK site as the reference. To go back: `npm i @fontsource/ibm-plex-sans
  @fontsource/ibm-plex-mono`, import their CSS in `app/layout.tsx`, and set `--font-sans` / `--font-mono`
  in `app/globals.css` (and update the font test).

## Pages

| Route | What it does |
|---|---|
| `/` | Public landing page (hero, a tabbed walkthrough of the five steps with made-up example data, and the built-in safeguards). Signed-in visitors are sent straight to `/campaigns` |
| `/login` | Sign in / create account (`/login?mode=register` opens on sign-up) |
| `/campaigns` | Your campaigns, create a new one |
| `/campaigns/[id]` | The pipeline: leads, find emails, score, write, review & approve, send |
| `/settings` | Sender details, mailboxes (SMTP), do-not-contact list |

## Not built yet

Edit or delete a campaign, pagination beyond the top 200 leads, a per-lead detail view, bulk
actions (approving drafts is deliberately one at a time), dark mode, reading replies or bounces.
