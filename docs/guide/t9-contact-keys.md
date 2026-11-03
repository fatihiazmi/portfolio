# Guide: Contact Form Keys (T9)

Goal: the contact form on `fatihiazmi.dev` stores a lead in SQLite and emails it to you.
Time: 20–30 minutes, plus DNS checks for Resend.
Cost: free tiers. Turnstile is free. Resend free sends 3,000 emails a month, 100 a day.

The code is done. This guide sets the keys it reads.

| Key | Where it goes | Public? |
|---|---|---|
| `PUBLIC_TURNSTILE_SITE_KEY` | Pages env var | Yes. It ships in the page. |
| `TURNSTILE_SECRET` | LXC `.env` | No |
| `IP_HASH_SALT` | LXC `.env` | No |
| `RESEND_API_KEY` | LXC `.env` | No |
| `LEAD_NOTIFY_EMAIL` | LXC `.env` | No. Your inbox. |
| `LEAD_FROM_EMAIL` | LXC `.env`, optional | Sender. Default `fatihiazmi.dev <leads@fatihiazmi.dev>`. |

Never paste a secret in chat, git, or `docs/notes.md`.

## 1. Turnstile widget

1. `dash.cloudflare.com` → **Turnstile** → **Add widget**.
2. Fill the form:

| Field | Value |
|---|---|
| Widget name | `portfolio-contact` |
| Hostnames | `fatihiazmi.dev` |
| Widget mode | Managed |
| Pre-clearance | No |

3. **Create**. Copy the **Site Key** and the **Secret Key**.

Preview builds on `*.pages.dev` are not in the hostname list. Their form runs in `mailto:` mode. This is intended.

## 2. Site key on Pages

1. **Workers & Pages** → `nik-portfolio` → **Settings** → **Variables and Secrets** → **Add**.
2. Environment: **Production** only.
3. Type: plain text. Name: `PUBLIC_TURNSTILE_SITE_KEY`. Value: the site key.
4. **Save**. The variable applies from the next build. Step 6 runs that build.

## 3. Resend domain

1. Sign up at `resend.com` with the inbox that receives leads.
2. **Domains** → **Add Domain** → `fatihiazmi.dev`. Region: Tokyo (`ap-northeast-1`), the nearest to Malaysia.

   The API sends from `leads@fatihiazmi.dev`. The Resend domain must match it exactly. A key for `fatihiazmi.dev` gets 403 for a sender on `send.fatihiazmi.dev`, and the reverse.
3. Resend lists DNS records: a DKIM `TXT` at `resend._domainkey`, and bounce records on the `send` subdomain.
4. Zone `fatihiazmi.dev` → **DNS** → **Records**. Add each record exactly as Resend lists it. Proxy status does not apply to `TXT` and `MX`.

   Resend has a **Sign in to Cloudflare** button that adds the records for you. Either way works.
5. Back in Resend → **Verify DNS Records**. Wait until the domain shows **Verified**. This takes from 1 minute to a few hours.
6. **API Keys** → **Create API Key**:

| Field | Value |
|---|---|
| Name | `portfolio-api` |
| Permission | Sending access |
| Domain | `fatihiazmi.dev` |

7. Copy the key. Resend shows it once.

## 4. Secrets on the LXC

From the Proxmox host shell:

```bash
pct enter 202
cd /opt/portfolio/infra/app
openssl rand -hex 32      # copy the output for IP_HASH_SALT
nano .env
```

Set these lines in `.env`:

```bash
IP_HASH_SALT=<openssl output>
TURNSTILE_SECRET=<Turnstile secret key>
RESEND_API_KEY=<Resend key>
LEAD_NOTIFY_EMAIL=<your inbox>
```

Keep `IP_HASH_SALT` fixed after launch. A new salt resets the rate limit history and makes old hashes unmatched.

## 5. Deploy the API

Still inside LXC 202:

```bash
cd /opt/portfolio && git pull --ff-only
cd infra/app && docker compose up -d --build
docker compose logs --tail 20 api | grep -i contact   # expect no "contact form off" line
exit
```

The new image runs migration `0002_leads_rate_limit` on start.

## 6. Rebuild the site

**Workers & Pages** → `nik-portfolio` → **Deployments** → latest production deployment → **⋯** → **Retry deployment**.

Check the build log. The line `PUBLIC_TURNSTILE_SITE_KEY is not set` must not appear.

## 7. Test from a phone

This is the T9 done-check.

1. Turn off Wi-Fi on the phone. Use mobile data.
2. Open `https://fatihiazmi.dev/#contact`.
3. Fill the form. Kind: **A project for my organisation**. Pick a budget. Message of 20+ characters.
4. **Send message**. Expect "Thanks. I reply within 2 working days."
5. Check the inbox for `[freelance] New lead from <name>`. Check the spam folder too.
6. Check SQLite:

```bash
pct exec 202 -- docker compose -f /opt/portfolio/infra/app/docker-compose.yml exec api \
  python -c "import sqlite3; print(sqlite3.connect('/data/portfolio.db').execute('SELECT id, created_at, kind, budget FROM leads ORDER BY id DESC LIMIT 3').fetchall())"
```

7. Reply to the email. The reply goes to the address typed in the form.

## 8. Record

Add to `docs/notes.md` under `## Contact (T9)`:

- Turnstile widget name and hostnames.
- Resend sending domain and its verify date.
- The phone test: date, time, and whether the email landed in the inbox or spam.

## Errors

| Symptom | Cause | Fix |
|---|---|---|
| Button says "Open in my mail app" on the live site | No site key in the build, or `/api/health` failed | Check step 2 and step 6. Run `curl -s https://api.fatihiazmi.dev/api/health`. |
| "The spam check failed" | Site key and secret are from different widgets, or the hostname is not listed | Check both keys come from `portfolio-contact`. Check the hostname list. |
| Lead in SQLite, no email | Resend domain unverified, a wrong key, or a sender on another domain | Run `docker compose logs api` and look for `notification email failed`. The line quotes Resend's reason. |
| API returns 503 `contact form is not configured` | `IP_HASH_SALT` or `TURNSTILE_SECRET` empty | Check step 4, then run `docker compose up -d api`. |
