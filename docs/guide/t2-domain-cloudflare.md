# Guide: Buy the Domain and Move DNS to Cloudflare (T2)

Goal: a domain whose DNS zone is active in Cloudflare.
Time: 20–40 minutes, plus nameserver propagation if you buy outside Cloudflare.
Cost: about USD 10–15 a year for `.com` or `.dev`.

## 1. Pick the name

| Option | Example | Note |
|---|---|---|
| Your name, `.com` | `fatihiazmi.com` | Easiest for clients to remember and type. |
| Your name, `.dev` | `fatihiazmi.dev` | Signals engineer. Browsers force HTTPS on `.dev`. Cloudflare handles that. |
| Your name, `.my` | `fatihiazmi.my` | Signals a Malaysian business. Cloudflare Registrar does not sell `.my`, so use path B. |

Pick one. Subdomains come later from this one name: `api.`, `grafana.`, `img.`.

## 2. Create the Cloudflare account

1. Sign up at `dash.cloudflare.com`.
2. Turn on two-factor authentication: **My Profile → Authentication**. This account controls your DNS, tunnel, and admin login. Losing it means losing the site.

## 3A. Buy through Cloudflare Registrar (`.com`, `.dev`)

1. In the dashboard, open **Domain Registration → Register Domains**. If the menu name differs, search the dashboard for "Register domain".
2. Search the name. Pick a 1-year term.
3. Enter contact details. Cloudflare redacts WHOIS data by default.
4. Pay. The zone is created on Cloudflare DNS automatically.
5. Go to step 4.

## 3B. Buy elsewhere (`.my` or other TLDs)

1. Buy the domain from a registrar that sells the TLD. For `.my`, use a MYNIC-accredited registrar.
2. In Cloudflare, open **Add a domain**. Enter the domain. Pick the **Free** plan.
3. Cloudflare shows two nameservers, for example `xxx.ns.cloudflare.com`.
4. At your registrar, replace the default nameservers with those two.
5. Remove DNSSEC at the registrar before the switch, if it is on. Turn it back on later from Cloudflare.
6. Wait until the Cloudflare zone shows **Active**. This takes minutes to 24 hours.

## 4. Base zone config

In the zone dashboard:

| Where | Setting |
|---|---|
| **SSL/TLS → Overview** | Mode: **Full (strict)** |
| **SSL/TLS → Edge Certificates** | **Always Use HTTPS**: on. **Minimum TLS Version**: 1.2. |
| **DNS → Records** | Leave empty for now. Pages (T8) and the tunnel (T5) create their own records. |
| **DNS → Settings** | **DNSSEC**: on. |

## 5. Check

Run from your laptop:

```bash
dig NS <your-domain> +short
```

The output lists two `*.ns.cloudflare.com` names. The zone shows **Active** in the dashboard.

## 6. Record

Add to `docs/notes.md` under **Domain**: the domain name, the registrar, and the renewal date.

Done when: the zone shows **Active** and `dig` returns the Cloudflare nameservers.
