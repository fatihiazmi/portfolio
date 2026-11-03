# Guide: R2 Backup Bucket and Token (T6)

Goal: an R2 bucket for Litestream, plus an API token that reaches only that bucket.
Time: 10–15 minutes.
Cost: free tier. R2 gives 10 GB storage and 1 million write requests a month. The database is under 1 MB.

## 1. Turn on R2

1. Open `dash.cloudflare.com` → **R2 Object Storage**.
2. If R2 is off, follow the prompt. Cloudflare asks for a payment method even on the free tier.
3. Copy the **Account ID** from the R2 overview page, right column.

## 2. Create the bucket

1. **R2 Object Storage → Create bucket**.
2. Name: `portfolio-backup`.
3. Location: **Automatic**. Add the hint **Asia-Pacific (APAC)**.
4. Storage class: **Standard**.
5. Leave **Public access** off. Never connect a custom domain to this bucket.

## 3. Create the token

1. **R2 Object Storage → Manage API tokens → Create Account API token**.
2. Name: `litestream-portfolio-backup`.
3. Permissions: **Object Read & Write**.
4. Specify buckets: **Apply to specific buckets only** → `portfolio-backup`.
5. TTL: **Forever**.
6. Click **Create**. The page shows the **Access Key ID** and **Secret Access Key** once. Keep the page open for step 4.

An account token keeps working if your user account changes. The bucket scope means a leaked key cannot touch the images bucket.

## 4. Put the keys on the LXC

Never paste the keys into chat, git, or `docs/notes.md`.

From the Proxmox host shell:

```bash
pct enter 202
cd /opt/portfolio/infra/app
umask 077
nano .env.litestream
```

File contents:

```
R2_ACCOUNT_ID=<account id from step 1>
R2_BACKUP_BUCKET=portfolio-backup
LITESTREAM_ACCESS_KEY_ID=<access key id>
LITESTREAM_SECRET_ACCESS_KEY=<secret access key>
```

Save. Then run:

```bash
chmod 600 .env.litestream
ls -l .env.litestream    # -rw------- 1 root root
exit
```

## 5. Record

Add to `docs/notes.md` under **R2 (T6)**: the bucket name, the location hint, the token name, and the date. Never the keys.

Done when: `.env.litestream` exists on LXC 202 with mode `600` and four non-empty values.
