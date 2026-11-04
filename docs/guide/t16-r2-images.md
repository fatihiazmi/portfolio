# Guide: R2 Images Bucket and Token (T16)

Goal: a public R2 bucket at `img.fatihiazmi.dev`, plus an API token that reaches only that bucket.
Time: 10–15 minutes.
Cost: free tier. R2 gives 10 GB storage and 10 million read requests a month. Reads through the custom domain have no egress fee.

The code is done. Until the four `R2_*` keys are in the LXC `.env`, image and diagram uploads return 503. Every other admin endpoint works without them.

| Key | Where it goes | Public? |
|---|---|---|
| `R2_ACCOUNT_ID` | LXC `.env` | Not secret. Same value as in `.env.litestream`. |
| `R2_IMAGES_BUCKET` | LXC `.env` | Yes. |
| `R2_ACCESS_KEY_ID` | LXC `.env` | No. |
| `R2_SECRET_ACCESS_KEY` | LXC `.env` | No. Shown once at creation. |

## 1. Create the bucket

1. `dash.cloudflare.com` → **R2 Object Storage** → **Create bucket**.
2. Name: `portfolio-images`.
3. Location: **Automatic**. Add the hint **Asia-Pacific (APAC)**.
4. Storage class: **Standard**.

## 2. Connect the custom domain

1. Open the bucket → **Settings** → **Custom Domains** → **Add**.
2. Domain: `img.fatihiazmi.dev`. Click **Continue**, then **Connect domain**.
3. Wait until the status shows **Active**. This takes 1–5 minutes.
4. Leave **Public Development URL** (`r2.dev`) off. The custom domain gets the Cloudflare cache. `r2.dev` does not.

Every object in this bucket is public through `img.fatihiazmi.dev`. Upload only scrubbed screenshots. The site still hides an image until you mark it `scrubbed`, but its URL works from the moment of upload.

## 3. Create the token

1. **R2 Object Storage** → **Manage API tokens** → **Create Account API token**.
2. Name: `api-portfolio-images`.
3. Permissions: **Object Read & Write**.
4. Specify buckets: **Apply to specific buckets only** → `portfolio-images`.
5. TTL: **Forever**.
6. Click **Create**. The page shows the **Access Key ID** and **Secret Access Key** once. Keep the page open for step 4.

Never reuse the Litestream token. A leaked images key must not reach the backups.

## 4. Put the keys on the LXC

Never paste the keys into chat, git, or `docs/notes.md`.

From the Proxmox host shell:

```bash
pct enter 202
cd /opt/portfolio/infra/app
nano .env
```

Add these lines:

```
R2_ACCOUNT_ID=<account id, same as in .env.litestream>
R2_IMAGES_BUCKET=portfolio-images
R2_ACCESS_KEY_ID=<access key id>
R2_SECRET_ACCESS_KEY=<secret access key>
```

Save. Then run:

```bash
ls -l .env    # -rw------- 1 root root
docker compose up -d api
docker compose logs api | grep -i "image uploads off"    # no output
exit
```

## 5. Record

Tell Claude "R2 images done". Claude checks an upload end to end and records the bucket, domain, token name, and date in `docs/notes.md`. Never the keys.

Done when: `img.fatihiazmi.dev` is **Active** on the bucket, and the API log has no `image uploads off` line.
