import pytest

from app.services import enrichment
from tests.conftest import make_campaign, register

# ---------- extraction ----------


def test_extract_emails_filters_junk():
    page = """
      <img src="logo@2x.png"> <a href="mailto:Info@Bright.example">Email us</a>
      noreply@bright.example, user@example.com, owner&#64;bright.example
      <script src="sentry@abc.sentry.io"></script>
    """
    # owner&#64;... is an HTML-encoded "@" and is a real address, so it must be found.
    assert enrichment.extract_emails(page) == ["info@bright.example", "owner@bright.example"]


def test_extract_emails_dedupes_and_lowercases():
    page = "Contact: A@Shop.example  and a@shop.example and b@shop.example."
    assert enrichment.extract_emails(page) == ["a@shop.example", "b@shop.example"]


def test_pick_best_prefers_own_domain_then_role():
    emails = ["random@gmail.com", "dr.smith@bright.example", "info@bright.example"]
    assert enrichment.pick_best_email(emails, "www.bright.example") == "info@bright.example"
    # Only third-party addresses: still returns something rather than nothing.
    assert enrichment.pick_best_email(["x@gmail.com"], "bright.example") == "x@gmail.com"
    assert enrichment.pick_best_email([], "bright.example") is None


# ---------- SSRF guard ----------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://127.0.0.1:8000/admin",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "ftp://example.org/",
        "not a url",
    ],
)
def test_unsafe_urls_are_rejected(url):
    assert enrichment.is_safe_url(url) is False


def test_public_ip_is_allowed():
    assert enrichment.is_safe_url("http://8.8.8.8/") is True


def test_fetch_page_refuses_private_address():
    # Must return None immediately without ever connecting.
    assert enrichment.fetch_page("http://127.0.0.1:1/") is None


# ---------- finding an email for a site ----------


def test_find_email_crawls_contact_page(monkeypatch):
    monkeypatch.setattr(enrichment, "is_safe_url", lambda url: True)
    pages = {
        "https://bright.example/": "<html>Welcome</html>",
        "https://bright.example/contact": '<a href="mailto:hello@bright.example">hi</a>',
    }
    result = enrichment.find_email_for_site(
        "bright.example", fetch=lambda url: pages.get(url), check_robots=False
    )
    assert result == "hello@bright.example"


def test_find_email_returns_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr(enrichment, "is_safe_url", lambda url: True)
    assert enrichment.find_email_for_site("bright.example", fetch=lambda url: None, check_robots=False) is None


def test_find_email_blocks_unsafe_site():
    called = []
    result = enrichment.find_email_for_site(
        "http://127.0.0.1", fetch=lambda url: called.append(url), check_robots=False
    )
    assert result is None
    assert called == []  # never even tried to fetch


# ---------- endpoint ----------

CSV = (
    "name,website\n"
    "Bright Smile,https://bright.example\n"
    "Oak Dental,https://oak.example\n"
    "No Email Clinic,https://none.example\n"
    "No Website,\n"
)


def _setup(client, monkeypatch, suppress=None):
    emails = {
        "https://bright.example": "info@bright.example",
        "https://oak.example": "info@oak.example",
    }
    monkeypatch.setattr(enrichment, "find_email_for_site", lambda site: emails.get(site))
    h = register(client)
    cid = make_campaign(client, h)
    client.post(
        f"/campaigns/{cid}/leads/import",
        headers=h,
        files={"file": ("l.csv", CSV, "text/csv")},
    )
    if suppress:
        client.post("/suppressions", headers=h, json={"email": suppress})
    return h, cid


def test_enrich_endpoint_fills_emails(client, monkeypatch):
    h, cid = _setup(client, monkeypatch)
    r = client.post(f"/campaigns/{cid}/enrich", headers=h, json={})
    assert r.json() == {"checked": 3, "found": 2, "not_found": 1, "suppressed": 0}

    items = {i["name"]: i for i in client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]}
    assert items["Bright Smile"]["email"] == "info@bright.example"
    assert items["No Email Clinic"]["email"] is None


def test_enrich_does_not_retry_already_checked_leads(client, monkeypatch):
    h, cid = _setup(client, monkeypatch)
    client.post(f"/campaigns/{cid}/enrich", headers=h, json={})
    again = client.post(f"/campaigns/{cid}/enrich", headers=h, json={}).json()
    assert again["checked"] == 0


def test_enrich_respects_limit(client, monkeypatch):
    h, cid = _setup(client, monkeypatch)
    r = client.post(f"/campaigns/{cid}/enrich", headers=h, json={"limit": 1}).json()
    assert r["checked"] == 1


def test_enrich_never_stores_suppressed_email(client, monkeypatch):
    h, cid = _setup(client, monkeypatch, suppress="info@oak.example")
    r = client.post(f"/campaigns/{cid}/enrich", headers=h, json={}).json()
    assert r["suppressed"] == 1 and r["found"] == 1

    items = {i["name"]: i for i in client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]}
    assert items["Oak Dental"]["email"] is None
    assert items["Oak Dental"]["status"] == "do_not_contact"


def test_enrich_is_tenant_isolated(client, monkeypatch):
    _, cid = _setup(client, monkeypatch)
    other = register(client, "b@example.com", "B Co")
    assert client.post(f"/campaigns/{cid}/enrich", headers=other, json={}).status_code == 404
