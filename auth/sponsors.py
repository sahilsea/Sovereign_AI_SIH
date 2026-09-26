"""Compartment ownership and sponsor authority.

NON-NEGOTIABLE DESIGN PRINCIPLES (separation of duties):
1. Exactly ONE path to a compartment: its designated sponsor grants or
   revokes it (grant_compartment / revoke_compartment below). There is no
   administrator override and no delegation -- sponsorship is personal and
   non-delegable.
2. Administrators manage ACCOUNTS (create employees, reset passwords); they
   hold no compartment authority at all, and cannot create or reset the
   password of a sponsor account through the application (see auth/users.py),
   which would otherwise let them log in AS a sponsor.
3. Ownership is declared in config/compartments.json, checked in and signed off once.
4. One person sponsors at most ONE compartment, and no sponsor may be an
   administrator: no single account ever holds more than one authority.
5. A sponsor holds READ access to the compartment they sponsor (derived from
   config, never stored as a grant). Owning one compartment gives ZERO
   authority over, or access to, other compartments.
6. NOBODY can grant compartments to themselves.
7. Every grant/revoke action writes an immutable audit ledger entry.
8. Startup check: a missing, deactivated, duplicated or admin sponsor fails
   loudly with a specific error.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional
from contracts import Compartment
from trust.ledger import get_db_connection, log as ledger_log

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "compartments.json"


def load_compartment_config(config_path: Optional[str | Path] = None) -> dict[str, dict[str, str]]:
    """Load and parse the declarative compartment sponsor configuration."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Compartment configuration file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate that every declared compartment is a valid Compartment enum
    validated = {}
    for comp_name, info in data.items():
        comp_enum = Compartment(comp_name)
        validated[comp_enum.value] = info
    return validated


def init_grants_tables(db_path: str) -> None:
    """Initialize compartment audit and delegation tables."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compartment_grants (
                    grant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compartment TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compartment_delegates (
                    compartment TEXT NOT NULL,
                    delegate_id TEXT NOT NULL,
                    assigned_by TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (compartment, delegate_id)
                );
                """
            )
    finally:
        conn.close()


