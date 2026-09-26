"""Tests for answer outcomes, verification notes and source-page access.

Verifies:
1. Restricted vs unavailable vs sourced outcomes are decided deterministically.
2. The verification note for a sourced answer says only the quotes were checked.
3. Reports no longer call the whole synthesis "verified".
4. /documents/{id}/file serves a PDF only to cleared users.
"""

import io
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from agents.mock import MockAgent
from api.main import app
from auth.users import create_user
from contracts import AskRequest, AskResponse, Citation, Compartment, Label, Passage, Principal, Tier
from deliver.docx import build_report
from harness.runner import run_query
from ingest.seed import seed_initial_admin
from trust.conversations import init_conversations_table
from trust.ledger import init_ledger_table
from trust.reports import init_reports_table

SECRET_TEXT = "The vigilance inquiry found three bids submitted from identical IP addresses last quarter."


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "o.db")
    for init in (init_ledger_table, init_reports_table, init_conversations_table):
        init(path)
    return path


def _principal(**kw):
    base = dict(person_id="p1", name="P", job_title="Officer", grade="A", compartments=frozenset())
    base.update(kw)
    return Principal(**base)


def test_denied_match_is_restricted_not_unavailable(db):
    corpus = [Passage(doc_id="vig", page=1, title="Vigilance", text=SECRET_TEXT,
                      label=Label(tier=Tier.CONFIDENTIAL, compartments=frozenset([Compartment.VIGILANCE])))]
    res = run_query(AskRequest(question="identical IP addresses bids"), corpus, _principal(), MockAgent(), db)
    assert res.outcome == "restricted"
    assert "not cleared" in res.verification_note
    assert SECRET_TEXT not in res.answer + res.verification_note


def test_no_match_is_unavailable(db):
    corpus = [Passage(doc_id="rti", page=1, text="MRPL is a Schedule A Miniratna enterprise.", label=Label(tier=Tier.PUBLIC))]
    res = run_query(AskRequest(question="zebra migration patterns"), corpus, _principal(), MockAgent(), db)
    assert res.outcome == "unavailable"


def test_sourced_note_says_only_quotes_were_checked():
    res = AskResponse(status="answered", answer="Summary.", effective_label=Label(tier=Tier.PUBLIC),
                      citations=[Citation(doc_id="d", page=1, quote="five words or more are quoted here")])
    assert res.outcome == "sourced"
    assert "not itself verified" in res.verification_note


def test_report_does_not_claim_whole_answer_verified():
    res = AskResponse(status="answered", answer="Summary.", effective_label=Label(tier=Tier.PUBLIC),
                      citations=[Citation(doc_id="d", page=1, quote="five words or more are quoted here")])
    doc = Document(io.BytesIO(build_report(res, question="q")))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Verified Synthesized Findings" not in text
    assert "not itself verified" in text


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    path = str(tmp_path / "doc.db")
    monkeypatch.setenv("SEVERANCE_DB_PATH", path)
    monkeypatch.setenv("SEVERANCE_ADMIN_ID", "admin-root")
    monkeypatch.setenv("SEVERANCE_ADMIN_PASSWORD", "RootAdmin123!")
    monkeypatch.setenv("AGENT_BACKEND", "mock")
    seed_initial_admin(path)
    create_user(db_path=path, actor_id="admin-root", person_id="staff-001", name="Staff", job_title="Officer",
                grade="A", password="StaffPassword123!", must_change_password=False)
    with TestClient(app) as c:
        assert c.post("/auth/login", json={"person_id": "staff-001", "password": "StaffPassword123!"}).status_code == 200
        yield c


def test_document_file_respects_clearance(client):
    public = client.get("/documents/mrpl-rti-manual-sec4/file")
    assert public.status_code == 200 and public.content[:4] == b"%PDF"
    assert client.get("/documents/mrpl-vig-proc-2025/file").status_code == 403
    assert client.get("/documents/no-such-doc/file").status_code == 404
