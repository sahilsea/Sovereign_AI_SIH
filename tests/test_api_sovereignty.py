"""API tests for /sovereignty, /workspace and /models.

Verifies:
1. The live network monitor endpoint requires a session and reports the
   guard as blocking once the app has started.
2. The guard probe (admin-only) is blocked without sending a packet.
3. Workspace downloads are owner-scoped and re-check the file's inherited
   classification against the reader's current clearance.
4. /models reports a per-task selection.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from auth.users import create_user
from contracts import Compartment, Label, Tier
from harness import workspace
from ingest.seed import seed_initial_admin


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db = str(tmp_path / "sov.db")
    monkeypatch.setenv("SEVERANCE_DB_PATH", db)
    monkeypatch.setenv("SEVERANCE_ADMIN_ID", "admin-root")
    monkeypatch.setenv("SEVERANCE_ADMIN_PASSWORD", "RootAdmin123!")
    monkeypatch.setenv("AGENT_BACKEND", "mock")
    monkeypatch.setenv("SEVERANCE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("SEVERANCE_EGRESS_GUARD", "block")
    seed_initial_admin(db)
    create_user(db_path=db, actor_id="admin-root", person_id="eng-001", name="Engineer",
                job_title="Engineer", grade="E", password="EngPassword123!", must_change_password=False)
    with TestClient(app) as c:
        yield c


def _login(c, pid, pw):
    assert c.post("/auth/login", json={"person_id": pid, "password": pw}).status_code == 200


def test_network_monitor_requires_login_and_reports_guard(client):
    assert client.get("/sovereignty/network").status_code == 401
    _login(client, "eng-001", "EngPassword123!")
    body = client.get("/sovereignty/network").json()
    assert body["guard"]["mode"] == "block"
    assert body["monitor"]["running"] is True
    assert "external_connections" in body["monitor"]


def test_guard_probe_is_admin_only_and_blocked(client):
    _login(client, "eng-001", "EngPassword123!")
    assert client.post("/sovereignty/network/probe").status_code == 403
    _login(client, "admin-root", "RootAdmin123!")
    res = client.post("/sovereignty/network/probe")
    assert res.status_code == 200
    assert res.json()["blocked"] is True


def test_workspace_download_rechecks_classification(client):
    _login(client, "eng-001", "EngPassword123!")
    workspace.write_bytes("eng-001", "open.txt", b"hello")
    workspace.write_bytes("eng-001", "vig.txt", b"secret",
                          label=Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.VIGILANCE])))

    names = {f["name"] for f in client.get("/workspace/files").json()}
    assert names == {"open.txt", "vig.txt"}
    assert client.get("/workspace/files/open.txt").content == b"hello"
    # eng-001 holds no vigilance compartment, so a file derived from it is refused.
    assert client.get("/workspace/files/vig.txt").status_code == 403
    assert client.get("/workspace/files/missing.txt").status_code == 404


def test_models_endpoint_reports_task_selection(client):
    _login(client, "eng-001", "EngPassword123!")
    body = client.get("/models").json()
    assert set(body["selection"]) >= {"document", "code", "vision", "planning"}
    assert all("roles" in m and "status" in m for m in body["models"])
