"""Corpus exploration endpoints.

ZERO ACCESS DECISIONS INSIDE.
Per-user readability is evaluated strictly by trust/labels.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from contracts import Compartment, Label, Principal, Tier
from auth.deps import current_principal
from trust.labels import can_read, denial_reason

router = APIRouter(prefix="/documents", tags=["Corpus"])

MANIFEST_PATH = Path(__file__).parent.parent.parent / "corpus" / "manifest.json"
DOCS_DIR = Path(__file__).parent.parent.parent / "corpus" / "documents"


def _entry_for(doc_id: str) -> tuple[Path, Label] | None:
    """Resolve a doc_id to its PDF and label: manifest first, then the same
    auto-discovery defaults ingest/pdf.py applies to undeclared PDFs."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else []
    for entry in manifest:
        if entry.get("doc_id") == doc_id:
            label_data = entry.get("label", {})
            label = Label(
                tier=Tier(label_data.get("tier", Tier.INTERNAL.value)),
                compartments=frozenset(Compartment(c) for c in label_data.get("compartments", [])),
            )
            return DOCS_DIR / entry.get("file", f"{doc_id}.pdf"), label
    from ingest.pdf import infer_default_label_and_title
    for pdf in DOCS_DIR.glob("*.pdf"):
        inferred_id, label, _ = infer_default_label_and_title(pdf.name)
        if inferred_id == doc_id:
            return pdf, label
    return None


@router.get("")
def list_documents(
    principal: Principal = Depends(current_principal),
):
    """List all documents in the corpus with per-user readability indicators."""
    if not MANIFEST_PATH.exists():
        return []

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    results = []
    for entry in manifest:
        label_data = entry.get("label", {})
        tier = Tier(label_data.get("tier", Tier.INTERNAL.value))
        comps = frozenset(Compartment(c) for c in label_data.get("compartments", []))
        label = Label(tier=tier, compartments=comps)

        # Pure evaluation via trust/labels.py
        is_readable = can_read(principal, label)
        reason = None if is_readable else denial_reason(principal, label)

        results.append({
            "doc_id": entry["doc_id"],
            "title": entry.get("title", entry["doc_id"]),
            "source": entry.get("source", "MRPL Internal"),
            "label": {
                "tier": tier.value,
                "compartments": [c.value for c in comps],
            },
            "readable": is_readable,
            "denial_reason": reason,
        })

    return results


@router.get("/{doc_id}/file")
def open_document(
    doc_id: str,
    principal: Principal = Depends(current_principal),
):
    """Serve a corpus PDF inline (so a source card can open it at #page=N),
    only if the caller is cleared for its label -- the same two-axis check
    retrieval applies. A denied or unknown doc_id reveals nothing."""
    resolved = _entry_for(doc_id)
    if resolved is None or not resolved[0].is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    path, label = resolved
    if not can_read(principal, label):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=denial_reason(principal, label))
    return FileResponse(str(path), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})
