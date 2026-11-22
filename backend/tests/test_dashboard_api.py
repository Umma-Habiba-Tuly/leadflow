"""Endpoints that exist for the dashboard: single campaign, /auth/me, score sorting, pipeline stats."""
from app.main import app
from app.services.llm import get_llm_client
from tests.conftest import make_campaign, register
from tests.test_sending import BODY, MAILBOX, PROFILE, FakeSender, send, world  # noqa: F401  (world is a fixture)
from app.routers.sending import get_sender_factory

CSV = (
    "name,website,email\n"
    "Alpha Dental,https://alpha.example,alpha@a.example\n"
    "Beta Dental,https://beta.example,beta@a.example\n"
    "Gamma Dental,https://gamma.example,gamma@a.example\n"
    "NoEmail Dental,https://noemail.example,\n"
)


class ScoringLLM:
    """Scores by name so ordering is predictable: Beta 95, Alpha 60, Gamma 20, NoEmail 40."""

    SCORES = {"Alpha": 60, "Beta": 95, "Gamma": 20, "NoEmail": 40}

    def generate_json(self, system, prompt, schema):
        if "subject" in schema["properties"]:
            return {"subject": "Quick idea for your clinic", "body": BODY}
        score = next(v for k, v in self.SCORES.items() if f"name: {k}" in prompt)
        return {"score": score, "reason": "stub"}


def setup(client):
    app.dependency_overrides[get_llm_client] = lambda: ScoringLLM()
    h = register(client)
    cid = make_campaign(client, h)
    client.post(f"/campaigns/{cid}/leads/import", headers=h, files={"file": ("l.csv", CSV, "text/csv")})
    return h, cid


def teardown():
    app.dependency_overrides.clear()


# ---------- single campaign ----------


def test_get_single_campaign(client):
    h = register(client)
    cid = client.post("/campaigns", headers=h, json={"name": "Dentists", "niche": "dental clinic", "location": "Austin", "offer": "SEO"}).json()["id"]
    got = client.get(f"/campaigns/{cid}", headers=h).json()
    assert got["id"] == cid and got["name"] == "Dentists" and got["offer"] == "SEO"


def test_single_campaign_is_tenant_isolated_and_authenticated(client):
    h = register(client)
    cid = make_campaign(client, h)
    other = register(client, "b@example.com", "B Co")
    assert client.get(f"/campaigns/{cid}", headers=other).status_code == 404
    assert client.get(f"/campaigns/9999", headers=h).status_code == 404
    assert client.get(f"/campaigns/{cid}").status_code == 401


# ---------- /auth/me ----------


def test_me_reports_identity_and_profile_completeness(client):
    h = register(client, "sam@example.com", "Rivera Web")
    me = client.get("/auth/me", headers=h).json()
    assert me["email"] == "sam@example.com" and me["workspace_name"] == "Rivera Web"
    assert me["profile_complete"] is False and set(me["profile_missing"]) == {"sender_name", "company_name", "postal_address"}
    client.put("/workspace/profile", headers=h, json=PROFILE)
    assert client.get("/auth/me", headers=h).json()["profile_complete"] is True
    assert "password" not in str(client.get("/auth/me", headers=h).json()).lower()


def test_me_requires_a_login(client):
    assert client.get("/auth/me").status_code == 401


# ---------- sorting leads ----------


def test_leads_can_be_listed_best_score_first_with_unscored_last(client):
    h, cid = setup(client)
    try:
        client.post(f"/campaigns/{cid}/score", headers=h, json={"limit": 3})  # NoEmail is left unscored
        by_id = [l["name"] for l in client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]]
        by_score = client.get(f"/campaigns/{cid}/leads?sort=score", headers=h).json()["items"]
        assert by_id == ["Alpha Dental", "Beta Dental", "Gamma Dental", "NoEmail Dental"]  # default unchanged
        assert [l["name"] for l in by_score] == ["Beta Dental", "Alpha Dental", "Gamma Dental", "NoEmail Dental"]
        assert by_score[-1]["score"] is None
        assert client.get(f"/campaigns/{cid}/leads?sort=bogus", headers=h).status_code == 422
    finally:
        teardown()


