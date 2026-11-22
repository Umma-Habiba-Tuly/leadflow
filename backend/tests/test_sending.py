from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.db.models import Mailbox, SentEmail, Suppression
from app.db.session import SessionLocal
from app.main import app
from app.routers.sending import get_sender_factory
from app.services import compliance, sending
from app.services.email_sender import SendError
from app.services.llm import get_llm_client
from tests.conftest import make_campaign, register

BODY = (
    "Hi team, I noticed you have a lot of happy patients. I help local clinics get more "
    "new-patient bookings with a faster, mobile-friendly website. Would it be useful if I sent "
    "over two quick ideas for yours?"
)
PROFILE = {"sender_name": "Sam Rivera", "company_name": "Rivera Web Studio", "postal_address": "100 Congress Ave, Austin, TX 78701"}
PASSWORD = "app-pass-123"
MAILBOX = {
    "from_email": "sam@rivera.example", "from_name": "Sam Rivera", "smtp_host": "8.8.8.8", "smtp_port": 587,
    "smtp_username": "sam@rivera.example", "smtp_password": PASSWORD, "security": "starttls", "daily_limit": 30,
}
CSV = (
    "name,website,email\n"
    "Alpha Dental,https://alpha.example,alpha@a.example\n"
    "Beta Dental,https://beta.example,beta@a.example\n"
    "Gamma Dental,https://gamma.example,gamma@a.example\n"
)


class FakeLLM:
    def generate_json(self, system, prompt, schema):
        if "subject" in schema["properties"]:
            return {"subject": "Quick idea for your clinic", "body": BODY}
        return {"score": 80, "reason": "Good fit."}


class FakeSender:
    """Records what would have been sent. `errors[email]` makes that recipient fail."""

    def __init__(self):
        self.sent, self.errors, self.check_error = [], {}, None

    def send(self, msg):
        if msg.to_email in self.errors:
            raise self.errors[msg.to_email]
        self.sent.append(msg)
        return f"<id-{len(self.sent)}@fake.test>"

    def check(self):
        if self.check_error:
            raise self.check_error

    @property
    def recipients(self):
        return [m.to_email for m in self.sent]


@pytest.fixture()
def world(client):
    sender = FakeSender()
    app.dependency_overrides[get_llm_client] = lambda: FakeLLM()
    app.dependency_overrides[get_sender_factory] = lambda: (lambda mailbox: sender)
    yield sender
    app.dependency_overrides.clear()


def ready(client, approve=3):
    """A workspace with a complete profile, 3 scored leads with drafts, `approve` of them approved,
    and a connected mailbox."""
    h = register(client)
    client.put("/workspace/profile", headers=h, json=PROFILE)
    cid = make_campaign(client, h)
    client.post(f"/campaigns/{cid}/leads/import", headers=h, files={"file": ("l.csv", CSV, "text/csv")})
    client.post(f"/campaigns/{cid}/score", headers=h, json={})
    client.post(f"/campaigns/{cid}/drafts/generate", headers=h, json={})
    for d in client.get(f"/campaigns/{cid}/drafts", headers=h).json()[:approve]:
        assert client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True}).status_code == 200
    mb = client.post("/mailboxes", headers=h, json=MAILBOX)
    assert mb.status_code == 201, mb.text
    return h, cid, mb.json()["id"]


def send(client, h, cid, mailbox_id, **kw):
    return client.post(f"/campaigns/{cid}/send", headers=h, json={"mailbox_id": mailbox_id, **kw})


def real(client, h, cid, mb, **kw):
    return send(client, h, cid, mb, dry_run=False, **kw).json()


def sent_rows(client, h, cid):
    return client.get(f"/campaigns/{cid}/sent", headers=h).json()


def lead_status(client, h, cid):
    return {l["name"]: l["status"] for l in client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]}


# ---------- the safety default ----------


def test_sending_is_a_dry_run_unless_you_say_otherwise(client, world):
    h, cid, mb = ready(client)
    r = send(client, h, cid, mb)  # note: no dry_run field at all
    body = r.json()
    assert r.status_code == 200 and body["dry_run"] is True and body["sent"] == 0
    assert [w["to_email"] for w in body["would_send"]] == ["alpha@a.example", "beta@a.example", "gamma@a.example"]
    assert world.sent == [] and sent_rows(client, h, cid) == []
    with SessionLocal() as db:
        assert db.scalars(select(SentEmail)).all() == []  # a preview must not even claim drafts


