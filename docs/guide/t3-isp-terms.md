# Guide: Check ISP Terms on Home Hosting (T3)

Goal: know whether your home internet plan allows serving a public site.
Time: 15–30 minutes.

## 1. Why it matters

Cloudflare Tunnel opens no inbound ports. Traffic still leaves your home line to serve the public. Some residential plans ban running servers. A ban puts the plan at risk of suspension, and with it the contact form.

## 2. Find the document

1. Identify your plan name from your bill or the ISP app.
2. On the ISP website, find the **Terms and Conditions**, **Acceptable Use Policy (AUP)**, or **Fair Usage Policy** for that residential plan.
3. Save the PDF or page URL and the date you read it.

## 3. Search the text

Search the document for these words:

| Word | What to look for |
|---|---|
| `server` | "Customer must not run a server" or similar |
| `host` / `hosting` | A ban on hosting websites or services |
| `commercial` | Residential plans limited to non-commercial use |
| `resell` / `resale` | A ban on reselling the connection. This does not apply to a portfolio. |
| `bandwidth` / `fair usage` | Limits on upload volume |

## 4. Decide

| What the terms say | Verdict | Action |
|---|---|---|
| Nothing about servers or hosting | Go | Proceed with the plan. |
| Bans reselling only | Go | A portfolio does not resell the connection. |
| Bans "commercial use" broadly | Grey | Expected traffic is tiny. Proceed, and keep the VPS fallback ready. |
| Bans running servers or hosting outright | No-go | Use the VPS fallback below, or ask the ISP about a business plan. |

### VPS fallback

The plan already isolates the risk:

- The static site stays on Cloudflare Pages. A home outage never takes it down.
- Only the `app` LXC moves. Its Docker Compose file runs unchanged on a small VPS.
- `cloudflared` runs on the VPS instead. DNS and Access stay the same.
- The `obs` LXC can stay at home and scrape the VPS over the tunnel, or move too.

## 5. Record

Add to `docs/notes.md` under **ISP**: the ISP, the plan name, the document URL and the date read, the exact clause quoted, and the verdict.

Done when: `docs/notes.md` holds the verdict with the quoted clause.
