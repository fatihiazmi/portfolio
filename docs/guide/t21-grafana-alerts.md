# Guide: Grafana Login and Telegram Alerts (T21)

Goal: open `grafana.fatihiazmi.dev` after an Access login, and get alerts in Telegram.
Time: 20–25 minutes.
Cost: free.

The code is done. Grafana, its dashboards, and its 5 alert rules load from git on the `obs` LXC (203). You create 3 things that only your accounts can create: a Telegram bot, a Cloudflare tunnel, and an Access application.

| Key | Where it comes from | Secret? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather, step 1 | Yes |
| `CLOUDFLARED_TUNNEL_TOKEN` | Tunnel `obs`, step 2 | Yes |
| `GRAFANA_ACCESS_AUD` | Access app `portfolio-grafana`, step 3 | No, but keep it out of git |

Claude fills the rest from the `app` LXC or generates it: `TELEGRAM_CHAT_ID`, `CF_ACCESS_TEAM_DOMAIN`, `ADMIN_EMAIL`, `RESEND_API_KEY`, `ALERT_EMAIL`, `GRAFANA_ADMIN_PASSWORD`.

Never paste a secret into chat, git, or `docs/notes.md`.

## 1. Telegram bot

1. In Telegram, open a chat with **@BotFather**. Check the blue verified tick.
2. Send `/newbot`.
3. Name: `fatihiazmi.dev alerts`. Username: any free name that ends in `bot`, for example `fatihiazmi_alerts_bot`.
4. BotFather replies with the token, in the form `123456789:AA...`. Keep the chat open for step 4.
5. Open a chat with your new bot. Press **Start**, then send any message, for example `hi`.

Step 5 matters. A bot cannot message you until you message it first. Claude reads your chat ID from that message.

## 2. Tunnel `obs`

A second tunnel keeps Grafana reachable when the `app` LXC is down. That is when you need Grafana most.

1. `dash.cloudflare.com` → **Networking** → **Tunnels** → **Create Tunnel**. The menu moved out of Zero Trust in 2026. The `portfolio` tunnel shows in the same list.
2. Type: **Cloudflared**. Name: `obs`. Save.
3. On the install page, pick **Docker**. The command ends with a long token after `--token`. Copy only the token. Never run the command: compose runs cloudflared.
4. Continue to the route step. The dashboard calls it a public hostname, a published application, or a route. Add:

| Field | Value |
|---|---|
| Subdomain | `grafana` |
| Domain | `fatihiazmi.dev` |
| Path | empty |
| Service type | `HTTP` |
| URL | `grafana:3000` |

5. Save.

The tunnel shows **Inactive** or **Down** until step 4 starts cloudflared.
The route form matches the `portfolio` tunnel's route for `api.fatihiazmi.dev` → `api:8000`. Open it as an example.

## 3. Access application

Do this before step 4. Without it, `grafana.fatihiazmi.dev` opens Grafana's own login page on the internet.

1. **Zero Trust** → **Access controls** → **Applications** → **Add an application** → **Self-hosted**.
2. Fill the form:

| Field | Value |
|---|---|
| Application name | `portfolio-grafana` |
| Session duration | `24 hours` |
| Public hostname | Subdomain `grafana`, domain `fatihiazmi.dev`, path empty |

3. Policy: select the existing `owner-only` policy from T14. If it is not offered, create it again: Action **Allow**, Include **Emails**, your email.
4. **Save**.
5. Copy the AUD tag: **Applications** → `portfolio-grafana` → **Edit** → **Additional settings** → **Application Audience (AUD) Tag**.

This AUD differs from the admin app's AUD. Grafana rejects a login that carries the wrong one.

## 4. Put the 3 values on the LXC

From the Proxmox host shell:

```bash
pct enter 203
cd /opt/portfolio/infra/obs
nano .env
```

Add these lines at the end:

```
TELEGRAM_BOT_TOKEN=<token from step 1>
CLOUDFLARED_TUNNEL_TOKEN=<token from step 2>
GRAFANA_ACCESS_AUD=<AUD tag from step 3>
```

Save. Then run:

```bash
ls -l .env    # -rw------- 1 root root
exit
```

Tell Claude the values are in. Claude adds the other keys, starts Grafana and the tunnel, and sends a test alert.

## 5. Check

| Check | Expected |
|---|---|
| Open `https://grafana.fatihiazmi.dev` in a private window | Access login page. After the PIN: Grafana, signed in as your email, role Admin. |
| `curl -s -o /dev/null -w "%{http_code}\n" https://grafana.fatihiazmi.dev` | `302` to the Access login. Never `200`. |
| Telegram | A test message from the bot |
| Inbox | A test email from `alerts@fatihiazmi.dev` |

## Rotate a key

| Key | Steps |
|---|---|
| Bot token | BotFather → `/revoke` → pick the bot. Replace the line in `.env`. Run `docker compose up -d grafana`. |
| Tunnel token | **Tunnels** → `obs` → **Refresh token**. Replace the line. Run `docker compose up -d cloudflared`. |
| AUD | Changes only when you delete and recreate the Access app. Replace the line. Run `docker compose up -d grafana`. |