def verify_sponsors(db_path: str, config_path: Optional[str | Path] = None) -> None:
    """Validate that every declared sponsor account exists in the user store.

    CRITICAL RULE: If config/compartments.json names a sponsor whose account does
    not exist, FAIL LOUDLY AT STARTUP.
    """
    from auth.users import init_users_table
    init_users_table(db_path)
    config = load_compartment_config(config_path)
    assert_separation_of_duties(config)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        for comp_name, info in config.items():
            sponsor_id = info.get("sponsor")
            if not sponsor_id:
                raise RuntimeError(
                    f"Configuration error: Compartment '{comp_name}' has no sponsor ID specified."
                )

            cursor.execute(
                "SELECT person_id, is_active, is_admin FROM users WHERE person_id = ?;",
                (sponsor_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(
                    f"FATAL STARTUP CHECK FAILED: Compartment '{comp_name}' declares sponsor '{sponsor_id}' "
                    f"({info.get('description', 'No description')}), but that account DOES NOT EXIST in the user store. "
                    "Accounts must be provisioned by an administrator before compartment sponsorship can activate."
                )
            if bool(row["is_admin"]):
                raise RuntimeError(
                    f"FATAL STARTUP CHECK FAILED: Sponsor '{sponsor_id}' for compartment '{comp_name}' is an "
                    "ADMINISTRATOR. Separation of duties forbids one account holding both authorities."
                )
            if not bool(row["is_active"]):
                raise RuntimeError(
                    f"FATAL STARTUP CHECK FAILED: Sponsor '{sponsor_id}' for compartment '{comp_name}' "
                    "is DEACTIVATED. A deactivated account cannot sponsor compartments."
                )
    finally:
        conn.close()


def assert_separation_of_duties(config: dict[str, dict[str, str]]) -> None:
    """One person may sponsor at most one compartment."""
    seen: dict[str, str] = {}
    for comp_name, info in config.items():
        sponsor_id = info.get("sponsor")
        if sponsor_id in seen:
            raise RuntimeError(
                f"Configuration error: '{sponsor_id}' is declared sponsor of both '{seen[sponsor_id]}' and "
                f"'{comp_name}'. Separation of duties requires a different sponsor for every compartment."
            )
        seen[sponsor_id] = comp_name


def sponsor_ids(config_path: Optional[str | Path] = None) -> set[str]:
    """Every person_id that sponsors some compartment."""
    return {info.get("sponsor") for info in load_compartment_config(config_path).values() if info.get("sponsor")}


def sponsored_by(person_id: str, config_path: Optional[str | Path] = None) -> set[str]:
    """Compartment id(s) this person sponsors. A sponsor can always READ the
    compartment they sponsor: that access derives from config, is not a
    stored grant, and so can't be self-granted or revoked by anyone."""
    return {c for c, info in load_compartment_config(config_path).items() if info.get("sponsor") == person_id}


def is_sponsor(
    db_path: str,
    actor_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> bool:
    """True only for the compartment's designated sponsor. There are no delegates."""
    comp_info = load_compartment_config(config_path).get(compartment.value)
    return bool(comp_info) and comp_info.get("sponsor") == actor_id



def get_sponsored_compartments(
    db_path: str,
    actor_id: str,
    config_path: Optional[str | Path] = None,
) -> list[Compartment]:
    """The compartment(s) actor_id sponsors, straight from config/compartments.json."""
    config = load_compartment_config(config_path)
    return sorted((Compartment(c) for c, info in config.items() if info.get("sponsor") == actor_id),
                  key=lambda c: c.value)


def grant_compartment(
    db_path: str,
    actor_id: str,
    target_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> None:
    """Grant a compartment clearance to an employee.

    Enforces all non-negotiable sponsor rules:
    - Actor cannot grant to themselves.
    - Actor must sponsor this specific compartment.
    - Target must be an active, non-administrator account.
    - Appends to immutable audit ledger.
    """
    if actor_id == target_id:
        raise PermissionError(
            "Self-grant violation blocked: A sponsor cannot grant compartments to themselves. "
            "A different authorized officer is required."
        )

    if not is_sponsor(db_path, actor_id, compartment, config_path):
        raise PermissionError(
            f"Unauthorized: Actor '{actor_id}' does not sponsor compartment '{compartment.value}'. "
            "Compartments may only be granted by their designated sponsor."
        )

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT compartments, is_admin FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active target employee '{target_id}' not found.")
            if bool(row["is_admin"]):
                raise PermissionError(
                    f"'{target_id}' is an administrator. Administrators manage accounts only and hold no "
                    "compartment access (separation of duties)."
                )

            current_comps = set(json.loads(row["compartments"]))
            current_comps.add(compartment.value)

            cursor.execute(
                "UPDATE users SET compartments = ? WHERE person_id = ?;",
                (json.dumps(sorted(list(current_comps))), target_id),
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO compartment_grants (compartment, actor_id, target_id, action, timestamp)
                VALUES (?, ?, ?, 'GRANT', ?);
                """,
                (compartment.value, actor_id, target_id, now_iso),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="GRANT_COMPARTMENT",
        details={
            "subject": target_id,
            "compartment": compartment.value,
        },
    )


def revoke_compartment(
    db_path: str,
    actor_id: str,
    target_id: str,
    compartment: Compartment,
    config_path: Optional[str | Path] = None,
) -> None:
    """Revoke a compartment clearance from an employee."""
    if actor_id == target_id:
        raise PermissionError("Self-modification violation blocked: Cannot revoke compartments from yourself.")

    if not is_sponsor(db_path, actor_id, compartment, config_path):
        raise PermissionError(
            f"Unauthorized: Actor '{actor_id}' does not sponsor compartment '{compartment.value}'."
        )

    init_grants_tables(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT compartments FROM users WHERE person_id = ? AND is_active = 1;", (target_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Active target employee '{target_id}' not found.")

            current_comps = set(json.loads(row["compartments"]))
            current_comps.discard(compartment.value)

            cursor.execute(
                "UPDATE users SET compartments = ? WHERE person_id = ?;",
                (json.dumps(sorted(list(current_comps))), target_id),
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO compartment_grants (compartment, actor_id, target_id, action, timestamp)
                VALUES (?, ?, ?, 'REVOKE', ?);
                """,
                (compartment.value, actor_id, target_id, now_iso),
            )
    finally:
        conn.close()

    ledger_log(
        db_path=db_path,
        actor=actor_id,
        action="REVOKE_COMPARTMENT",
        details={
            "subject": target_id,
            "compartment": compartment.value,
        },
    )
