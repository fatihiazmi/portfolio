"""Contact form endpoint. Spec section 6.

Check order, cheapest first:

1. Honeypot `website` filled: return the success body, store nothing. Bots learn nothing.
2. Rate limit: 5 stored leads per IP hash per hour. Returns 429.
3. Turnstile token check with Cloudflare. Returns 400 on a rejected token.
4. Store the lead with a salted HMAC of the IP. The raw IP is never stored.
5. Send one notification email after the response. A send error is logged.
   The lead stays in SQLite, so the admin Leads screen still shows it.

The honeypot runs before Turnstile, unlike the spec order. Both paths return
the same body, so the order is not visible to the client, and it saves a
Cloudflare call per bot.
"""

import hashlib
import hmac
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from portfolio_api.config import Settings

log = logging.getLogger("portfolio_api.contact")

router = APIRouter(prefix="/api/contact", tags=["contact"])

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
RESEND_SEND_URL = "https://api.resend.com/emails"
RATE_LIMIT = 5
RATE_WINDOW = timedelta(hours=1)

Kind = Literal["freelance", "hiring", "other"]
Budget = Literal["<RM10k", "RM10k–50k", "RM50k+", "unsure"]


class ContactIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    email: Annotated[EmailStr, Field(max_length=254)]
    company: Annotated[str | None, Field(max_length=150)] = None
    kind: Kind
    budget: Budget | None = None
    message: Annotated[str, Field(min_length=20, max_length=5000)]
    # Honeypot. Any type and length are accepted, so a filled value never fails validation.
    website: str | None = None
    turnstile_token: Annotated[str, Field(min_length=1, max_length=2048)]


class ContactOut(BaseModel):
    ok: bool


OK = ContactOut(ok=True)


def client_ip(request: Request) -> str:
    """Visitor IP. Cloudflare sets `CF-Connecting-IP` at the edge.

    The API port binds to loopback on the LXC, so every outside request arrives
    through the tunnel and carries the header. Local dev falls back to the socket peer.
    """
    header = request.headers.get("cf-connecting-ip", "").strip()
    if header:
        return header
    return request.client.host if request.client else "unknown"


def ip_hash(salt: str, ip: str) -> str:
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


def _recent_count(conn: sqlite3.Connection, hashed: str, now: datetime) -> int:
    since = (now - RATE_WINDOW).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE ip_hash = ? AND created_at > ?", (hashed, since)
    ).fetchone()
    return int(row[0])


def _turnstile_ok(http: httpx.Client, secret: str, token: str, ip: str) -> bool:
    """True when Cloudflare accepts the token. Raises `httpx.HTTPError` when Cloudflare is down."""
    res = http.post(
        TURNSTILE_VERIFY_URL, data={"secret": secret, "response": token, "remoteip": ip}
    )
    res.raise_for_status()
    body = res.json()
    if body.get("success") is True:
        return True
    log.info("turnstile rejected token: %s", body.get("error-codes"))
    return False


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _send_notification(
    http: httpx.Client, settings: Settings, lead_id: int, lead: ContactIn
) -> None:
    """Email the owner. Runs after the response. Errors are logged, never raised."""
    lines = [
        f"Kind: {lead.kind}",
        f"Budget: {lead.budget or '-'}",
        f"Name: {lead.name}",
        f"Email: {lead.email}",
        f"Company: {lead.company or '-'}",
        "",
        lead.message,
        "",
        f"Lead #{lead_id}. Reply to this email to answer the sender.",
    ]
    payload = {
        "from": settings.lead_from_email,
        "to": [settings.lead_notify_email],
        "reply_to": lead.email,
        "subject": _one_line(f"[{lead.kind}] New lead from {lead.name}")[:200],
        "text": "\n".join(lines),
    }
    try:
        res = http.post(
            RESEND_SEND_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Idempotency-Key": f"lead/{lead_id}",
            },
        )
        res.raise_for_status()
    except httpx.HTTPError:
        log.exception("lead %s: notification email failed", lead_id)
        return
    log.info("lead %s: notification email sent", lead_id)


@router.post("", response_model=ContactOut)
def create_lead(body: ContactIn, request: Request, background: BackgroundTasks) -> ContactOut:
    settings: Settings = request.app.state.settings
    if not settings.contact_ready:
        log.error("contact: IP_HASH_SALT or TURNSTILE_SECRET is not set")
        raise HTTPException(status_code=503, detail="contact form is not configured")

    if body.website:
        log.info("contact: honeypot filled, lead dropped")
        return OK

    conn: sqlite3.Connection = request.app.state.db
    http: httpx.Client = request.app.state.http
    ip = client_ip(request)
    hashed = ip_hash(settings.ip_hash_salt, ip)
    now = datetime.now(UTC)

    if _recent_count(conn, hashed, now) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="too many messages, try again in an hour")

    try:
        accepted = _turnstile_ok(http, settings.turnstile_secret, body.turnstile_token, ip)
    except httpx.HTTPError:
        log.exception("contact: turnstile check failed to run")
        raise HTTPException(status_code=502, detail="spam check unavailable") from None
    if not accepted:
        raise HTTPException(status_code=400, detail="spam check failed, reload and try again")

    budget = body.budget if body.kind == "freelance" else None
    cur = conn.execute(
        "INSERT INTO leads (created_at, name, email, company, kind, budget, message, ip_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            now.isoformat(),
            body.name,
            body.email,
            body.company or None,
            body.kind,
            budget,
            body.message,
            hashed,
        ),
    )
    lead_id = int(cur.lastrowid or 0)
    log.info("contact: lead %s stored, kind=%s", lead_id, body.kind)

    if settings.email_ready:
        background.add_task(
            _send_notification, http, settings, lead_id, body.model_copy(update={"budget": budget})
        )
    else:
        log.warning("lead %s: RESEND_API_KEY or LEAD_NOTIFY_EMAIL not set, no email", lead_id)
    return OK
