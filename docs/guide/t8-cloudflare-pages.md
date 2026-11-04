# Guide: Cloudflare Pages and Deploy Hook (T8)

Goal: Pages builds `web/` from GitHub, serves it on `fatihiazmi.dev`, and has a deploy hook for the admin **Publish** button.
Time: 15–20 minutes, plus the first build and certificate issue.
Cost: free tier. 500 builds a month.

## 1. Create the project

1. `dash.cloudflare.com` → **Workers & Pages** → **Create** → **Pages** tab, or the link "Looking to deploy Pages? Get started" → **Import an existing Git repository**.

   The default **Create** flow makes a Worker, not a Pages project. A Worker has no deploy hooks. Check: the Pages setup screen has **Framework preset** and **Build output directory**. A screen with **Deploy command** `npx wrangler deploy` is the Worker flow.
2. Authorise the Cloudflare GitHub app for `fatihiazmi/portfolio` only, not all repositories.
3. Select `fatihiazmi/portfolio` → **Begin setup**.

## 2. Build settings

| Field | Value |
|---|---|
| Project name | `nik-portfolio` |
| Production branch | `main` |
| Framework preset | Astro |
| Build command | `pnpm build` |
| Build output directory | `dist` |
| Root directory (advanced) | `web` |

Environment variables (advanced), for **Production** and **Preview**:

| Name | Value | Reason |
|---|---|---|
| `PNPM_VERSION` | `11.25.0` | The build image defaults to pnpm 10.11.1. The repo uses pnpm 11 settings. |
| `ASTRO_TELEMETRY_DISABLED` | `1` | No telemetry from builds. |

Node comes from `web/.node-version` (24.13.1). `API_URL` is not needed. The default is `https://api.fatihiazmi.dev`.

Click **Save and Deploy**. The first build takes 1–2 minutes. It ends with a `*.pages.dev` URL.

## 3. Skip builds for non-web changes

**Settings → Builds → Build watch paths** → **Edit**:

| Field | Value |
|---|---|
| Include paths | `*` |
| Exclude paths | `api/*, admin/*, infra/*, docs/*` |

Commits that only touch `api/`, `admin/`, `infra/`, or `docs/` skip the build. Any other change builds. Deploy hooks build every time.

Use excludes, not `Include: web/*`. On 2026-11-03, `Include: web/*` skipped pushes `73596c8` and `d10eb22`, which changed only `web/src/` files and `docs/plan.md`. The cause is unconfirmed. If an exclude fails to match, you get an extra build. If an include fails to match, a deploy is lost.

Check after a web push: **Deployments** shows a new build for the commit, not "skipped".

## 4. Custom domain

1. **Custom domains → Set up a custom domain** → `fatihiazmi.dev` → **Continue** → **Activate domain**.
2. Cloudflare creates the DNS record in the zone. The certificate is ready in a few minutes.
3. Add `www.fatihiazmi.dev` the same way. Without it, `www.` returns "site can't be reached".
4. Zone `fatihiazmi.dev` → **Rules → Overview → Templates → Redirect from WWW to root** → **Create a rule**. Check the fields, then **Deploy**:

| Field | Value |
|---|---|
| Match | Wildcard pattern |
| Request URL | `https://www.*` |
| Target URL | `https://${1}` |
| Status code | `301 - Permanent Redirect` |
| Preserve query string | on. The template leaves it off. Tick it. |

Check: `curl -sI https://www.fatihiazmi.dev/stack | head -3` shows `301` and `location: https://fatihiazmi.dev/stack`.

## 5. Deploy hook

1. **Settings → Builds → Deploy hooks → Add deploy hook**.
2. Name: `admin-publish`. Branch: `main`.
3. Copy the URL. Anyone with this URL can start a build, so treat it as a secret.

Put it on the LXC. Never in chat, git, or `docs/notes.md`:

```bash
pct enter 202
cd /opt/portfolio/infra/app
nano .env    # set PAGES_DEPLOY_HOOK_URL=<url>
exit
```

## 6. Record

Add to `docs/notes.md` under **Pages (T8)**: the project name, the `*.pages.dev` URL, and the date. Never the hook URL.

Done when: `https://fatihiazmi.dev` shows the site, and `PAGES_DEPLOY_HOOK_URL` is set in `.env` on LXC 202.
