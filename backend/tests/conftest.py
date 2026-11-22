import os
import tempfile

# Must be set before the app is imported so it binds to a throwaway database.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
from cryptography.fernet import Fernet  # noqa: E402

os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

# Make the suite hermetic. Real environment variables beat the developer's .env file, so pin
# every setting a test could depend on. Without this, a dev-only switch such as
# ALLOW_PRIVATE_SMTP=true in .env silently turned the SSRF tests off, and real API keys in .env
# were visible to tests that should only ever use fakes.
os.environ["ALLOW_PRIVATE_SMTP"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_PLACES_API_KEY"] = ""
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def register(client, email="a@example.com", workspace="Acme"):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "workspace_name": workspace},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_campaign(client, headers, name="Dentists"):
    r = client.post(
        "/campaigns",
        headers=headers,
        json={"name": name, "niche": "dental clinic", "location": "Austin, TX"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]
