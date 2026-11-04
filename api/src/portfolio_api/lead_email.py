"""Lead notification email: subject, plain text, and HTML.

Every value from the visitor passes through `html.escape` before it enters the HTML.
The layout uses tables and inline styles only, because mail clients strip `<style>`
blocks and ignore most CSS layout. Colours follow the site's blueprint tokens.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

# Malaysia has no daylight saving. A fixed offset avoids a tzdata dependency in the image.
MYT = timezone(timedelta(hours=8), "MYT")

KIND_LABELS = {"freelance": "Freelance project", "hiring": "Hiring", "other": "Other"}
BUDGET_LABELS = {
    "<RM10k": "Under RM10k",
    "RM10k–50k": "RM10k – RM50k",
    "RM50k+": "Over RM50k",
    "unsure": "Not sure yet",
}

INK = "#0a1c30"
PAPER = "#f4f6f9"
LINE = "#dde3ec"
MUTED = "#5b6b80"
TEXT = "#16202c"
AMBER = "#ffb547"
CYAN_DARK = "#0b6fa4"


@dataclass(frozen=True)
class Lead:
    id: int
    created_at: datetime
    name: str
    email: str
    company: str | None
    kind: str
    budget: str | None
    message: str


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _subject(lead: Lead) -> str:
    who = lead.name if not lead.company else f"{lead.name}, {lead.company}"
    return _one_line(f"New lead: {who} · {KIND_LABELS[lead.kind]}")[:200]


def _rows(lead: Lead) -> list[tuple[str, str]]:
    """(label, value) pairs shown in both the text and the HTML body. Values are raw."""
    rows = [("Name", lead.name), ("Email", lead.email)]
    if lead.company:
        rows.append(("Company", lead.company))
    rows.append(("About", KIND_LABELS[lead.kind]))
    if lead.kind == "freelance":
        rows.append(("Budget", BUDGET_LABELS.get(lead.budget or "", "Not given")))
    rows.append(("Received", _received(lead.created_at)))
    return rows


def _received(at: datetime) -> str:
    return at.astimezone(MYT).strftime("%a %d %b %Y, %H:%M MYT")


def _reply_href(lead: Lead) -> str:
    subject = quote("Re: your enquiry on fatihiazmi.dev")
    return f"mailto:{quote(lead.email, safe='@.+-_')}?subject={subject}"


def _text(lead: Lead) -> str:
    width = max(len(label) for label, _ in _rows(lead))
    lines = [f"New lead #{lead.id}", ""]
    lines += [f"{label.ljust(width)}  {value}" for label, value in _rows(lead)]
    lines += ["", "Message", "-------", lead.message, ""]
    lines.append(f"Reply to this email to answer {lead.name} directly.")
    return "\n".join(lines)


def _html(lead: Lead) -> str:
    preheader = escape(_one_line(lead.message)[:120])
    detail_rows = "".join(
        f'<tr><td style="padding:8px 0;width:96px;vertical-align:top;color:{MUTED};'
        f'font-size:13px;line-height:22px;">{escape(label)}</td>'
        f'<td style="padding:8px 0;vertical-align:top;color:{TEXT};font-size:15px;'
        f'line-height:22px;">'
        f"{_value_html(lead, label, value)}</td></tr>"
        for label, value in _rows(lead)
    )
    message = escape(lead.message)
    name = escape(lead.name)
    kind = escape(KIND_LABELS[lead.kind])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>New lead #{lead.id}</title>
</head>
<body style="margin:0;padding:0;background:{PAPER};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:8px;
  font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:{INK};padding:16px 24px;border-radius:8px 8px 0 0;">
    <span style="font-family:'IBM Plex Mono',Menlo,Consolas,monospace;font-size:13px;
      color:#e6eef7;letter-spacing:0.5px;">
      <span style="color:#5cc8ff;">&#9671;</span> fatihiazmi.dev</span>
    <span style="float:right;font-family:'IBM Plex Mono',Menlo,Consolas,monospace;
      font-size:13px;color:#8aa4c2;">Lead #{lead.id}</span>
  </td></tr>
  <tr><td style="padding:24px 24px 8px;">
    <span style="display:inline-block;background:{AMBER};color:{INK};font-size:12px;
      font-weight:600;padding:3px 10px;border-radius:999px;">{kind}</span>
    <h1 style="margin:12px 0 0;font-size:22px;line-height:1.3;color:{TEXT};">
      New message from {name}</h1>
  </td></tr>
  <tr><td style="padding:8px 24px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      style="border-top:1px solid {LINE};border-bottom:1px solid {LINE};">
      {detail_rows}
    </table>
  </td></tr>
  <tr><td style="padding:16px 24px 8px;">
    <div style="color:{MUTED};font-size:13px;margin-bottom:8px;">Message</div>
    <div style="background:{PAPER};border-left:3px solid {AMBER};padding:14px 16px;
      color:{TEXT};font-size:15px;line-height:1.6;white-space:pre-wrap;
      word-break:break-word;">{message}</div>
  </td></tr>
  <tr><td style="padding:16px 24px 24px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="background:{INK};border-radius:6px;">
        <a href="{escape(_reply_href(lead))}" style="display:inline-block;padding:12px 22px;
          color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;">
          Reply to {name}</a>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:14px 24px;border-top:1px solid {LINE};color:{MUTED};font-size:12px;
    line-height:1.5;">
    Replying to this email answers {name} directly. Stored as lead #{lead.id}.
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _value_html(lead: Lead, label: str, value: str) -> str:
    if label == "Email":
        return (
            f'<a href="{escape(_reply_href(lead))}" style="color:{CYAN_DARK};'
            f'text-decoration:none;">{escape(value)}</a>'
        )
    return escape(value)


def render(lead: Lead) -> RenderedEmail:
    return RenderedEmail(subject=_subject(lead), text=_text(lead), html=_html(lead))
