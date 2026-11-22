import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import Draft, Suppression
from app.db.session import SessionLocal
from app.main import app
from app.services import compliance, email_draft
from app.services.llm import LLMError, LLMNotConfigured, LLMRateLimited, get_llm_client
from tests.conftest import make_campaign, register

GOOD_BODY = (
    "Hi Good Dental team, I noticed you have 120 Google reviews, which is a great sign of happy "
    "patients. I help local dental clinics get more new-patient bookings with a faster, "
    "mobile-friendly website. Would it be useful if I sent over two quick ideas for yours?"
)
PROFILE = {"sender_name": "Sam Rivera", "company_name": "Rivera Web Studio", "postal_address": "100 Congress Ave, Austin, TX 78701"}

CSV = (
    "name,website,email\n"
    "Good Dental,https://good.example,hello@good.example\n"
    "NoEmail Dental,https://noemail.example,\n"
    "Low Fit Co,https://low.example,info@low.example\n"
    "Blocked Co,https://blocked.example,no@blocked.example\n"
)


class FakeLLM:
    """Handles both scoring and drafting calls, picked by the response schema."""

    def __init__(self, draft=None):
        self.draft = draft or (lambda prompt: {"subject": "Quick idea for your website", "body": GOOD_BODY})
        self.prompts = []

    def generate_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        if "subject" in schema["properties"]:
            return self.draft(prompt)
        return {"score": 20 if "Low Fit Co" in prompt else 80, "reason": "Good fit."}


@pytest.fixture()
def use_llm(client):
    def _install(llm=None):
        llm = llm or FakeLLM()
        app.dependency_overrides[get_llm_client] = lambda: llm
        return llm

    yield _install
    app.dependency_overrides.clear()


def _setup(client, use_llm, llm=None, profile=PROFILE, score=True):
    fake = use_llm(llm)
    h = register(client)
    if profile:
        assert client.put("/workspace/profile", headers=h, json=profile).status_code == 200
    cid = make_campaign(client, h)
    client.post(f"/campaigns/{cid}/leads/import", headers=h, files={"file": ("l.csv", CSV, "text/csv")})
    client.post("/suppressions", headers=h, json={"email": "no@blocked.example"})
    if score:
        client.post(f"/campaigns/{cid}/score", headers=h, json={})
    return h, cid, fake


def generate(client, h, cid, **body):
    return client.post(f"/campaigns/{cid}/drafts/generate", headers=h, json=body)


# ---------- sender profile ----------


def test_profile_reports_whats_missing(client):
    h = register(client)
    p = client.get("/workspace/profile", headers=h).json()
    assert p["complete"] is False and set(p["missing"]) == {"sender_name", "company_name", "postal_address"}
    client.put("/workspace/profile", headers=h, json=PROFILE)
    assert client.get("/workspace/profile", headers=h).json()["complete"] is True
    # blank strings count as missing
    client.put("/workspace/profile", headers=h, json={**PROFILE, "postal_address": "   "})
    assert client.get("/workspace/profile", headers=h).json()["missing"] == ["postal_address"]


def test_cannot_generate_without_complete_profile(client, use_llm):
    h, cid, fake = _setup(client, use_llm, profile=None)
    r = generate(client, h, cid)
    assert r.status_code == 400 and "postal_address" in r.json()["detail"]
    assert not any("subject" in p for p in fake.prompts)  # no LLM spend either


# ---------- generation ----------