def test_real_send_delivers_and_records_everything(client, world):
    h, cid, mb = ready(client)
    r = real(client, h, cid, mb)
    assert r["sent"] == 3 and r["rejected"] == 0 and r["stopped_reason"] is None
    assert world.recipients == ["alpha@a.example", "beta@a.example", "gamma@a.example"]
    rows = sent_rows(client, h, cid)
    assert [x["status"] for x in rows] == ["sent"] * 3 and all(x["message_id"] for x in rows)
    assert set(lead_status(client, h, cid).values()) == {"contacted"}
    assert {d["status"] for d in client.get(f"/campaigns/{cid}/drafts", headers=h).json()} == {"sent"}
    assert client.get("/mailboxes", headers=h).json()[0]["sent_today"] == 3


def test_every_email_carries_identity_footer_and_a_working_unsubscribe(client, world):
    h, cid, mb = ready(client)
    real(client, h, cid, mb, limit=1)
    m = world.sent[0]
    assert m.from_email == "sam@rivera.example" and m.from_name == "Sam Rivera"
    assert "100 Congress Ave, Austin, TX 78701" in m.text_body and "Unsubscribe here: http" in m.text_body
    assert m.unsubscribe_url in m.text_body
    ws_id, email = compliance.read_unsubscribe_token(m.unsubscribe_url.rsplit("/u/", 1)[1])
    assert email == m.to_email  # the link opts out exactly this recipient


# ---------- only what was approved, only once ----------


def test_unapproved_drafts_are_never_sent(client, world):
    h, cid, mb = ready(client, approve=1)
    assert real(client, h, cid, mb)["sent"] == 1
    assert world.recipients == ["alpha@a.example"]


def test_the_same_draft_is_never_sent_twice(client, world):
    h, cid, mb = ready(client)
    real(client, h, cid, mb)
    assert real(client, h, cid, mb)["sent"] == 0
    assert len(world.sent) == 3


def test_a_stuck_in_flight_claim_is_never_retried_automatically(client, world):
    """If the server died mid-send we can't know whether the email went out. A missed lead is
    better than emailing a prospect twice, so these wait for a human."""
    h, cid, mb = ready(client)
    alpha = client.get(f"/campaigns/{cid}/drafts", headers=h).json()[0]
    with SessionLocal() as db:
        db.add(SentEmail(workspace_id=1, draft_id=alpha["id"], lead_id=alpha["lead_id"], mailbox_id=mb,
                         to_email=alpha["to_email"], subject="x", status="sending"))
        db.commit()
    r = real(client, h, cid, mb)
    assert r["sent"] == 2 and "alpha@a.example" not in world.recipients


def test_database_itself_refuses_a_second_send_record_for_one_draft(client, world):
    h, cid, mb = ready(client)
    real(client, h, cid, mb, limit=1)
    row = sent_rows(client, h, cid)[0]
    with SessionLocal() as db:
        db.add(SentEmail(workspace_id=1, draft_id=row["draft_id"], lead_id=1, mailbox_id=mb, to_email="x@a.example", subject="s", status="sent"))
        with pytest.raises(IntegrityError):
            db.commit()


# ---------- volume limits ----------


def test_daily_limit_is_enforced(client, world):
    h, cid, mb = ready(client)
    client.patch(f"/mailboxes/{mb}", headers=h, json={"daily_limit": 2})
    first = real(client, h, cid, mb)
    assert first["sent"] == 2 and first["quota_remaining"] == 0
    second = real(client, h, cid, mb)
    assert second["sent"] == 0 and "daily limit" in second["stopped_reason"]
    assert len(world.sent) == 2


def test_yesterdays_sends_do_not_use_up_todays_quota(client, world):
    h, cid, mb = ready(client)
    client.patch(f"/mailboxes/{mb}", headers=h, json={"daily_limit": 1})
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    with SessionLocal() as db:
        db.add(SentEmail(workspace_id=1, draft_id=9001, lead_id=9001, mailbox_id=mb, to_email="old@a.example",
                         subject="s", status="sent", created_at=yesterday))
        db.commit()
    assert real(client, h, cid, mb)["sent"] == 1


def test_per_request_limit(client, world):
    h, cid, mb = ready(client)
    assert real(client, h, cid, mb, limit=1)["sent"] == 1
    assert send(client, h, cid, mb, limit=21).status_code == 422  # cannot ask for more than 20 at once


# ---------- people who opt out ----------


def test_someone_who_unsubscribed_after_approval_is_not_emailed(client, world):
    h, cid, mb = ready(client)
    # Assert the setup step itself worked, so a failed setup can't masquerade as a product bug.
    assert client.post("/suppressions", headers=h, json={"email": "alpha@a.example"}).status_code == 201
    real(client, h, cid, mb)
    assert "alpha@a.example" not in world.recipients and len(world.sent) == 2


