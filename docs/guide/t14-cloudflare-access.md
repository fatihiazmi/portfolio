# Guide: Admin Login with Cloudflare Access (T14)

Goal: only you can open `api.fatihiazmi.dev/admin` and `api.fatihiazmi.dev/api/admin`.
Time: 15–20 minutes.
Cost: free. Zero Trust Free covers up to 50 users.

The code is done. Cloudflare Access asks for a login at the edge. The API then checks the Access token again on every admin request.

| Key | Where it goes | Public? |
|---|---|---|
| `CF_ACCESS_TEAM_DOMAIN` | LXC `.env` | Yes. It shows on the login page. |
| `CF_ACCESS_AUD` | LXC `.env` | Not secret, but keep it out of git. |
| `ADMIN_EMAIL` | LXC `.env` | No. Your login email. |

The API returns 503 on every admin path while any of the three is empty.

## 1. Zero Trust team

Skip this step if Zero Trust is already set up on the account.

1. `dash.cloudflare.com` → **Zero Trust**.
2. Pick a team name, for example `fatihiazmi`. Your team domain becomes `fatihiazmi.cloudflareaccess.com`.
3. Pick the **Free** plan. Cloudflare asks for a payment card even on Free.

Login method: keep the default **One-time PIN**. Access emails you a code at each login.

## 2. Access application

1. **Zero Trust** → **Access controls** → **Applications** → **Add an application** → **Self-hosted**.
2. Fill the form:

| Field | Value |
|---|---|
| Application name | `portfolio-admin` |
| Session duration | `24 hours` |
| Public hostname 1 | Subdomain `api`, domain `fatihiazmi.dev`, path `admin` |
| Public hostname 2 | Subdomain `api`, domain `fatihiazmi.dev`, path `api/admin` |

Use **Add public hostname** for the second row. Both paths belong to one application, so they share one AUD tag.

3. Add a policy:

| Field | Value |
|---|---|
| Policy name | `owner-only` |
| Action | Allow |
| Include | Selector **Emails**, value: your email |

4. **Save**.

The Tunnel needs no change. It already sends every path on `api.fatihiazmi.dev` to the API.

## 3. Copy the two values

| Value | Where |
|---|---|
| AUD tag | **Access controls** → **Applications** → `portfolio-admin` → **Edit** → **Additional settings** → **Application Audience (AUD) Tag** |
| Team domain | **Zero Trust** → **Settings** → **Team name and domain**. Copy the `<team>.cloudflareaccess.com` form. |

The AUD tag changes only when you delete and recreate the application.

## 4. Secrets on the LXC

From the Proxmox host shell:

```bash
pct enter 202
cd /opt/portfolio/infra/app
nano .env
```

Set these lines in `.env`:

```bash
CF_ACCESS_TEAM_DOMAIN=<team>.cloudflareaccess.com
CF_ACCESS_AUD=<AUD tag>
ADMIN_EMAIL=<the email in the owner-only policy>
```

`ADMIN_EMAIL` must match the policy email. Case does not matter. A token for any other email gets 403.

## 5. Deploy the API

Push the T14 commits to GitHub first. Then, still inside LXC 202:

```bash
cd /opt/portfolio && git pull --ff-only
cd infra/app && docker compose up -d --build
docker compose logs --tail 20 api | grep -i admin   # expect no "admin off" line
```

## 6. Test

1. Bypass test. Still inside LXC 202, call the API directly without Access:

```bash
curl -s -w ' %{http_code}\n' http://localhost:8000/api/admin/me
# expect: {"detail":"Admin login required."} 403
exit
```

2. Edge test. From your laptop, without a login:

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://api.fatihiazmi.dev/api/admin/me
# expect: 302 https://<team>.cloudflareaccess.com/...
```

3. Login test. Open `https://api.fatihiazmi.dev/api/admin/me` in a private window.
   - Access shows its login page. Enter your email, then the code from your inbox.
   - The page shows `{"email":"<your email>"}`.
4. Public test. `https://api.fatihiazmi.dev/api/health` still returns `{"ok":true}` without a login.

## 7. Record

Add to `docs/notes.md` under `## Admin access (T14)`:

- Date set up.
- Team domain.
- Application name: `portfolio-admin`. Policy: `owner-only`.
- Test results from step 6.

Do not record the AUD tag or your email in git.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 503 `Admin is not configured.` | One of the three `.env` values is empty | Check step 4. Run `docker compose up -d api`. |
| 403 after a good login | `ADMIN_EMAIL` differs from the login email, or the AUD tag is from another application | Run `docker compose logs api \| grep "admin denied"`. The line names the reason. |
| 403 on every request, log says `kid is not in the team keys` | Wrong team domain, so the API fetched the wrong keys | Check `CF_ACCESS_TEAM_DOMAIN` against step 3. |
| 403 `Missing X-Requested-With: admin header.` | A POST, PUT, PATCH, or DELETE without the header | The admin SPA (T17) sends it. For `curl`, add `-H 'X-Requested-With: admin'`. |
| No login page, the API answers 403 | The path is not in the application | Check both public hostnames in step 2. |