def test_only_reachable_high_scoring_leads_get_drafts(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    r = generate(client, h, cid).json()
    # Good Dental yes. NoEmail (nobody to write to), Low Fit (score 20), Blocked (opted out): no.
    assert r == {"generated": 1, "failed": 0, "rate_limited": False, "remaining": 0, "last_error": None}
    drafts = client.get(f"/campaigns/{cid}/drafts", headers=h).json()
    assert [d["lead_name"] for d in drafts] == ["Good Dental"]


def test_min_score_is_respected(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    r = generate(client, h, cid, min_score=10).json()
    assert r["generated"] == 2  # Low Fit Co (20) now qualifies too


def test_second_run_does_not_duplicate_or_respend(client, use_llm):
    h, cid, fake = _setup(client, use_llm)
    generate(client, h, cid)
    calls = len(fake.prompts)
    assert generate(client, h, cid).json()["generated"] == 0
    assert len(fake.prompts) == calls
    assert len(client.get(f"/campaigns/{cid}/drafts", headers=h).json()) == 1


def test_preview_always_has_signature_address_and_working_unsubscribe(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    generate(client, h, cid)
    d = client.get(f"/campaigns/{cid}/drafts", headers=h).json()[0]
    p = d["preview"]
    assert GOOD_BODY in p
    assert "Sam Rivera" in p and "Rivera Web Studio" in p and "100 Congress Ave, Austin, TX 78701" in p
    token = p.split("/u/")[1].split()[0]
    ws_id, email = compliance.read_unsubscribe_token(token)
    assert email == "hello@good.example" and isinstance(ws_id, int)


def test_footer_is_not_stored_in_the_body(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    generate(client, h, cid)
    with SessionLocal() as db:
        body = db.scalar(select(Draft.body))
    assert "Unsubscribe" not in body and "Congress Ave" not in body


def test_ai_untrusted_text_stays_inside_the_data_fence(client, use_llm):
    h, cid, fake = _setup(client, use_llm)
    generate(client, h, cid)
    prompt = next(p for p in fake.prompts if "Sender:" in p)
    inside = prompt.split("<business_data>")[1].split("</business_data>")[0]
    assert "why this lead scored well" in inside  # model-written, so also untrusted


# ---------- validation of AI output ----------


@pytest.mark.parametrize(
    "bad, why",
    [
        ({"subject": "Hello", "body": GOOD_BODY + " See https://evil.example now"}, "link"),
        ({"subject": "Hello", "body": GOOD_BODY + " Visit www.evil.example"}, "link"),
        ({"subject": "Re: our chat", "body": GOOD_BODY}, "deceptive"),
        ({"subject": "FWD: invoice", "body": GOOD_BODY}, "deceptive"),
        ({"subject": "Hello [Name]", "body": GOOD_BODY}, "placeholder"),
        ({"subject": "Hello", "body": "Hi [First Name], " + GOOD_BODY}, "placeholder"),
        ({"subject": "Hello", "body": "too short"}, "characters"),
        ({"subject": "x" * 200, "body": GOOD_BODY}, "subject"),
        ({"subject": "two\nlines", "body": GOOD_BODY}, "subject"),
        ({"subject": "", "body": GOOD_BODY}, "subject"),
        ({"subject": "Hi", "body": 123}, "text"),
    ],
)
def test_unsafe_ai_output_is_rejected_and_not_saved(client, use_llm, bad, why):
    h, cid, _ = _setup(client, use_llm, llm=FakeLLM(draft=lambda p: bad))
    r = generate(client, h, cid).json()
    assert r["generated"] == 0 and r["failed"] == 1 and why in r["last_error"].lower()
    assert client.get(f"/campaigns/{cid}/drafts", headers=h).json() == []
    # failed lead stays eligible so a retry can succeed
    assert r["remaining"] == 1


def test_non_object_model_output_is_rejected(client, use_llm):
    h, cid, _ = _setup(client, use_llm, llm=FakeLLM(draft=lambda p: ["nope"]))
    assert generate(client, h, cid).json()["failed"] == 1


def test_rate_limit_keeps_partial_progress(client, use_llm):
    state = {"n": 0}

    def limited(prompt):
        state["n"] += 1
        if state["n"] == 2:
            raise LLMRateLimited("slow down")
        return {"subject": "Quick idea", "body": GOOD_BODY}

    h, cid, _ = _setup(client, use_llm, llm=FakeLLM(draft=limited))
    r = generate(client, h, cid, min_score=10).json()
    assert r["generated"] == 1 and r["rate_limited"] is True and r["remaining"] == 1


def test_missing_api_key_gives_503(client, use_llm):
    def nokey(prompt):
        raise LLMNotConfigured("GEMINI_API_KEY is not set")

    h, cid, _ = _setup(client, use_llm, llm=FakeLLM(draft=nokey))
    assert generate(client, h, cid).status_code == 503


def test_validator_directly():
    assert email_draft.validate_draft("Quick idea", GOOD_BODY).subject == "Quick idea"
    with pytest.raises(LLMError):
        email_draft.validate_draft("Quick idea", GOOD_BODY + " http://x.example")
    # humans may add links
    assert email_draft.validate_draft("Quick idea", GOOD_BODY + " http://x.example", allow_links=True)


# ---------- editing and approving ----------


def _first_draft(client, h, cid):
    generate(client, h, cid)
    return client.get(f"/campaigns/{cid}/drafts", headers=h).json()[0]


def test_edit_and_approve_flow(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    d = _first_draft(client, h, cid)
    assert d["status"] == "draft"

    ok = client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True}).json()
    assert ok["status"] == "approved"

    # Editing after approval sends it back: what's approved is what the human last read.
    edited = client.patch(f"/drafts/{d['id']}", headers=h, json={"subject": "A better subject"}).json()
    assert edited["status"] == "draft" and edited["subject"] == "A better subject"

    # Edit + approve together is fine.
    both = client.patch(f"/drafts/{d['id']}", headers=h, json={"body": GOOD_BODY + " Thanks!", "approved": True}).json()
    assert both["status"] == "approved" and both["body"].endswith("Thanks!")


def test_human_edit_may_add_a_link_but_not_break_other_rules(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    d = _first_draft(client, h, cid)
    assert client.patch(f"/drafts/{d['id']}", headers=h, json={"body": GOOD_BODY + " Book: https://cal.example/me"}).status_code == 200
    assert client.patch(f"/drafts/{d['id']}", headers=h, json={"subject": "Re: hello"}).status_code == 422
    assert client.patch(f"/drafts/{d['id']}", headers=h, json={"body": "tiny"}).status_code == 422


def test_footer_survives_any_edit(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    d = _first_draft(client, h, cid)
    out = client.patch(f"/drafts/{d['id']}", headers=h, json={"body": "Hi there, " + GOOD_BODY}).json()
    assert "Unsubscribe here: http" in out["preview"] and "Congress Ave" in out["preview"]


def test_cannot_approve_a_lead_that_opted_out_meanwhile(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    d = _first_draft(client, h, cid)
    client.post("/suppressions", headers=h, json={"email": "hello@good.example"})
    r = client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True})
    assert r.status_code == 409


def test_drafts_are_tenant_isolated(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    d = _first_draft(client, h, cid)
    other = register(client, "b@example.com", "B Co")
    assert client.patch(f"/drafts/{d['id']}", headers=other, json={"approved": True}).status_code == 404
    assert client.get(f"/campaigns/{cid}/drafts", headers=other).status_code == 404
    assert generate(client, other, cid).status_code == 404


# ---------- public unsubscribe link ----------


def _unsub_path(client, h, cid):
    d = _first_draft(client, h, cid)
    return "/u/" + d["preview"].split("/u/")[1].split()[0]


def test_get_shows_confirmation_but_does_not_unsubscribe(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    path = _unsub_path(client, h, cid)
    page = client.get(path)
    assert page.status_code == 200 and "<form method='post'>" in page.text
    assert "hello@good.example" not in page.text  # address is masked on the page
    assert "h***@good.example" in page.text
    # A scanner/link-previewer doing GET must not opt anyone out.
    suppressed = [s["email"] for s in client.get("/suppressions", headers=h).json()]
    assert "hello@good.example" not in suppressed


def test_post_unsubscribes_and_blocks_future_contact(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    path = _unsub_path(client, h, cid)
    r = client.post(path)
    assert r.status_code == 200 and "unsubscribed" in r.text.lower()

    assert any(s["email"] == "hello@good.example" for s in client.get("/suppressions", headers=h).json())
    leads = {l["name"]: l for l in client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]}
    assert leads["Good Dental"]["status"] == "do_not_contact"
    # and it can no longer be approved
    d = client.get(f"/campaigns/{cid}/drafts", headers=h).json()[0]
    assert client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True}).status_code == 409


def test_unsubscribe_is_idempotent(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    path = _unsub_path(client, h, cid)
    assert client.post(path).status_code == 200
    assert client.post(path).status_code == 200
    with SessionLocal() as db:
        assert len(db.scalars(select(Suppression).where(Suppression.email == "hello@good.example")).all()) == 1


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_bad_tokens_are_rejected(client, token):
    assert client.post(f"/u/{token}").status_code in (400, 404, 405)
    assert client.get(f"/u/{token}").status_code in (400, 404)


def test_a_login_token_cannot_be_used_to_unsubscribe(client, use_llm):
    h, cid, _ = _setup(client, use_llm)
    login_token = h["Authorization"].split()[1]
    assert client.post(f"/u/{login_token}").status_code == 400


def test_a_forged_unsubscribe_token_is_rejected(client):
    import jwt

    forged = jwt.encode({"typ": "unsub", "ws": 1, "em": "victim@example.com"}, "wrong-secret-wrong-secret-wrong!!", algorithm="HS256")
    assert client.post(f"/u/{forged}").status_code == 400


def test_unsubscribe_cannot_cross_workspaces(client, use_llm):
    """A token is bound to the workspace that issued it."""
    h, cid, _ = _setup(client, use_llm)
    path = _unsub_path(client, h, cid)
    other = register(client, "b@example.com", "B Co")
    client.post(path)
    assert client.get("/suppressions", headers=other).json() == []