def test_optout_list_is_rechecked_at_the_last_moment(client, world):
    """Even if a lead's own status wasn't updated, the suppression list itself blocks the send."""
    h, cid, mb = ready(client)
    with SessionLocal() as db:
        db.add(Suppression(workspace_id=1, email="beta@a.example", reason="unsubscribed"))
        db.commit()
    r = real(client, h, cid, mb)
    assert r["skipped_opted_out"] == 1 and r["sent"] == 2 and "beta@a.example" not in world.recipients


# ---------- when delivery goes wrong ----------


def test_a_refused_address_is_recorded_suppressed_and_never_retried(client, world):
    h, cid, mb = ready(client)
    world.errors["beta@a.example"] = SendError("recipient", "Recipient refused (550)")
    r = real(client, h, cid, mb)
    assert r["sent"] == 2 and r["rejected"] == 1  # one bad address does not stop the rest
    assert [x["status"] for x in sent_rows(client, h, cid)] == ["sent", "rejected", "sent"]
    assert any(s["email"] == "beta@a.example" and s["reason"] == "hard_bounce" for s in client.get("/suppressions", headers=h).json())
    assert lead_status(client, h, cid)["Beta Dental"] == "do_not_contact"
    world.errors.clear()
    assert real(client, h, cid, mb)["sent"] == 0  # not retried
    assert client.get("/mailboxes", headers=h).json()[0]["status"] == "active"  # one miss is not a pattern


def test_a_network_error_stops_the_run_and_the_rest_can_be_retried(client, world):
    h, cid, mb = ready(client)
    world.errors["beta@a.example"] = SendError("transient", "Could not complete SMTP exchange")
    r = real(client, h, cid, mb)
    assert r["sent"] == 1 and r["stopped_reason"].startswith("transient")
    assert world.recipients == ["alpha@a.example"]  # gamma was not attempted after the failure
    assert [x["to_email"] for x in sent_rows(client, h, cid)] == ["alpha@a.example"]  # claim released

    world.errors.clear()
    assert real(client, h, cid, mb)["sent"] == 2  # beta and gamma go out now


def test_a_mailbox_login_problem_stops_everything_without_burning_leads(client, world):
    h, cid, mb = ready(client)
    world.errors["alpha@a.example"] = SendError("config", "Mailbox login/sender problem")
    r = real(client, h, cid, mb)
    assert r["sent"] == 0 and r["stopped_reason"].startswith("config")
    assert sent_rows(client, h, cid) == []
    assert set(lead_status(client, h, cid).values()) == {"new"}  # nobody was marked contacted


def _history(mb, sent, rejected):
    with SessionLocal() as db:
        for i in range(sent + rejected):
            db.add(SentEmail(workspace_id=1, draft_id=9100 + i, lead_id=9100 + i, mailbox_id=mb, to_email=f"h{i}@a.example",
                             subject="s", status="sent" if i < sent else "rejected"))
        db.commit()


def test_mailbox_pauses_itself_when_too_many_addresses_bounce(client, world):
    h, cid, mb = ready(client)
    _history(mb, sent=9, rejected=1)  # already 10% refused over 10 attempts
    world.errors["beta@a.example"] = SendError("recipient", "Recipient refused (550)")
    r = real(client, h, cid, mb)
    assert r["mailbox_paused"] is True and "paused" in r["stopped_reason"]
    assert world.recipients == ["alpha@a.example"]  # gamma was never attempted
    box = client.get("/mailboxes", headers=h).json()[0]
    assert box["status"] == "paused" and box["paused_reason"]

    assert send(client, h, cid, mb, dry_run=False).status_code == 409  # stays paused until a human acts
    world.errors.clear()
    assert client.patch(f"/mailboxes/{mb}", headers=h, json={"status": "active"}).json()["paused_reason"] is None
    assert real(client, h, cid, mb)["sent"] == 1  # gamma


def test_pause_rule_needs_enough_data_to_mean_something(client, world):
    h, cid, mb = ready(client)
    _history(mb, sent=2, rejected=1)  # 33% but only 3 attempts
    with SessionLocal() as db:
        assert sending._should_pause(db, db.get(Mailbox, mb)) is False
    _history(mb, sent=0, rejected=0)


# ---------- preconditions ----------


def test_cannot_send_without_a_complete_sender_profile(client, world):
    h, cid, mb = ready(client)
    client.put("/workspace/profile", headers=h, json={**PROFILE, "postal_address": ""})
    r = send(client, h, cid, mb, dry_run=False)
    assert r.status_code == 400 and "postal_address" in r.json()["detail"] and world.sent == []


def test_a_paused_mailbox_cannot_send(client, world):
    h, cid, mb = ready(client)
    client.patch(f"/mailboxes/{mb}", headers=h, json={"status": "paused"})
    assert send(client, h, cid, mb, dry_run=False).status_code == 409