# ---------- pipeline stats ----------


def stats(client, h, cid):
    return client.get(f"/campaigns/{cid}/stats", headers=h).json()


def test_stats_follow_the_pipeline_step_by_step(client, world):
    h, cid = setup(client)
    app.dependency_overrides[get_sender_factory] = lambda: (lambda mailbox: world)
    try:
        s = stats(client, h, cid)
        assert (s["leads"], s["with_email"], s["scored"], s["drafts"], s["sent"]) == (4, 3, 0, 0, 0)
        assert (s["to_enrich"], s["to_score"], s["to_draft"], s["to_send"]) == (1, 4, 0, 0)  # NoEmail has a site but no email

        client.post(f"/campaigns/{cid}/score", headers=h, json={})
        s = stats(client, h, cid)
        assert (s["scored"], s["to_score"]) == (4, 0)
        assert s["to_draft"] == 2  # Beta 95 and Alpha 60 qualify; Gamma 20 is below 50, NoEmail has no email

        client.put("/workspace/profile", headers=h, json=PROFILE)
        client.post(f"/campaigns/{cid}/drafts/generate", headers=h, json={})
        s = stats(client, h, cid)
        assert (s["drafts"], s["approved"], s["to_draft"], s["to_send"]) == (2, 0, 0, 0)

        for d in client.get(f"/campaigns/{cid}/drafts", headers=h).json():
            client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True})
        assert (stats(client, h, cid)["approved"], stats(client, h, cid)["to_send"]) == (2, 2)

        mb = client.post("/mailboxes", headers=h, json=MAILBOX).json()["id"]
        send(client, h, cid, mb, dry_run=False)
        s = stats(client, h, cid)
        assert (s["sent"], s["to_send"]) == (2, 0)

        client.post("/suppressions", headers=h, json={"email": "gamma@a.example"})
        assert stats(client, h, cid)["opted_out"] == 1
    finally:
        teardown()


def test_stats_are_tenant_isolated_and_count_only_this_campaign(client):
    h, cid = setup(client)
    try:
        second = make_campaign(client, h, name="Other")
        assert stats(client, h, second)["leads"] == 0 and stats(client, h, cid)["leads"] == 4
        other = register(client, "b@example.com", "B Co")
        assert client.get(f"/campaigns/{cid}/stats", headers=other).status_code == 404
        assert client.get(f"/campaigns/{cid}/stats").status_code == 401
    finally:
        teardown()


def test_stats_to_review_and_to_send_match_what_will_really_happen(client, world):
    """to_send must not count approved drafts whose send was refused: they will never go out, and the
    dashboard would say '2 waiting' while Send did nothing. to_review is drafts nobody approved yet."""
    from app.services.email_sender import SendError

    h, cid = setup(client)
    app.dependency_overrides[get_sender_factory] = lambda: (lambda mailbox: world)
    try:
        client.post(f"/campaigns/{cid}/score", headers=h, json={})
        client.put("/workspace/profile", headers=h, json=PROFILE)
        client.post(f"/campaigns/{cid}/drafts/generate", headers=h, json={})
        s = stats(client, h, cid)
        assert (s["drafts"], s["to_review"], s["approved"], s["to_send"]) == (2, 2, 0, 0)

        for d in client.get(f"/campaigns/{cid}/drafts", headers=h).json():
            client.patch(f"/drafts/{d['id']}", headers=h, json={"approved": True})
        s = stats(client, h, cid)
        assert (s["to_review"], s["approved"], s["to_send"]) == (0, 2, 2)

        world.errors["alpha@a.example"] = SendError("recipient", "Recipient refused (550)")  # one address is refused
        mb = client.post("/mailboxes", headers=h, json=MAILBOX).json()["id"]
        send(client, h, cid, mb, dry_run=False)
        s = stats(client, h, cid)
        assert s["sent"] == 1
        assert s["to_send"] == 0, "the refused draft is approved but will never be sent, so it is not 'waiting'"
        assert s["to_review"] == 0
    finally:
        teardown()
