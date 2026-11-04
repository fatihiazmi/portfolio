from datetime import UTC, datetime

from portfolio_api.lead_email import Lead, render

AT = datetime(2026, 11, 4, 2, 3, tzinfo=UTC)


def _lead(**overrides: object) -> Lead:
    values: dict[str, object] = {
        "id": 7,
        "created_at": AT,
        "name": "Aisyah Rahman",
        "email": "aisyah@example.com",
        "company": "Acme Sdn Bhd",
        "kind": "freelance",
        "budget": "<RM10k",
        "message": "Line one.\nLine two with 40 sites.",
    }
    values.update(overrides)
    return Lead(**values)  # type: ignore[arg-type]


def test_subject_names_sender_company_and_kind() -> None:
    assert render(_lead()).subject == "New lead: Aisyah Rahman, Acme Sdn Bhd · Freelance project"
    assert render(_lead(company=None, kind="hiring")).subject == "New lead: Aisyah Rahman · Hiring"


def test_subject_is_one_line() -> None:
    subject = render(_lead(name="A\r\nBcc: x@evil.example")).subject
    assert "\n" not in subject
    assert "\r" not in subject


def test_text_body_lists_fields_and_message() -> None:
    text = render(_lead()).text
    assert "New lead #7" in text
    assert "Budget    Under RM10k" in text
    assert "Received  Wed 04 Nov 2026, 10:03 MYT" in text
    assert "Line one.\nLine two with 40 sites." in text


def test_budget_shown_only_for_freelance() -> None:
    email = render(_lead(kind="hiring", budget=None))
    assert "Budget" not in email.text
    assert "Budget" not in email.html


def test_missing_budget_on_freelance_says_not_given() -> None:
    assert "Not given" in render(_lead(budget=None)).text


def test_company_row_omitted_when_empty() -> None:
    assert "Company" not in render(_lead(company=None)).text


def test_html_escapes_every_visitor_value() -> None:
    evil = "<script>alert(1)</script>"
    html = render(
        _lead(
            name=evil,
            company=f'"><img src=x onerror=alert(1)>{evil}',
            message=evil,
            email='a"b@example.com',
        )
    ).html
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert 'a"b@' not in html


def test_html_has_reply_link_and_lead_id() -> None:
    html = render(_lead()).html
    assert 'href="mailto:aisyah@example.com?subject=Re%3A%20your%20enquiry' in html
    assert "Lead #7" in html
    assert "Wed 04 Nov 2026, 10:03 MYT" in html
