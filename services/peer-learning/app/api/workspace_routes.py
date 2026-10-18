import hashlib
import io
import logging
import os
import re
import secrets
import string
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents.workspace_assistant import workspace_assistant
from app.api.student_routes import verify_jwt_student
from app.models.workspace_schemas import (
    AssistantAskRequest,
    ChatMessageCreateRequest,
    CodeRunRequest,
    CommentCreateRequest,
    CommentUpdateRequest,
    FileContentUpdateRequest,
    FileCreateRequest,
    FileUpdateRequest,
    InviteAcceptRequest,
    InviteCreateRequest,
    JoinKeyCreateRequest,
    JoinWorkspaceRequest,
    MemberAddRequest,
    MemberRoleUpdateRequest,
    OwnershipTransferRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
)
from app.services import code_sandbox
from app.services.mongodb import get_collection, log_workspace_activity

logger = logging.getLogger("workspace_routes")

router = APIRouter(prefix="/api/workspaces", tags=["Project Workspace"])

VALID_ROLES = {"owner", "editor", "viewer"}
ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
MANAGER_ROLES = {"owner"}
WRITE_ROLES = {"owner", "editor"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _gen_join_key(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    ambiguous = set("O0I1")
    chars = [c for c in alphabet if c not in ambiguous]
    return "".join(secrets.choice(chars) for _ in range(length))


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


def _require_workspace(workspace_id: str) -> dict:
    workspace = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _require_member(workspace_id: str, student_id: str) -> dict:
    member = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": student_id,
        "status": "active",
    })
    if not member:
        raise HTTPException(status_code=403, detail="You are not an active member of this workspace.")
    return member


def _require_role(member: dict, allowed: set) -> None:
    if member.get("role") not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires one of these roles: {', '.join(sorted(allowed))}.",
        )


def _member_count(workspace_id: str) -> int:
    return get_collection("workspace_members").count_documents({
        "workspace_id": workspace_id,
        "status": "active",
    })


def _add_member(workspace_id: str, student_id: str, role: str, actor_student_id: Optional[str] = None) -> dict:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role '{role}'. Use one of: owner, editor, viewer.")

    existing = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": student_id,
    })
    if existing and existing.get("status") == "active":
        return _clean(existing)

    now = _now_iso()
    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "student_id": student_id},
        {
            "$set": {"role": role, "status": "active", "updated_at": now},
            "$setOnInsert": {"joined_at": now, "last_seen_at": now},
        },
        upsert=True,
    )
    log_workspace_activity(
        workspace_id,
        actor_student_id or student_id,
        "member_added",
        {"student_id": student_id, "role": role},
    )
    return {"workspace_id": workspace_id, "student_id": student_id, "role": role, "status": "active"}


def _expiry_iso(expires_in_hours: Optional[int]) -> Optional[str]:
    if expires_in_hours is None:
        return None
    return (_now() + timedelta(hours=expires_in_hours)).isoformat()


def _consume(record: dict, collection_name: str, id_field: str) -> None:
    if record.get("expires_at") and record["expires_at"] < _now_iso():
        raise HTTPException(status_code=410, detail="This join credential has expired.")
    max_uses = record.get("max_uses")
    if max_uses is not None and record.get("uses", 0) >= max_uses:
        raise HTTPException(status_code=410, detail="This join credential has reached its maximum number of uses.")

    uses = record.get("uses", 0) + 1
    update: Dict[str, Any] = {"$inc": {"uses": 1}, "$set": {"last_used_at": _now_iso()}}
    if max_uses is not None and uses >= max_uses:
        update["$set"]["status"] = "exhausted"
    get_collection(collection_name).update_one({id_field: record[id_field]}, update)


# ==========================================
# 1. Workspace Endpoints
# ==========================================

@router.post("")
def create_workspace(
    request: WorkspaceCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Creates a new project workspace and registers the caller as its owner."""
    visibility = request.visibility or "private"
    if visibility not in {"private", "invite"}:
        raise HTTPException(status_code=422, detail="Invalid visibility. Use 'private' or 'invite'.")

    workspace_id = f"WS_{uuid.uuid4().hex[:12].upper()}"
    now = _now_iso()
    workspace = {
        "workspace_id": workspace_id,
        "name": request.name,
        "description": request.description or "",
        "visibility": visibility,
        "status": "active",
        "owner_student_id": token_student_id,
        "member_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    get_collection("workspaces").insert_one(dict(workspace))
    _add_member(workspace_id, token_student_id, "owner", actor_student_id=token_student_id)
    workspace["member_count"] = _member_count(workspace_id)
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id}, {"$set": {"member_count": workspace["member_count"]}}
    )

    return {"status": "success", "workspace": _clean(workspace)}


@router.get("")
def list_workspaces(
    include_archived: bool = Query(default=False),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists every workspace the caller is an active member of."""
    try:
        memberships = list(get_collection("workspace_members").find({
            "student_id": token_student_id,
            "status": "active",
        }))
        workspace_ids = [m["workspace_id"] for m in memberships]
        role_by_id = {m["workspace_id"]: m.get("role") for m in memberships}

        query: Dict[str, Any] = {"workspace_id": {"$in": workspace_ids}}
        if not include_archived:
            query["status"] = {"$ne": "archived"}

        workspaces = list(get_collection("workspaces").find(query, sort=[("updated_at", -1)]))
        for workspace in workspaces:
            workspace["role"] = role_by_id.get(workspace["workspace_id"])

        return {
            "status": "success",
            "total": len(workspaces),
            "workspaces": [_clean(w) for w in workspaces],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list workspaces: {str(e)}")


@router.get("/{workspace_id}")
def get_workspace(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns workspace details for an active member."""
    workspace = _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    result = _clean(workspace)
    result["role"] = member.get("role")
    result["member_count"] = _member_count(workspace_id)
    return {"status": "success", "workspace": result}


@router.patch("/{workspace_id}")
def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Updates workspace metadata. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    updates: Dict[str, Any] = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.visibility is not None:
        if request.visibility not in {"private", "invite"}:
            raise HTTPException(status_code=422, detail="Invalid visibility. Use 'private' or 'invite'.")
        updates["visibility"] = request.visibility
    if request.status is not None:
        if request.status not in {"active", "archived"}:
            raise HTTPException(status_code=422, detail="Invalid status. Use 'active' or 'archived'.")
        updates["status"] = request.status

    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields were supplied.")

    updates["updated_at"] = _now_iso()
    get_collection("workspaces").update_one({"workspace_id": workspace_id}, {"$set": updates})
    log_workspace_activity(workspace_id, token_student_id, "workspace_updated", {"fields": list(updates.keys())})

    return {"status": "success", "workspace": _clean(_require_workspace(workspace_id))}


@router.delete("/{workspace_id}")
def archive_workspace(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Archives a workspace (soft delete). Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"status": "archived", "updated_at": _now_iso()}},
    )
    log_workspace_activity(workspace_id, token_student_id, "workspace_archived", {})

    return {"status": "success", "message": f"Workspace '{workspace_id}' archived."}


# ==========================================
# 2. Membership Endpoints
# ==========================================

@router.get("/{workspace_id}/members")
def list_members(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists active members of a workspace."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    members = list(get_collection("workspace_members").find(
        {"workspace_id": workspace_id, "status": "active"},
        sort=[("joined_at", 1)],
    ))
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(members),
        "members": [_clean(m) for m in members],
    }


@router.post("/{workspace_id}/members")
def add_member(
    workspace_id: str,
    request: MemberAddRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Directly adds a member to a workspace. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    added = _add_member(workspace_id, request.student_id, request.role or "editor", actor_student_id=token_student_id)
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"member_count": _member_count(workspace_id), "updated_at": _now_iso()}},
    )
    return {"status": "success", "member": added}


@router.patch("/{workspace_id}/members/{student_id}")
def update_member_role(
    workspace_id: str,
    student_id: str,
    request: MemberRoleUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Changes a member's role. Owner only."""
    _require_workspace(workspace_id)
    acting = _require_member(workspace_id, token_student_id)
    _require_role(acting, MANAGER_ROLES)

    if request.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role. Use one of: owner, editor, viewer.")
    if student_id == token_student_id and request.role != "owner":
        raise HTTPException(status_code=422, detail="The owner cannot demote themselves.")

    target = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": student_id,
        "status": "active",
    })
    if not target:
        raise HTTPException(status_code=404, detail="Member not found in this workspace.")

    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "student_id": student_id},
        {"$set": {"role": request.role, "updated_at": _now_iso()}},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "member_role_changed",
        {"student_id": student_id, "role": request.role},
    )
    return {"status": "success", "message": f"Member '{student_id}' is now '{request.role}'."}


