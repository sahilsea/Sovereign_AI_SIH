"""Compartment grant and revocation endpoints.

ZERO ACCESS DECISIONS INSIDE.
All authority is delegated to auth/sponsors.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from contracts import GrantCompartmentRequest, Principal, RevokeCompartmentRequest
from auth.deps import current_principal, get_db_path
from auth.sponsors import get_sponsored_compartments, grant_compartment, load_compartment_config, revoke_compartment
from auth.users import list_users

router = APIRouter(prefix="/grants", tags=["Compartment Grants"])


@router.post("")
def add_compartment_grant(
    payload: GrantCompartmentRequest,
    principal: Principal = Depends(current_principal),
):
    """Grant a compartment clearance. Caller must be the designated sponsor."""
    db_path = get_db_path()
    try:
        grant_compartment(
            db_path=db_path,
            actor_id=principal.person_id,
            target_id=payload.person_id,
            compartment=payload.compartment,
        )
        return {
            "status": "compartment_granted",
            "actor": principal.person_id,
            "subject": payload.person_id,
            "compartment": payload.compartment.value,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("")
def remove_compartment_grant(
    payload: RevokeCompartmentRequest,
    principal: Principal = Depends(current_principal),
):
    """Revoke a compartment clearance. Caller must be the designated sponsor."""
    db_path = get_db_path()
    try:
        revoke_compartment(
            db_path=db_path,
            actor_id=principal.person_id,
            target_id=payload.person_id,
            compartment=payload.compartment,
        )
        return {
            "status": "compartment_revoked",
            "actor": principal.person_id,
            "subject": payload.person_id,
            "compartment": payload.compartment.value,
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/mine")
def get_my_sponsored_compartments(
    principal: Principal = Depends(current_principal),
):
    """List compartments that the caller is authorized to grant or revoke."""
    db_path = get_db_path()
    comps = get_sponsored_compartments(db_path, principal.person_id)
    return {"sponsored_compartments": [c.value for c in comps]}


@router.get("/compartments")
def list_compartment_sponsors(
    principal: Principal = Depends(current_principal),
):
    """Every compartment and the ONE person who sponsors it (read-only)."""
    return [
        {"id": comp_id, "description": info.get("description", ""), "sponsor": info.get("sponsor")}
        for comp_id, info in load_compartment_config().items()
    ]


@router.get("/people")
def list_people_for_sponsor(
    principal: Principal = Depends(current_principal),
):
    """For a sponsor: every active, non-admin employee (except themselves) and
    whether they currently hold the sponsor's compartment. Shows ONLY the
    caller's own compartment -- a sponsor learns nothing about the others."""
    comps = [c.value for c in get_sponsored_compartments(get_db_path(), principal.person_id)]
    if not comps:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not sponsor any compartment.")
    people = []
    for u in list_users(get_db_path()):
        if not u.is_active or u.is_admin or u.person_id == principal.person_id:
            continue
        held = {c.value for c in u.compartments}
        people.append({
            "person_id": u.person_id, "name": u.name, "job_title": u.job_title, "grade": u.grade,
            "holds": {c: c in held for c in comps},
            "sponsor_of": [c.value for c in u.sponsor_of],
        })
    return {"compartments": comps, "people": people}
