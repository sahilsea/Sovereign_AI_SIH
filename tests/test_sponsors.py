"""Unit tests for auth/sponsors.py.

Verifies:
1. An admin CANNOT grant compartments -- there is no admin path at all.
6. Separation of duties: no delegation, no admin sponsors, no one sponsoring
   two compartments, no grants to admins, no admin reset of sponsor passwords.
2. A sponsor CANNOT grant a compartment they do not own.
3. Nobody can grant a compartment to themselves.
4. A valid sponsor grant succeeds and writes an immutable ledger entry.
5. Missing sponsor account declared in config fails loudly at startup.
"""

import json
from pathlib import Path
import pytest
from contracts import Compartment
import auth.sponsors as sponsors_module
from auth.sponsors import (
    assert_separation_of_duties,
    get_sponsored_compartments,
    grant_compartment,
    revoke_compartment,
    verify_sponsors,
)
from auth.users import create_user, get_principal, reset_password
from trust.ledger import read as ledger_read


@pytest.fixture
def test_setup(tmp_path: Path):
    """Set up a test database with an admin, two sponsors, and a regular user."""
    db_path = str(tmp_path / "sponsor_test.db")
    config_path = tmp_path / "test_compartments.json"

    # Config with CVO and Safety sponsors
    config_data = {
        "vigilance": {"sponsor": "cvo-001", "description": "Chief Vigilance Officer"},
        "hse": {"sponsor": "safety-001", "description": "Head of Safety"},
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # Create users
    create_user(db_path, "boot", "admin-01", "Admin One", "HR Admin", "E", is_admin=True)
    create_user(db_path, "admin-01", "cvo-001", "CVO Officer", "CVO", "G")
    create_user(db_path, "admin-01", "safety-001", "Safety Chief", "Safety Head", "F")
    create_user(db_path, "admin-01", "emp-001", "Process Eng", "Engineer", "B")

    return db_path, config_path


def test_admin_cannot_grant_compartment(test_setup):
    """An administrator CANNOT use the sponsor grant path."""
    db_path, config_path = test_setup

    with pytest.raises(PermissionError, match="does not sponsor compartment"):
        grant_compartment(
            db_path=db_path,
            actor_id="admin-01",
            target_id="emp-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_sponsor_cannot_grant_unowned_compartment(test_setup):
    """A sponsor cannot grant a compartment belonging to another officer."""
    db_path, config_path = test_setup

    # Safety chief attempts to grant vigilance -> REJECTED
    with pytest.raises(PermissionError, match="does not sponsor compartment 'vigilance'"):
        grant_compartment(
            db_path=db_path,
            actor_id="safety-001",
            target_id="emp-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_self_grant_prohibited(test_setup):
    """A sponsor CANNOT grant a compartment to themselves."""
    db_path, config_path = test_setup

    with pytest.raises(PermissionError, match="Self-grant violation blocked"):
        grant_compartment(
            db_path=db_path,
            actor_id="cvo-001",
            target_id="cvo-001",
            compartment=Compartment.VIGILANCE,
            config_path=config_path,
        )


def test_valid_sponsor_grant_and_ledger(test_setup):
    """A valid grant by the designated sponsor updates clearances and writes to ledger."""
    db_path, config_path = test_setup

    grant_compartment(
        db_path=db_path,
        actor_id="cvo-001",
        target_id="emp-001",
        compartment=Compartment.VIGILANCE,
        config_path=config_path,
    )

    p = get_principal(db_path, "emp-001")
    assert p is not None
    assert Compartment.VIGILANCE in p.compartments

    # Verify ledger entry
    entries = ledger_read(db_path, limit=5)
    grant_entry = next(e for e in entries if e.action == "GRANT_COMPARTMENT")
    assert grant_entry.actor == "cvo-001"
    assert grant_entry.details["subject"] == "emp-001"
    assert grant_entry.details["compartment"] == "vigilance"


def test_missing_sponsor_fails_loudly_at_startup(tmp_path: Path):
    """If config/compartments.json names a sponsor who does not exist, fail loudly."""
    db_path = str(tmp_path / "startup_check.db")
    config_path = tmp_path / "bad_config.json"

    # Declare sponsor who has not been provisioned
    config_data = {
        "legal": {"sponsor": "legal-missing-001", "description": "Legal Advisor"}
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f)

    # No users exist in db
    with pytest.raises(RuntimeError, match="FATAL STARTUP CHECK FAILED.*legal-missing-001"):
        verify_sponsors(db_path=db_path, config_path=config_path)


def test_no_admin_override_or_delegation_exists():
    assert not hasattr(sponsors_module, "admin_set_compartments")
    assert not hasattr(sponsors_module, "delegate_sponsor")
    assert not hasattr(sponsors_module, "is_sponsor_or_delegate")


def test_sponsor_authority_is_exactly_one_compartment(test_setup):
    db_path, config_path = test_setup
    assert get_sponsored_compartments(db_path, "cvo-001", config_path) == [Compartment.VIGILANCE]
    assert get_sponsored_compartments(db_path, "admin-01", config_path) == []
    with pytest.raises(PermissionError, match="does not sponsor"):
        grant_compartment(db_path, "cvo-001", "emp-001", Compartment.HSE, config_path)


def test_sponsor_cannot_grant_to_an_administrator(test_setup):
    db_path, config_path = test_setup
    with pytest.raises(PermissionError, match="administrator"):
        grant_compartment(db_path, "cvo-001", "admin-01", Compartment.VIGILANCE, config_path)
    assert get_principal(db_path, "admin-01").compartments == frozenset()


def test_one_person_cannot_sponsor_two_compartments():
    with pytest.raises(RuntimeError, match="Separation of duties"):
        assert_separation_of_duties({
            "hse": {"sponsor": "boss-1"}, "vigilance": {"sponsor": "boss-1"},
        })


def test_admin_account_cannot_be_a_sponsor(tmp_path: Path):
    db_path = str(tmp_path / "s.db")
    config_path = tmp_path / "c.json"
    config_path.write_text(json.dumps({"hse": {"sponsor": "admin-01", "description": "x"}}))
    create_user(db_path, "boot", "admin-01", "Admin", "Admin", "E", is_admin=True)
    with pytest.raises(RuntimeError, match="ADMINISTRATOR"):
        verify_sponsors(db_path=db_path, config_path=config_path)


def test_admin_cannot_reset_a_sponsor_password(test_setup, monkeypatch):
    db_path, config_path = test_setup
    monkeypatch.setattr(sponsors_module, "DEFAULT_CONFIG_PATH", config_path)
    with pytest.raises(PermissionError, match="compartment sponsor"):
        reset_password(db_path, "admin-01", "cvo-001")
    assert reset_password(db_path, "admin-01", "emp-001").startswith("temp-")  # ordinary accounts: fine


def test_sponsor_reads_own_compartment_but_no_other(test_setup, monkeypatch):
    db_path, config_path = test_setup
    monkeypatch.setattr(sponsors_module, "DEFAULT_CONFIG_PATH", config_path)
    assert get_principal(db_path, "safety-001").compartments == frozenset({Compartment.HSE})
    assert get_principal(db_path, "cvo-001").compartments == frozenset({Compartment.VIGILANCE})
    assert get_principal(db_path, "admin-01").compartments == frozenset()
    # Derived from config, not stored: nothing to revoke, nothing self-granted.
    from auth.users import list_users
    rows = {u.person_id: u for u in list_users(db_path)}
    assert rows["safety-001"].sponsor_of == [Compartment.HSE]