def test_check_mailbox_reports_success_and_failure(client, world):
    h, cid, mb = ready(client)
    assert client.post(f"/mailboxes/{mb}/check", headers=h).json() == {"ok": True}
    world.check_error = SendError("config", "login rejected")
    r = client.post(f"/mailboxes/{mb}/check", headers=h)
    assert r.status_code == 502 and "config" in r.json()["detail"]


# ---------- one client can never touch another's mailbox or sends ----------


def test_tenants_are_isolated(client, world):
    h, cid, mb = ready(client)
    other = register(client, "b@example.com", "B Co")
    client.put("/workspace/profile", headers=other, json=PROFILE)
    assert send(client, other, cid, mb, dry_run=False).status_code == 404  # not their campaign
    other_cid = make_campaign(client, other)
    assert send(client, other, other_cid, mb, dry_run=False).status_code == 404  # not their mailbox
    assert client.patch(f"/mailboxes/{mb}", headers=other, json={"daily_limit": 1}).status_code == 404
    assert client.post(f"/mailboxes/{mb}/check", headers=other).status_code == 404
    assert client.get("/mailboxes", headers=other).json() == []
    assert client.get(f"/campaigns/{cid}/sent", headers=other).status_code == 404
    assert world.sent == []


# ---------- mailbox API: secrets and the SSRF guard ----------


def test_password_is_encrypted_at_rest_and_never_returned(client, world):
    h, cid, mb = ready(client)
    for resp in (client.get("/mailboxes", headers=h), client.patch(f"/mailboxes/{mb}", headers=h, json={"daily_limit": 5})):
        assert PASSWORD not in resp.text and "password" not in resp.text.lower()
    with SessionLocal() as db:
        stored = db.get(Mailbox, mb).smtp_password_enc
    assert PASSWORD not in stored and decrypt_secret(stored) == PASSWORD


def test_changing_the_password_re_encrypts_it(client, world):
    h, cid, mb = ready(client)
    client.patch(f"/mailboxes/{mb}", headers=h, json={"smtp_password": "new-pass-456"})
    with SessionLocal() as db:
        assert decrypt_secret(db.get(Mailbox, mb).smtp_password_enc) == "new-pass-456"


def test_same_mailbox_cannot_be_connected_twice(client, world):
    h, cid, mb = ready(client)
    assert client.post("/mailboxes", headers=h, json=MAILBOX).status_code == 409


@pytest.mark.parametrize(
    "override",
    [
        {"smtp_host": "127.0.0.1"},  # the server's own machine
        {"smtp_host": "localhost"},
        {"smtp_host": "169.254.169.254"},  # cloud metadata
        {"smtp_host": "10.0.0.5"},  # internal network
        {"smtp_port": 22},  # not a mail port (would let a client probe SSH)
        {"smtp_port": 5432},
        {"security": "none"},  # unencrypted
        {"smtp_host": "this-host-does-not-exist.invalid"},
    ],
)
def test_ssrf_attempts_are_rejected(client, world, override):
    h = register(client)
    r = client.post("/mailboxes", headers=h, json={**MAILBOX, **override})
    assert r.status_code == 422, r.text


def test_local_servers_are_allowed_only_with_the_dev_switch(client, world, monkeypatch):
    h = register(client)
    local = {**MAILBOX, "smtp_host": "127.0.0.1", "smtp_port": 1025, "security": "none"}
    assert client.post("/mailboxes", headers=h, json=local).status_code == 422
    monkeypatch.setattr(settings, "allow_private_smtp", True)
    assert client.post("/mailboxes", headers=h, json=local).status_code == 201


@pytest.mark.parametrize(
    "override",
    [
        {"daily_limit": 0}, {"daily_limit": 201}, {"from_name": "Sam\r\nBcc: x@a.example"},
        {"smtp_username": "u\nX: y"}, {"smtp_password": ""}, {"from_email": "not-an-email"},
        {"smtp_port": 0}, {"smtp_port": 70000}, {"security": "plaintext"},
    ],
)
def test_invalid_mailbox_input_is_rejected(client, world, override):
    h = register(client)
    assert client.post("/mailboxes", headers=h, json={**MAILBOX, **override}).status_code == 422


def test_missing_encryption_key_refuses_to_store_passwords(client, world, monkeypatch):
    h = register(client)
    monkeypatch.setattr(settings, "encryption_key", "")
    assert client.post("/mailboxes", headers=h, json=MAILBOX).status_code == 503


def test_host_is_rechecked_at_send_time(client, world, monkeypatch):
    """DNS can change after a mailbox is saved. A host that now resolves privately must not be used."""
    h, cid, mb = ready(client)
    with SessionLocal() as db:
        box = db.get(Mailbox, mb)
        box.smtp_host = "127.0.0.1"
        db.commit()
    assert send(client, h, cid, mb, dry_run=False).status_code == 422
    assert world.sent == []
