# web

Public site for `fatihiazmi.dev`: Astro, static output, Tailwind CSS 4. Spec: [`docs/spec.md`](../docs/spec.md) sections 2–5.
Hosting: Cloudflare Pages, root directory `web`. Setup: [`docs/guide/t8-cloudflare-pages.md`](../docs/guide/t8-cloudflare-pages.md).

## Run

```bash
cd web
pnpm install
pnpm dev        # http://localhost:4321
pnpm build      # astro check, then build into dist/
pnpm preview
```

Node 24 (`.node-version`) and pnpm 11 (`packageManager`).

## Project data

`src/lib/projects.ts` fetches `GET ${API_URL}/api/projects` once per build.

| Case | Result |
|---|---|
| API answers with a valid body | Data from the API. Log: `[projects] N projects from <url>`. |
| Network error, 10 s timeout, non-200, or a body that fails the schema | Data from `src/data/projects.snapshot.json`. Log: `[projects] fetch <url> failed: <reason>`. The build still succeeds. |

`API_URL` defaults to `https://api.fatihiazmi.dev`.

Build against local data:

```bash
cd ../api && uv run python -m portfolio_api.seed --db /tmp/dev.db --publish
DATABASE_PATH=/tmp/dev.db uv run uvicorn portfolio_api.main:app --port 8000
cd ../web && API_URL=http://127.0.0.1:8000 pnpm dev
```

Refresh the fallback from the live API. Plan T26 runs this before launch:

```bash
pnpm snapshot
```

## Systems map

`src/components/SystemsMap.astro` renders the hero map. Spec section 4.

| Stage | What shows |
|---|---|
| First paint | Static SVG from `MapStatic.astro`. |
| Map within 200 px of the viewport | `src/lib/map/scene.ts` and three.js load as one lazy chunk. The canvas fades in over the SVG. |
| WebGL or the chunk fails | The SVG stays. The console logs `[map] 3D map unavailable`. |

- The node list under the canvas holds every project. `Tab` moves through it, and `Enter` opens the side panel.
- Projects without `map_x` and `map_z` appear in the list only.
- The render loop stops while the map is off screen.
- The 3D chunk measures 133 KB gzipped at three.js 0.186.1. Budget: 300 KB.

## Contact form

`src/components/ContactForm.astro` posts JSON to `${API_URL}/api/contact`. Spec section 6.

| Variable | Where | Purpose |
|---|---|---|
| `PUBLIC_TURNSTILE_SITE_KEY` | Pages env, Production | Turnstile site key. Public. `pnpm dev` uses Cloudflare's always-pass test key when unset. |

The form switches to `mailto:` mode in these cases. The send button then opens the visitor's mail app with the message pre-filled.

- The production build has no `PUBLIC_TURNSTILE_SITE_KEY`. The build log prints a warning.
- `GET /api/health` fails or takes over 5 s when the form nears the viewport.
- A send fails with a network error, a 5xx, or a 429.

The Turnstile script and the health probe load only when the form is within 400 px of the viewport, or on first focus.
The `mailto:` address is `CONTACT_EMAIL` in `src/lib/site.ts`.
WhatsApp: a button in the contact section and a floating button on every page (`src/components/WhatsAppFab.astro`).
The floating button hides while the contact section fills the upper 60% of the screen.
Number and greeting: `WHATSAPP_DISPLAY` and `WHATSAPP_URL` in `src/lib/site.ts`.

Accessibility rules for the form:

- Validation runs in script. Each invalid field gets `aria-invalid` and an inline error. Focus moves to the first one.
- Controls are at least 44 px tall. Inputs use 16 px text, so iOS does not zoom on focus.
- Text on WhatsApp green uses `ink-950` (9.5:1). White text fails at 2:1.
- Turnstile uses the full-width widget. Forms under 300 px wide get the compact widget.

Key setup: [`docs/guide/t9-contact-keys.md`](../docs/guide/t9-contact-keys.md).

## Styling

Tokens live in `src/styles/global.css` under `@theme`. Use them as Tailwind utilities, for example `bg-ink-900`, `text-paper`, `border-line`, `text-amber`.

| Token | Use |
|---|---|
| `ink-950`, `ink-900`, `ink-800` | Backgrounds, from deepest to panel |
| `line`, `line-strong` | Grid lines and borders |
| `paper` | Body text |
| `muted` | Secondary text |
| `cyan` | Accent, map nodes |
| `amber` | Calls to action and focus ring |

## Dependencies

- Versions are pinned exactly.
- `pnpm-workspace.yaml` sets `minimumReleaseAge: 10080`. pnpm refuses any version published in the last 7 days, including dependencies of dependencies.