@router.delete("/{workspace_id}/members/{student_id}")
def remove_member(
    workspace_id: str,
    student_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Removes a member. Owner may remove anyone; members may remove themselves (leave)."""
    _require_workspace(workspace_id)
    acting = _require_member(workspace_id, token_student_id)

    is_self = student_id == token_student_id
    if not is_self and acting.get("role") not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only the owner can remove other members.")

    target = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": student_id,
        "status": "active",
    })
    if not target:
        raise HTTPException(status_code=404, detail="Member not found in this workspace.")
    if target.get("role") == "owner" and not is_self:
        raise HTTPException(status_code=422, detail="The workspace owner cannot be removed.")

    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "student_id": student_id},
        {"$set": {"status": "removed", "updated_at": _now_iso()}},
    )
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"member_count": _member_count(workspace_id), "updated_at": _now_iso()}},
    )
    log_workspace_activity(
        workspace_id, token_student_id,
        "member_left" if is_self else "member_removed",
        {"student_id": student_id},
    )
    return {"status": "success", "message": f"Member '{student_id}' removed from workspace."}


@router.post("/{workspace_id}/leave")
def leave_workspace(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Leaves a workspace. The owner must transfer ownership or archive instead."""
    return remove_member(workspace_id, token_student_id, token_student_id=token_student_id)


# ==========================================
# 3. Join Key Endpoints
# ==========================================

@router.post("/{workspace_id}/join-keys")
def create_join_key(
    workspace_id: str,
    request: JoinKeyCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Generates a shareable join key. The plaintext key is returned only once. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    if request.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role. Use one of: owner, editor, viewer.")

    join_key = _gen_join_key()
    while get_collection("workspace_join_keys").find_one({"key_hash": _hash_secret(join_key)}):
        join_key = _gen_join_key()

    key_id = f"KEY_{uuid.uuid4().hex[:10].upper()}"
    get_collection("workspace_join_keys").insert_one({
        "key_id": key_id,
        "workspace_id": workspace_id,
        "key_hash": _hash_secret(join_key),
        "role": request.role or "editor",
        "created_by": token_student_id,
        "created_at": _now_iso(),
        "expires_at": _expiry_iso(request.expires_in_hours),
        "max_uses": request.max_uses,
        "uses": 0,
        "status": "active",
    })
    log_workspace_activity(
        workspace_id, token_student_id, "join_key_created", {"key_id": key_id, "role": request.role or "editor"}
    )
    return {"status": "success", "join_key": join_key, "key_id": key_id}


@router.get("/{workspace_id}/join-keys")
def list_join_keys(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists join-key metadata (never the secret). Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    keys = list(get_collection("workspace_join_keys").find(
        {"workspace_id": workspace_id},
        sort=[("created_at", -1)],
    ))
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(keys),
        "join_keys": [_clean(k) for k in keys],
    }


@router.delete("/{workspace_id}/join-keys/{key_id}")
def revoke_join_key(
    workspace_id: str,
    key_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Revokes a join key. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    result = get_collection("workspace_join_keys").update_one(
        {"workspace_id": workspace_id, "key_id": key_id},
        {"$set": {"status": "revoked", "revoked_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Join key not found.")

    log_workspace_activity(workspace_id, token_student_id, "join_key_revoked", {"key_id": key_id})
    return {"status": "success", "message": f"Join key '{key_id}' revoked."}


@router.post("/join")
def join_with_key(
    request: JoinWorkspaceRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Joins a workspace using a join key."""
    key_hash = _hash_secret(request.join_key.strip())
    record = get_collection("workspace_join_keys").find_one({"key_hash": key_hash, "status": "active"})
    if not record:
        raise HTTPException(status_code=404, detail="Invalid or inactive join key.")

    workspace_id = record["workspace_id"]
    workspace = _require_workspace(workspace_id)
    if workspace.get("status") == "archived":
        raise HTTPException(status_code=410, detail="This workspace has been archived.")

    _consume(record, "workspace_join_keys", "key_id")

    already = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": token_student_id,
        "status": "active",
    })
    if already:
        return {"status": "success", "message": "You are already a member.", "workspace_id": workspace_id}

    _add_member(workspace_id, token_student_id, record.get("role", "editor"), actor_student_id=token_student_id)
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"member_count": _member_count(workspace_id), "updated_at": _now_iso()}},
    )
    return {
        "status": "success",
        "message": f"Joined workspace '{workspace_id}'.",
        "workspace_id": workspace_id,
        "workspace": _clean(workspace),
    }


# ==========================================
# 4. Invite Endpoints
# ==========================================

@router.post("/{workspace_id}/invites")
def create_invite(
    workspace_id: str,
    request: InviteCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Creates an invite token. The token is returned only once. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    if request.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail="Invalid role. Use one of: owner, editor, viewer.")

    token = _gen_token()
    invite_id = f"INV_{uuid.uuid4().hex[:10].upper()}"
    get_collection("workspace_invites").insert_one({
        "invite_id": invite_id,
        "workspace_id": workspace_id,
        "token_hash": _hash_secret(token),
        "role": request.role or "editor",
        "created_by": token_student_id,
        "created_at": _now_iso(),
        "expires_at": _expiry_iso(request.expires_in_hours),
        "max_uses": request.max_uses,
        "uses": 0,
        "status": "active",
    })
    log_workspace_activity(
        workspace_id, token_student_id, "invite_created", {"invite_id": invite_id, "role": request.role or "editor"}
    )
    return {"status": "success", "invite_token": token, "invite_id": invite_id}


@router.get("/{workspace_id}/invites")
def list_invites(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists invite metadata (never the token). Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    invites = list(get_collection("workspace_invites").find(
        {"workspace_id": workspace_id},
        sort=[("created_at", -1)],
    ))
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(invites),
        "invites": [_clean(i) for i in invites],
    }


@router.delete("/{workspace_id}/invites/{invite_id}")
def revoke_invite(
    workspace_id: str,
    invite_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Revokes an invite. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    result = get_collection("workspace_invites").update_one(
        {"workspace_id": workspace_id, "invite_id": invite_id},
        {"$set": {"status": "revoked", "revoked_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invite not found.")

    log_workspace_activity(workspace_id, token_student_id, "invite_revoked", {"invite_id": invite_id})
    return {"status": "success", "message": f"Invite '{invite_id}' revoked."}


@router.post("/invites/accept")
def accept_invite(
    request: InviteAcceptRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Accepts a workspace invite token and joins the workspace."""
    token_hash = _hash_secret(request.token.strip())
    record = get_collection("workspace_invites").find_one({"token_hash": token_hash, "status": "active"})
    if not record:
        raise HTTPException(status_code=404, detail="Invalid or inactive invite token.")

    workspace_id = record["workspace_id"]
    workspace = _require_workspace(workspace_id)
    if workspace.get("status") == "archived":
        raise HTTPException(status_code=410, detail="This workspace has been archived.")

    _consume(record, "workspace_invites", "invite_id")

    already = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": token_student_id,
        "status": "active",
    })
    if already:
        return {"status": "success", "message": "You are already a member.", "workspace_id": workspace_id}

    _add_member(workspace_id, token_student_id, record.get("role", "editor"), actor_student_id=token_student_id)
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"member_count": _member_count(workspace_id), "updated_at": _now_iso()}},
    )
    return {
        "status": "success",
        "message": f"Joined workspace '{workspace_id}'.",
        "workspace_id": workspace_id,
        "workspace": _clean(workspace),
    }


# ==========================================
# 5. File System & Editor Endpoints
# ==========================================

def _norm_path(value: Optional[str]) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    for part in parts:
        if part == "..":
            raise HTTPException(status_code=422, detail="Path traversal is not allowed.")
    return "/".join(parts)


def _file_or_404(workspace_id: str, file_id: str) -> dict:
    doc = get_collection("workspace_files").find_one({
        "workspace_id": workspace_id,
        "file_id": file_id,
        "status": "active",
    })
    if not doc:
        raise HTTPException(status_code=404, detail="File or folder not found in this workspace.")
    return doc


def _descendants(workspace_id: str, path: str) -> List[dict]:
    return list(get_collection("workspace_files").find({
        "workspace_id": workspace_id,
        "status": "active",
        "path": {"$regex": f"^{re.escape(path)}/"},
    }))


def _snapshot_version(
    workspace_id: str, file_doc: dict, content: str, author_student_id: str, message: Optional[str] = None
) -> int:
    version_number = int(file_doc.get("version_count", 0)) + 1
    get_collection("workspace_file_versions").insert_one({
        "version_id": f"VER_{uuid.uuid4().hex[:12].upper()}",
        "workspace_id": workspace_id,
        "file_id": file_doc["file_id"],
        "version_number": version_number,
        "content": content,
        "size": len(content.encode("utf-8")),
        "author_student_id": author_student_id,
        "message": message or f"Version {version_number}",
        "created_at": _now_iso(),
    })
    return version_number


@router.post("/{workspace_id}/files")
def create_file(
    workspace_id: str,
    request: FileCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Creates a file or folder in the workspace tree. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    entry_type = request.type or "file"
    if entry_type not in {"file", "folder"}:
        raise HTTPException(status_code=422, detail="Invalid type. Use 'file' or 'folder'.")

    name = _norm_path(request.name)
    if not name or "/" in name:
        raise HTTPException(status_code=422, detail="Name must be a single path segment without '/'.")

    parent = _norm_path(request.parent_path)
    path = f"{parent}/{name}" if parent else name

    if get_collection("workspace_files").find_one({
        "workspace_id": workspace_id, "path": path, "status": "active",
    }):
        raise HTTPException(status_code=409, detail=f"An item already exists at '{path}'.")

    if parent and not get_collection("workspace_files").find_one({
        "workspace_id": workspace_id, "path": parent, "type": "folder", "status": "active",
    }):
        raise HTTPException(status_code=404, detail=f"Parent folder '{parent}' was not found.")

    content = "" if entry_type == "folder" else (request.content or "")
    now = _now_iso()
    file_id = f"FILE_{uuid.uuid4().hex[:12].upper()}"
    doc = {
        "file_id": file_id,
        "workspace_id": workspace_id,
        "name": name,
        "path": path,
        "parent_path": parent,
        "type": entry_type,
        "language": request.language or "java",
        "content": content,
        "size": len(content.encode("utf-8")),
        "version_count": 0,
        "created_by": token_student_id,
        "updated_by": token_student_id,
        "created_at": now,
        "updated_at": now,
        "status": "active",
    }
    get_collection("workspace_files").insert_one(dict(doc))

    if entry_type == "file":
        version_number = _snapshot_version(workspace_id, doc, content, token_student_id, "Initial version")
        get_collection("workspace_files").update_one(
            {"workspace_id": workspace_id, "file_id": file_id},
            {"$set": {"version_count": version_number}},
        )
        doc["version_count"] = version_number

    log_workspace_activity(
        workspace_id, token_student_id,
        "file_created" if entry_type == "file" else "folder_created",
        {"file_id": file_id, "path": path},
    )
    return {"status": "success", "file": _clean(doc)}


@router.get("/{workspace_id}/files")
def list_files(
    workspace_id: str,
    include_content: bool = Query(default=False),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists the workspace file tree. Content is omitted unless requested."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    files = list(get_collection("workspace_files").find(
        {"workspace_id": workspace_id, "status": "active"},
        sort=[("path", 1)],
    ))
    result = []
    for entry in files:
        cleaned = _clean(entry)
        if not include_content:
            cleaned.pop("content", None)
        result.append(cleaned)

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(result),
        "files": result,
    }


