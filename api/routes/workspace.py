"""The caller's private agent workspace: list, download, delete.

ZERO ACCESS DECISIONS INSIDE beyond ownership (a person only ever addresses
their own workspace directory) -- the classification check on download is
trust/labels.can_read against the label each file inherited when the agent
wrote it (harness/workspace.py).
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Response, status

from auth.deps import current_principal
from contracts import Principal, WorkspaceFile
from harness import workspace
from trust.labels import can_read, denial_reason

router = APIRouter(prefix="/workspace", tags=["Agent Workspace"])


@router.get("/files", response_model=list[WorkspaceFile])
def list_workspace(principal: Principal = Depends(current_principal)):
    return workspace.list_files(principal.person_id)


@router.get("/files/{name}")
def download_workspace_file(name: str, principal: Principal = Depends(current_principal)):
    try:
        info = workspace.describe(principal.person_id, name)
        data = workspace.read_bytes(principal.person_id, name)
    except workspace.WorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not can_read(principal, info.label):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This file was derived from material you can no longer read: {denial_reason(principal, info.label)}",
        )
    media_type = mimetypes.guess_type(info.name)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{info.name}"'})


@router.delete("/files/{name}")
def delete_workspace_file(name: str, principal: Principal = Depends(current_principal)):
    try:
        workspace.delete(principal.person_id, name)
    except workspace.WorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"status": "deleted", "name": name}
