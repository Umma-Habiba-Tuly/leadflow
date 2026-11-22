from tests.conftest import make_campaign, register

CSV = (
    "name,website,email,rating,review_count\n"
    "Bright Smile,https://bright.example,hi@bright.example,4.8,120\n"
    "Oak Dental,https://oak.example,info@oak.example,4.1,35\n"
    "Bright Smile,https://bright.example,hi@bright.example,4.8,120\n"
    ",https://noname.example,x@noname.example,,\n"
)


def upload(client, headers, campaign_id, content=CSV):
    return client.post(
        f"/campaigns/{campaign_id}/leads/import",
        headers=headers,
        files={"file": ("leads.csv", content, "text/csv")},
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_requires_auth(client):
    assert client.get("/campaigns").status_code == 401
    assert client.get("/campaigns", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_register_login_and_duplicate_email(client):
    register(client)
    assert (
        client.post(
            "/auth/register",
            json={"email": "A@example.com", "password": "password123", "workspace_name": "X"},
        ).status_code
        == 409
    )
    ok = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert ok.status_code == 200
    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_csv_import_dedupes_and_skips_invalid(client):
    h = register(client)
    cid = make_campaign(client, h)
    r = upload(client, h, cid)
    assert r.status_code == 200
    assert r.json() == {
        "added": 2,
        "skipped_duplicates": 1,
        "skipped_suppressed": 0,
        "skipped_invalid": 1,
    }
    leads = client.get(f"/campaigns/{cid}/leads", headers=h).json()
    assert leads["total"] == 2

    # Re-importing the same file adds nothing.
    again = upload(client, h, cid).json()
    assert again["added"] == 0


def test_csv_requires_name_column(client):
    h = register(client)
    cid = make_campaign(client, h)
    r = upload(client, h, cid, content="company,email\nFoo,foo@example.com\n")
    assert r.status_code == 400


def test_suppressed_email_is_never_imported(client):
    h = register(client)
    cid = make_campaign(client, h)
    client.post("/suppressions", headers=h, json={"email": "HI@bright.example"})
    r = upload(client, h, cid).json()
    assert r["skipped_suppressed"] == 2  # both copies of the suppressed row
    assert r["added"] == 1


def test_suppression_marks_existing_leads(client):
    h = register(client)
    cid = make_campaign(client, h)
    upload(client, h, cid)
    client.post("/suppressions", headers=h, json={"email": "info@oak.example"})
    items = client.get(f"/campaigns/{cid}/leads", headers=h).json()["items"]
    status = {i["name"]: i["status"] for i in items}
    assert status["Oak Dental"] == "do_not_contact"
    assert status["Bright Smile"] == "new"


def test_tenant_isolation(client):
    a = register(client, "a@example.com", "A Co")
    b = register(client, "b@example.com", "B Co")
    cid = make_campaign(client, a)
    upload(client, a, cid)

    assert client.get(f"/campaigns/{cid}/leads", headers=b).status_code == 404
    assert upload(client, b, cid).status_code == 404
    assert client.post(f"/campaigns/{cid}/search", headers=b, json={}).status_code == 404
    assert client.get("/campaigns", headers=b).json() == []

    # Suppression lists are per workspace too.
    client.post("/suppressions", headers=a, json={"email": "x@example.com"})
    assert client.get("/suppressions", headers=b).json() == []


def test_search_without_api_key_returns_503(client):
    h = register(client)
    cid = make_campaign(client, h)
    r = client.post(f"/campaigns/{cid}/search", headers=h, json={"max_results": 5})
    assert r.status_code == 503