@router.get("/{workspace_id}/files/{file_id}")
def get_file(
    workspace_id: str,
    file_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns a single file/folder including its current content."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)
    return {"status": "success", "file": _clean(_file_or_404(workspace_id, file_id))}


@router.put("/{workspace_id}/files/{file_id}/content")
def update_file_content(
    workspace_id: str,
    file_id: str,
    request: FileContentUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Saves editor content, creating a new version snapshot. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    doc = _file_or_404(workspace_id, file_id)
    if doc.get("type") != "file":
        raise HTTPException(status_code=422, detail="Folders have no editable content.")

    current_version = int(doc.get("version_count", 0))
    if request.base_version is not None and int(request.base_version) != current_version:
        raise HTTPException(
            status_code=409,
            detail=f"Version conflict: file is at version {current_version}, request expected {request.base_version}.",
        )

    content = request.content or ""
    version_number = _snapshot_version(
        workspace_id, doc, content, token_student_id, request.message or "Content update"
    )
    now = _now_iso()
    get_collection("workspace_files").update_one(
        {"workspace_id": workspace_id, "file_id": file_id},
        {"$set": {
            "content": content,
            "size": len(content.encode("utf-8")),
            "version_count": version_number,
            "updated_by": token_student_id,
            "updated_at": now,
        }},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "file_edited",
        {"file_id": file_id, "path": doc.get("path"), "version": version_number},
    )
    return {
        "status": "success",
        "file_id": file_id,
        "version_number": version_number,
        "updated_at": now,
    }


@router.patch("/{workspace_id}/files/{file_id}")
def update_file(
    workspace_id: str,
    file_id: str,
    request: FileUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Renames or moves a file/folder. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    doc = _file_or_404(workspace_id, file_id)
    now = _now_iso()
    updates: Dict[str, Any] = {}

    target_name = _norm_path(request.name) if request.name is not None else doc.get("name", "")
    if not target_name or "/" in target_name:
        raise HTTPException(status_code=422, detail="Name must be a single path segment without '/'.")
    target_parent = (
        _norm_path(request.parent_path) if request.parent_path is not None else doc.get("parent_path", "")
    )
    new_path = f"{target_parent}/{target_name}" if target_parent else target_name

    if new_path != doc.get("path"):
        if get_collection("workspace_files").find_one({
            "workspace_id": workspace_id, "path": new_path, "status": "active",
        }):
            raise HTTPException(status_code=409, detail=f"An item already exists at '{new_path}'.")
        if target_parent and not get_collection("workspace_files").find_one({
            "workspace_id": workspace_id, "path": target_parent, "type": "folder", "status": "active",
        }):
            raise HTTPException(status_code=404, detail=f"Target parent folder '{target_parent}' was not found.")
        if doc.get("type") == "folder" and new_path.startswith(f"{doc['path']}/"):
            raise HTTPException(status_code=400, detail="A folder cannot be moved into one of its own descendants.")

        if doc.get("type") == "folder":
            for child in _descendants(workspace_id, doc["path"]):
                child_path = new_path + child["path"][len(doc["path"]):]
                get_collection("workspace_files").update_one(
                    {"workspace_id": workspace_id, "file_id": child["file_id"]},
                    {"$set": {"path": child_path, "parent_path": child_path.rsplit("/", 1)[0], "updated_at": now}},
                )

        updates.update({"name": target_name, "parent_path": target_parent, "path": new_path})

    if request.language is not None:
        updates["language"] = request.language

    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields were supplied.")

    updates.update({"updated_by": token_student_id, "updated_at": now})
    get_collection("workspace_files").update_one(
        {"workspace_id": workspace_id, "file_id": file_id},
        {"$set": updates},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "file_moved",
        {"file_id": file_id, "from": doc.get("path"), "to": new_path},
    )
    return {"status": "success", "file": _clean(_file_or_404(workspace_id, file_id))}


@router.delete("/{workspace_id}/files/{file_id}")
def delete_file(
    workspace_id: str,
    file_id: str,
    recursive: bool = Query(default=False),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Deletes a file, or a folder (recursively when requested). Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    doc = _file_or_404(workspace_id, file_id)
    now = _now_iso()
    deleted_count = 1

    if doc.get("type") == "folder":
        children = _descendants(workspace_id, doc["path"])
        if children and not recursive:
            raise HTTPException(
                status_code=409,
                detail="Folder is not empty. Pass recursive=true to delete its contents.",
            )
        for child in children:
            get_collection("workspace_files").update_one(
                {"workspace_id": workspace_id, "file_id": child["file_id"]},
                {"$set": {"status": "deleted", "deleted_at": now}},
            )
        deleted_count += len(children)

    get_collection("workspace_files").update_one(
        {"workspace_id": workspace_id, "file_id": file_id},
        {"$set": {"status": "deleted", "deleted_at": now, "updated_by": token_student_id}},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "file_deleted",
        {"file_id": file_id, "path": doc.get("path"), "deleted_count": deleted_count},
    )
    return {
        "status": "success",
        "message": f"Deleted '{doc.get('path')}'.",
        "deleted_count": deleted_count,
    }


@router.get("/{workspace_id}/files/{file_id}/versions")
def list_file_versions(
    workspace_id: str,
    file_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists version metadata for a file (content omitted)."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)
    _file_or_404(workspace_id, file_id)

    versions = list(get_collection("workspace_file_versions").find(
        {"workspace_id": workspace_id, "file_id": file_id},
        sort=[("version_number", -1)],
    ))
    result = []
    for version in versions:
        cleaned = _clean(version)
        cleaned.pop("content", None)
        result.append(cleaned)

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "file_id": file_id,
        "total": len(result),
        "versions": result,
    }


@router.get("/{workspace_id}/files/{file_id}/versions/{version_id}")
def get_file_version(
    workspace_id: str,
    file_id: str,
    version_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns one historical version of a file, including its content."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)
    _file_or_404(workspace_id, file_id)

    version = get_collection("workspace_file_versions").find_one({
        "workspace_id": workspace_id,
        "file_id": file_id,
        "version_id": version_id,
    })
    if not version:
        raise HTTPException(status_code=404, detail="Version not found.")

    return {"status": "success", "version": _clean(version)}


# ==========================================
# 6. Activity Feed Endpoint
# ==========================================

@router.get("/{workspace_id}/activity")
def list_activity(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    since: Optional[str] = Query(default=None, description="ISO timestamp — return only newer entries"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns the workspace activity feed, newest first, for active members."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    query: Dict[str, Any] = {"workspace_id": workspace_id}
    if since:
        query["timestamp"] = {"$gt": since}

    entries = list(get_collection("workspace_activity_log").find(
        query,
        sort=[("timestamp", -1)],
        limit=limit,
    ))
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(entries),
        "activity": [_clean(e) for e in entries],
    }


# ==========================================
# 7. Workspace Chat Endpoints
# ==========================================

def _student_display_name(student_id: str) -> str:
    for collection_name in ("students", "student_analyses"):
        try:
            doc = get_collection(collection_name).find_one({"student_id": student_id})
        except Exception:
            doc = None
        if doc and doc.get("name"):
            return str(doc["name"])
    return str(student_id)


def persist_chat_message(
    workspace_id: str,
    student_id: str,
    sender_name: str,
    role: Optional[str],
    message: str,
    message_type: Optional[str] = "text",
    reply_to: Optional[str] = None,
) -> dict:
    """Builds and persists a workspace chat message; shared by REST and WebSocket."""
    doc = {
        "message_id": f"MSG_{uuid.uuid4().hex[:12].upper()}",
        "workspace_id": workspace_id,
        "student_id": student_id,
        "sender_name": sender_name,
        "role": role,
        "message": message,
        "message_type": message_type or "text",
        "reply_to": reply_to,
        "timestamp": _now_iso(),
    }
    get_collection("workspace_chat_messages").insert_one(dict(doc))
    return doc


@router.post("/{workspace_id}/chat/messages")
def send_chat_message(
    workspace_id: str,
    request: ChatMessageCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Posts a chat message to the workspace."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)

    message = (request.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty.")

    doc = persist_chat_message(
        workspace_id,
        token_student_id,
        _student_display_name(token_student_id),
        member.get("role"),
        message,
        request.message_type,
        request.reply_to,
    )
    log_workspace_activity(
        workspace_id, token_student_id, "chat_message_sent", {"message_id": doc["message_id"]}
    )
    return {"status": "success", "message": _clean(doc)}


@router.get("/{workspace_id}/chat/messages")
def list_chat_messages(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[str] = Query(default=None, description="ISO timestamp — return messages older than this"),
    since: Optional[str] = Query(default=None, description="ISO timestamp — return messages newer than this"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns workspace chat history, chronological, for active members."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    query: Dict[str, Any] = {"workspace_id": workspace_id}
    if before:
        query["timestamp"] = {"$lt": before}
    elif since:
        query["timestamp"] = {"$gt": since}

    messages = list(get_collection("workspace_chat_messages").find(
        query,
        sort=[("timestamp", -1)],
        limit=limit,
    ))
    messages.reverse()

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(messages),
        "messages": [_clean(m) for m in messages],
    }


@router.delete("/{workspace_id}/chat/messages/{message_id}")
def delete_chat_message(
    workspace_id: str,
    message_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Deletes a chat message. Authors may delete their own; the owner may delete any."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)

    doc = get_collection("workspace_chat_messages").find_one({
        "workspace_id": workspace_id,
        "message_id": message_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found.")

    is_author = str(doc.get("student_id")) == token_student_id
    if not is_author and member.get("role") != "owner":
        raise HTTPException(status_code=403, detail="You can only delete your own messages.")

    get_collection("workspace_chat_messages").delete_one({"message_id": message_id})
    log_workspace_activity(
        workspace_id, token_student_id, "chat_message_deleted", {"message_id": message_id}
    )
    return {"status": "success", "message": f"Message '{message_id}' deleted."}


TASK_STATUSES = {"todo", "in_progress", "review", "done"}
TASK_PRIORITIES = {"low", "medium", "high"}
COMMENT_STATUSES = {"open", "resolved"}


def _notify(
    workspace_id: str,
    recipient_student_id: Optional[str],
    kind: str,
    message: str,
    actor_student_id: str,
    detail: Optional[dict] = None,
) -> Optional[str]:
    if not recipient_student_id or str(recipient_student_id) == str(actor_student_id):
        return None
    try:
        notification_id = f"NTF_{uuid.uuid4().hex[:12].upper()}"
        get_collection("workspace_notifications").insert_one({
            "notification_id": notification_id,
            "workspace_id": workspace_id,
            "recipient_student_id": str(recipient_student_id),
            "type": kind,
            "message": message,
            "actor_student_id": actor_student_id,
            "detail": detail or {},
            "status": "unread",
            "created_at": _now_iso(),
        })
        return notification_id
    except Exception as e:
        logger.warning("Failed to create workspace notification: %s", e)
        return None


# ==========================================
# 8. Version Restore
# ==========================================

@router.post("/{workspace_id}/files/{file_id}/versions/{version_id}/restore")
def restore_file_version(
    workspace_id: str,
    file_id: str,
    version_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Restores a historical version as the new current content. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    file_doc = _file_or_404(workspace_id, file_id)
    if file_doc.get("type") != "file":
        raise HTTPException(status_code=422, detail="Only files can be restored.")

    version = get_collection("workspace_file_versions").find_one({
        "workspace_id": workspace_id,
        "file_id": file_id,
        "version_id": version_id,
    })
    if not version:
        raise HTTPException(status_code=404, detail="Version not found.")

    content = version.get("content", "")
    version_number = _snapshot_version(
        workspace_id, file_doc, content, token_student_id,
        f"Restored from version {version.get('version_number')}",
    )
    now = _now_iso()
    get_collection("workspace_files").update_one(
        {"workspace_id": workspace_id, "file_id": file_id},
        {"$set": {
            "content": content,
            "size": len(content.encode("utf-8")),
            "version_count": version_number,
            "updated_by": token_student_id,
            "updated_at": now,
        }},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "version_restored",
        {"file_id": file_id, "restored_version": version.get("version_number"), "new_version": version_number},
    )
    return {
        "status": "success",
        "file_id": file_id,
        "version_number": version_number,
        "restored_from": version_id,
    }


# ==========================================
# 9. Inline Code Comments
# ==========================================

@router.get("/{workspace_id}/files/{file_id}/comments")
def list_comments(
    workspace_id: str,
    file_id: str,
    status: Optional[str] = Query(default="all", pattern="^(open|resolved|all)$"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists inline comments for a file."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)
    _file_or_404(workspace_id, file_id)

    query: Dict[str, Any] = {"workspace_id": workspace_id, "file_id": file_id}
    if status != "all":
        query["status"] = status

    comments = list(get_collection("workspace_code_comments").find(
        query, sort=[("created_at", 1)]
    ))
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "file_id": file_id,
        "total": len(comments),
        "comments": [_clean(c) for c in comments],
    }


@router.post("/{workspace_id}/files/{file_id}/comments")
def create_comment(
    workspace_id: str,
    file_id: str,
    request: CommentCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Adds an inline comment to a file."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)
    file_doc = _file_or_404(workspace_id, file_id)

    body = (request.body or "").strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment body must not be empty.")

    now = _now_iso()
    comment_id = f"CMT_{uuid.uuid4().hex[:12].upper()}"
    doc = {
        "comment_id": comment_id,
        "workspace_id": workspace_id,
        "file_id": file_id,
        "body": body,
        "line_start": request.line_start,
        "line_end": request.line_end if request.line_end is not None else request.line_start,
        "parent_comment_id": request.parent_comment_id,
        "author_student_id": token_student_id,
        "author_name": _student_display_name(token_student_id),
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    get_collection("workspace_code_comments").insert_one(dict(doc))

    _notify(
        workspace_id, file_doc.get("created_by"), "comment_added",
        f"{doc['author_name']} commented on '{file_doc.get('path')}'",
        token_student_id, {"file_id": file_id, "comment_id": comment_id},
    )
    log_workspace_activity(
        workspace_id, token_student_id, "comment_added",
        {"file_id": file_id, "comment_id": comment_id},
    )
    return {"status": "success", "comment": _clean(doc)}


@router.patch("/{workspace_id}/comments/{comment_id}")
def update_comment(
    workspace_id: str,
    comment_id: str,
    request: CommentUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Edits a comment body (author/owner) or resolves/reopens it (any member)."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)

    doc = get_collection("workspace_code_comments").find_one({
        "workspace_id": workspace_id, "comment_id": comment_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Comment not found.")

    updates: Dict[str, Any] = {}
    if request.body is not None:
        is_author = str(doc.get("author_student_id")) == token_student_id
        if not is_author and member.get("role") != "owner":
            raise HTTPException(status_code=403, detail="Only the author or owner can edit this comment.")
        updates["body"] = request.body.strip()
    if request.status is not None:
        if request.status not in COMMENT_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status. Use 'open' or 'resolved'.")
        updates["status"] = request.status

    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields were supplied.")

    updates["updated_at"] = _now_iso()
    get_collection("workspace_code_comments").update_one(
        {"workspace_id": workspace_id, "comment_id": comment_id}, {"$set": updates}
    )
    log_workspace_activity(
        workspace_id, token_student_id, "comment_updated", {"comment_id": comment_id, "fields": list(updates.keys())}
    )
    updated = get_collection("workspace_code_comments").find_one({"comment_id": comment_id})
    return {"status": "success", "comment": _clean(updated)}


@router.delete("/{workspace_id}/comments/{comment_id}")
def delete_comment(
    workspace_id: str,
    comment_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Deletes a comment. Author or owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)

    doc = get_collection("workspace_code_comments").find_one({
        "workspace_id": workspace_id, "comment_id": comment_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Comment not found.")

    is_author = str(doc.get("author_student_id")) == token_student_id
    if not is_author and member.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the author or owner can delete this comment.")

    get_collection("workspace_code_comments").delete_one({"workspace_id": workspace_id, "comment_id": comment_id})
    log_workspace_activity(workspace_id, token_student_id, "comment_deleted", {"comment_id": comment_id})
    return {"status": "success", "message": f"Comment '{comment_id}' deleted."}


# ==========================================
# 10. Task Board
# ==========================================

@router.get("/{workspace_id}/tasks")
def list_tasks(
    workspace_id: str,
    status: Optional[str] = Query(default="all"),
    assignee: Optional[str] = Query(default=None),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists tasks plus a status-grouped board view."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    query: Dict[str, Any] = {"workspace_id": workspace_id}
    if status and status != "all":
        query["status"] = status
    if assignee:
        query["assignee_student_id"] = assignee

    tasks = list(get_collection("workspace_tasks").find(query, sort=[("created_at", 1)]))
    board: Dict[str, List[dict]] = {state: [] for state in TASK_STATUSES}
    for task in tasks:
        board.setdefault(task.get("status", "todo"), []).append(_clean(task))

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(tasks),
        "tasks": [_clean(t) for t in tasks],
        "board": board,
    }


@router.post("/{workspace_id}/tasks")
def create_task(
    workspace_id: str,
    request: TaskCreateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Creates a task on the workspace board. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    status_value = request.status or "todo"
    priority_value = request.priority or "medium"
    if status_value not in TASK_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Use one of: {', '.join(sorted(TASK_STATUSES))}.")
    if priority_value not in TASK_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority. Use one of: {', '.join(sorted(TASK_PRIORITIES))}.")
    if request.assignee_student_id and not get_collection("workspace_members").find_one({
        "workspace_id": workspace_id, "student_id": request.assignee_student_id, "status": "active",
    }):
        raise HTTPException(status_code=404, detail="Assignee is not an active member of this workspace.")

    now = _now_iso()
    task_id = f"TASK_{uuid.uuid4().hex[:12].upper()}"
    doc = {
        "task_id": task_id,
        "workspace_id": workspace_id,
        "title": request.title,
        "description": request.description or "",
        "assignee_student_id": request.assignee_student_id,
        "status": status_value,
        "priority": priority_value,
        "due_date": request.due_date,
        "labels": request.labels or [],
        "created_by": token_student_id,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    get_collection("workspace_tasks").insert_one(dict(doc))

    _notify(
        workspace_id, request.assignee_student_id, "task_assigned",
        f"You were assigned task '{request.title}'",
        token_student_id, {"task_id": task_id},
    )
    log_workspace_activity(workspace_id, token_student_id, "task_created", {"task_id": task_id, "title": request.title})
    return {"status": "success", "task": _clean(doc)}


@router.patch("/{workspace_id}/tasks/{task_id}")
def update_task(
    workspace_id: str,
    task_id: str,
    request: TaskUpdateRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Updates a task (status, assignee, fields). Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    doc = get_collection("workspace_tasks").find_one({"workspace_id": workspace_id, "task_id": task_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found.")

    updates: Dict[str, Any] = {}
    if request.title is not None:
        updates["title"] = request.title
    if request.description is not None:
        updates["description"] = request.description
    if request.priority is not None:
        if request.priority not in TASK_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"Invalid priority. Use one of: {', '.join(sorted(TASK_PRIORITIES))}.")
        updates["priority"] = request.priority
    if request.due_date is not None:
        updates["due_date"] = request.due_date
    if request.labels is not None:
        updates["labels"] = request.labels
    if request.assignee_student_id is not None:
        if request.assignee_student_id and not get_collection("workspace_members").find_one({
            "workspace_id": workspace_id, "student_id": request.assignee_student_id, "status": "active",
        }):
            raise HTTPException(status_code=404, detail="Assignee is not an active member of this workspace.")
        updates["assignee_student_id"] = request.assignee_student_id
    if request.status is not None:
        if request.status not in TASK_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Use one of: {', '.join(sorted(TASK_STATUSES))}.")
        updates["status"] = request.status
        updates["completed_at"] = _now_iso() if request.status == "done" else None

    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields were supplied.")

    updates["updated_at"] = _now_iso()
    get_collection("workspace_tasks").update_one({"workspace_id": workspace_id, "task_id": task_id}, {"$set": updates})

    new_assignee = updates.get("assignee_student_id")
    if new_assignee and new_assignee != doc.get("assignee_student_id"):
        _notify(
            workspace_id, new_assignee, "task_assigned",
            f"You were assigned task '{doc.get('title')}'",
            token_student_id, {"task_id": task_id},
        )
    log_workspace_activity(workspace_id, token_student_id, "task_updated", {"task_id": task_id, "fields": list(updates.keys())})
    updated = get_collection("workspace_tasks").find_one({"workspace_id": workspace_id, "task_id": task_id})
    return {"status": "success", "task": _clean(updated)}


@router.delete("/{workspace_id}/tasks/{task_id}")
def delete_task(
    workspace_id: str,
    task_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Deletes a task. Owner/editor only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    result = get_collection("workspace_tasks").delete_one({"workspace_id": workspace_id, "task_id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found.")

    log_workspace_activity(workspace_id, token_student_id, "task_deleted", {"task_id": task_id})
    return {"status": "success", "message": f"Task '{task_id}' deleted."}


# ==========================================
# 11. AI Study Assistant
# ==========================================

@router.post("/{workspace_id}/assistant/ask")
def ask_assistant(
    workspace_id: str,
    request: AssistantAskRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Asks the workspace AI assistant, optionally with file/code context."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)

    context_parts: List[str] = []
    code = request.code
    if request.file_id:
        file_doc = get_collection("workspace_files").find_one({
            "workspace_id": workspace_id, "file_id": request.file_id, "status": "active",
        })
        if file_doc:
            context_parts.append(f"File: {file_doc.get('path')} ({file_doc.get('language')})")
            if code is None:
                code = file_doc.get("content")
    if code:
        context_parts.append(f"Code:\n{code[:4000]}")

    result = workspace_assistant.ask(request.question, context="\n\n".join(context_parts), student_id=token_student_id)
    reply = result.get("reply", "")

    question_doc = persist_chat_message(
        workspace_id,
        token_student_id,
        _student_display_name(token_student_id),
        member.get("role"),
        request.question,
        "ai_question",
    )
    doc = persist_chat_message(
        workspace_id, "WORKSPACE_AI", "AI Study Assistant", "ai", reply, "ai", question_doc["message_id"],
    )
    log_workspace_activity(
        workspace_id, token_student_id, "assistant_query", {"message_id": doc["message_id"]}
    )
    return {
        "status": "success",
        "reply": reply,
        "ai_status": result.get("status"),
        "message_id": doc["message_id"],
        "question": _clean(question_doc),
    }


# ==========================================
# 12. Contribution Analytics
# ==========================================

def _group_counts(collection_name: str, workspace_id: str, field: str) -> Dict[str, int]:
    try:
        pipeline = [
            {"$match": {"workspace_id": workspace_id}},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        return {str(doc["_id"]): doc["count"] for doc in get_collection(collection_name).aggregate(pipeline)}
    except Exception as e:
        logger.warning("Analytics aggregation failed for %s: %s", collection_name, e)
        return {}


@router.get("/{workspace_id}/analytics")
def get_workspace_analytics(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Aggregates per-member contribution and activity metrics."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    members = list(get_collection("workspace_members").find({
        "workspace_id": workspace_id, "status": "active",
    }))
    files_created = _group_counts("workspace_files", workspace_id, "created_by")
    file_edits = _group_counts("workspace_file_versions", workspace_id, "author_student_id")
    messages = _group_counts("workspace_chat_messages", workspace_id, "student_id")
    comments = _group_counts("workspace_code_comments", workspace_id, "author_student_id")

    tasks = list(get_collection("workspace_tasks").find({"workspace_id": workspace_id}))
    tasks_assigned: Dict[str, int] = {}
    tasks_completed: Dict[str, int] = {}
    for task in tasks:
        assignee = str(task.get("assignee_student_id") or "")
        if not assignee:
            continue
        tasks_assigned[assignee] = tasks_assigned.get(assignee, 0) + 1
        if task.get("status") == "done":
            tasks_completed[assignee] = tasks_completed.get(assignee, 0) + 1

    per_member = []
    for member in members:
        sid = str(member["student_id"])
        per_member.append({
            "student_id": sid,
            "name": _student_display_name(sid),
            "role": member.get("role"),
            "files_created": files_created.get(sid, 0),
            "file_edits": file_edits.get(sid, 0),
            "messages_sent": messages.get(sid, 0),
            "comments": comments.get(sid, 0),
            "tasks_assigned": tasks_assigned.get(sid, 0),
            "tasks_completed": tasks_completed.get(sid, 0),
            "last_seen_at": member.get("last_seen_at"),
        })
    per_member.sort(
        key=lambda item: item["files_created"] + item["file_edits"] + item["messages_sent"],
        reverse=True,
    )

    activity_by_day: Dict[str, int] = {}
    for entry in get_collection("workspace_activity_log").find(
        {"workspace_id": workspace_id}, sort=[("timestamp", -1)], limit=1000
    ):
        day = str(entry.get("timestamp", ""))[:10]
        if day:
            activity_by_day[day] = activity_by_day.get(day, 0) + 1
    timeline = [{"date": day, "count": activity_by_day[day]} for day in sorted(activity_by_day, reverse=True)][:14]

    total_files = get_collection("workspace_files").count_documents({
        "workspace_id": workspace_id, "status": "active", "type": "file",
    })

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "totals": {
            "members": len(members),
            "files": total_files,
            "versions": sum(file_edits.values()),
            "messages": sum(messages.values()),
            "comments": sum(comments.values()),
            "tasks": len(tasks),
        },
        "per_member": per_member,
        "timeline": timeline,
    }


# ==========================================
# 13. Notifications
# ==========================================

@router.get("/{workspace_id}/notifications")
def list_notifications(
    workspace_id: str,
    status: Optional[str] = Query(default="unread", pattern="^(unread|read|all)$"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Lists workspace notifications for the authenticated student."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    query: Dict[str, Any] = {"workspace_id": workspace_id, "recipient_student_id": token_student_id}
    if status != "all":
        query["status"] = status

    notifications = list(get_collection("workspace_notifications").find(
        query, sort=[("created_at", -1)]
    ))
    unread_count = get_collection("workspace_notifications").count_documents({
        "workspace_id": workspace_id, "recipient_student_id": token_student_id, "status": "unread",
    })
    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total": len(notifications),
        "unread_count": unread_count,
        "notifications": [_clean(n) for n in notifications],
    }


@router.post("/{workspace_id}/notifications/{notification_id}/read")
def mark_workspace_notification_read(
    workspace_id: str,
    notification_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Marks one notification as read."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    result = get_collection("workspace_notifications").update_one(
        {
            "workspace_id": workspace_id,
            "notification_id": notification_id,
            "recipient_student_id": token_student_id,
        },
        {"$set": {"status": "read", "read_at": _now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found.")

    return {"status": "success", "message": "Notification marked as read."}


@router.post("/{workspace_id}/notifications/read-all")
def mark_all_workspace_notifications_read(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Marks all of the student's unread notifications in this workspace as read."""
    _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    result = get_collection("workspace_notifications").update_many(
        {
            "workspace_id": workspace_id,
            "recipient_student_id": token_student_id,
            "status": "unread",
        },
        {"$set": {"status": "read", "read_at": _now_iso()}},
    )
    return {
        "status": "success",
        "message": f"Marked {result.modified_count} notification(s) as read.",
        "modified_count": result.modified_count,
    }


# ==========================================
# 14. Workspace Lifecycle
# ==========================================

@router.post("/{workspace_id}/unarchive")
def unarchive_workspace(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Reactivates an archived workspace. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"status": "active", "updated_at": _now_iso()}},
    )
    log_workspace_activity(workspace_id, token_student_id, "workspace_unarchived", {})
    return {"status": "success", "message": f"Workspace '{workspace_id}' reactivated."}


@router.post("/{workspace_id}/transfer-ownership")
def transfer_ownership(
    workspace_id: str,
    request: OwnershipTransferRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Transfers workspace ownership to another active member. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    new_owner = request.new_owner_student_id
    if new_owner == token_student_id:
        raise HTTPException(status_code=422, detail="You are already the owner.")

    target = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id, "student_id": new_owner, "status": "active",
    })
    if not target:
        raise HTTPException(status_code=404, detail="New owner is not an active member of this workspace.")

    now = _now_iso()
    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "student_id": new_owner},
        {"$set": {"role": "owner", "updated_at": now}},
    )
    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "student_id": token_student_id},
        {"$set": {"role": "editor", "updated_at": now}},
    )
    get_collection("workspaces").update_one(
        {"workspace_id": workspace_id},
        {"$set": {"owner_student_id": new_owner, "updated_at": now}},
    )
    _notify(workspace_id, new_owner, "ownership_transferred", "You are now the workspace owner.", token_student_id, {})
    log_workspace_activity(workspace_id, token_student_id, "ownership_transferred", {"new_owner": new_owner})
    return {"status": "success", "message": f"Ownership transferred to '{new_owner}'.", "new_owner": new_owner}


@router.delete("/{workspace_id}/purge")
def purge_workspace(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Permanently deletes a workspace and all of its data. Owner only."""
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, MANAGER_ROLES)

    deleted: Dict[str, int] = {}
    for collection_name in [
        "workspace_members",
        "workspace_invites",
        "workspace_join_keys",
        "workspace_files",
        "workspace_file_versions",
        "workspace_chat_messages",
        "workspace_code_comments",
        "workspace_tasks",
        "workspace_activity_log",
        "workspace_notifications",
    ]:
        try:
            deleted[collection_name] = get_collection(collection_name).delete_many(
                {"workspace_id": workspace_id}
            ).deleted_count
        except Exception as e:
            logger.warning("Purge failed for %s: %s", collection_name, e)

    get_collection("workspaces").delete_one({"workspace_id": workspace_id})
    return {"status": "success", "message": f"Workspace '{workspace_id}' purged.", "deleted": deleted}


# ==========================================
# 15. ZIP export
# ==========================================

_ZIP_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._/-]")


def _zip_entry_name(entry: dict) -> str:
    """Turn a stored workspace path into a safe, archive-relative path."""
    raw = str(entry.get("path") or entry.get("name") or "").replace("\\", "/").strip("/")
    parts = [part for part in raw.split("/") if part not in ("", ".", "..")]
    if not parts:
        return ""
    parts = [_ZIP_UNSAFE_CHARS.sub("_", part)[:160] or "_" for part in parts]
    return "/".join(parts)


def _archive_filename(workspace: dict) -> str:
    slug = _ZIP_UNSAFE_CHARS.sub("_", str(workspace.get("name") or "workspace")).strip("._") or "workspace"
    return f"{slug[:60]}_{workspace.get('workspace_id', 'workspace')}.zip"


@router.get("/{workspace_id}/export")
def export_workspace_zip(
    workspace_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Download every file and folder in the workspace as a ZIP archive."""
    workspace = _require_workspace(workspace_id)
    _require_member(workspace_id, token_student_id)

    entries = list(
        get_collection("workspace_files")
        .find({"workspace_id": workspace_id, "status": "active"})
        .sort("path", 1)
    )

    buffer = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            name = _zip_entry_name(entry)
            if not name:
                continue
            if name in used:
                stem, dot, ext = name.partition(".")
                suffix = 1
                while f"{stem}_{suffix}{dot}{ext}" in used:
                    suffix += 1
                name = f"{stem}_{suffix}{dot}{ext}"
            used.add(name)

            if entry.get("type") == "folder":
                archive.writestr(f"{name}/", "")
            else:
                archive.writestr(name, str(entry.get("content") or ""))

        if not used:
            archive.writestr(
                "README.txt",
                f"Workspace: {workspace.get('name', workspace_id)}\n"
                f"ID: {workspace_id}\n\nThis workspace does not contain any files yet.\n",
            )

    buffer.seek(0)
    log_workspace_activity(workspace_id, token_student_id, "export_zip", {"file_count": len(entries)})
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{_archive_filename(workspace)}"',
            "Content-Length": str(buffer.getbuffer().nbytes),
        },
    )


# ==========================================
# 16. Sandboxed Code Run
# ==========================================

def _code_run_enabled() -> bool:
    return os.getenv("WORKSPACE_CODE_RUN_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


_MAX_ACTIVE_CODE_CHARS = 20000


def _java_sources(workspace_id: str, active_file_id: Optional[str], active_code: str):
    """Collect the workspace's .java files, overlaying the editor's unsaved buffer."""
    docs = list(
        get_collection("workspace_files").find(
            {"workspace_id": workspace_id, "status": "active", "type": "file"}
        )
    )

    sources: Dict[str, str] = {}
    active_name: Optional[str] = None

    for doc in docs:
        name = str(doc.get("name") or "").strip()
        if not name or not name.lower().endswith(".java"):
            continue
        is_active = bool(active_file_id) and doc.get("file_id") == active_file_id
        if is_active:
            active_name = name
            sources[name] = active_code
        else:
            sources[name] = str(doc.get("content") or "")

    if not sources and active_code.strip():
        sources["Main.java"] = active_code
        active_name = "Main.java"

    return sources, active_name


@router.post("/{workspace_id}/run")
def run_workspace_code(
    workspace_id: str,
    request: CodeRunRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Compile the workspace's Java sources in a sandbox and run the entry point.

    Compilation always uses the real ``javac`` so the diagnostics read exactly like a
    terminal in VS Code.  Execution only happens when ``WORKSPACE_CODE_RUN_ENABLED``
    is true; otherwise the request is compile-only.
    """
    _require_workspace(workspace_id)
    member = _require_member(workspace_id, token_student_id)
    _require_role(member, WRITE_ROLES)

    code = request.code or ""
    if len(code) > _MAX_ACTIVE_CODE_CHARS:
        raise HTTPException(status_code=413, detail="Code exceeds the 20,000 character limit.")
    if not code.strip():
        raise HTTPException(status_code=400, detail="Nothing to run: the file is empty.")

    sources, active_name = _java_sources(workspace_id, request.file_id, code)
    if not sources:
        raise HTTPException(status_code=400, detail="No .java file to compile. Create a Java file to run code.")

    execute = _code_run_enabled()
    scope = "project" if len(sources) > 1 else "file"
    main_class = code_sandbox.detect_main_class(sources)
    result = code_sandbox.compile_and_run(
        sources,
        main_class=main_class,
        stdin_data=request.stdin or "",
        execute=execute,
    )

    # Independent files in one workspace may legitimately declare the same class, which
    # makes a whole-project compile fail. Fall back to compiling just the open file.
    if not result.get("compiled") and len(sources) > 1 and active_name and active_name in sources:
        single = {active_name: sources[active_name]}
        fallback = code_sandbox.compile_and_run(
            single,
            main_class=code_sandbox.detect_main_class(single),
            stdin_data=request.stdin or "",
            execute=execute,
        )
        if fallback.get("compiled"):
            result = fallback
            scope = "file"

    log_workspace_activity(
        workspace_id,
        token_student_id,
        "code_run",
        {
            "compiled": bool(result.get("compiled")),
            "scope": scope,
            "exit_code": result.get("exit_code"),
        },
    )

    payload: Dict[str, Any] = {"status": "success", "execution_enabled": execute, "scope": scope, **result}
    if not execute:
        payload["message"] = "Compilation only — set WORKSPACE_CODE_RUN_ENABLED=true to execute programs."
    return payload
