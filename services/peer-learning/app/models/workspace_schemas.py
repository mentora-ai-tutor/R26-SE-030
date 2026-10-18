from typing import List, Optional
from pydantic import BaseModel, Field


# ==========================================
# 1. Workspace Schemas
# ==========================================

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Workspace/project room name")
    description: Optional[str] = None
    visibility: Optional[str] = Field(default="private", description="private | invite")


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    visibility: Optional[str] = None
    status: Optional[str] = Field(default=None, description="active | archived")


class WorkspaceResponse(BaseModel):
    status: str
    workspace: dict


class WorkspaceListResponse(BaseModel):
    status: str
    total: int
    workspaces: List[dict]


# ==========================================
# 2. Membership Schemas
# ==========================================

class MemberAddRequest(BaseModel):
    student_id: str
    role: Optional[str] = Field(default="editor", description="owner | editor | viewer")


class MemberRoleUpdateRequest(BaseModel):
    role: str = Field(..., description="owner | editor | viewer")


class MemberListResponse(BaseModel):
    status: str
    workspace_id: str
    total: int
    members: List[dict]


# ==========================================
# 3. Join Key & Invite Schemas
# ==========================================

class JoinKeyCreateRequest(BaseModel):
    role: Optional[str] = Field(default="editor", description="owner | editor | viewer")
    expires_in_hours: Optional[int] = Field(default=None, description="Omit for a non-expiring key")
    max_uses: Optional[int] = Field(default=None, description="Omit for unlimited uses")


class JoinWorkspaceRequest(BaseModel):
    join_key: str


class InviteCreateRequest(BaseModel):
    role: Optional[str] = Field(default="editor", description="owner | editor | viewer")
    expires_in_hours: Optional[int] = Field(default=168, description="Default 7 days")
    max_uses: Optional[int] = Field(default=1)


class InviteAcceptRequest(BaseModel):
    token: str


# ==========================================
# 4. File System & Editor Schemas
# ==========================================

class FileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    parent_path: Optional[str] = Field(default="", description="Folder path relative to the workspace root")
    type: Optional[str] = Field(default="file", description="file | folder")
    content: Optional[str] = ""
    language: Optional[str] = Field(default="java", description="Editor language id, e.g. java")


class FileContentUpdateRequest(BaseModel):
    content: str
    message: Optional[str] = Field(default=None, description="Optional version message")
    base_version: Optional[int] = Field(default=None, description="Optional optimistic-concurrency check")


class FileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    parent_path: Optional[str] = None
    language: Optional[str] = None


# ==========================================
# 5. Workspace Chat Schemas
# ==========================================

class ChatMessageCreateRequest(BaseModel):
    message: str = Field(..., min_length=1)
    message_type: Optional[str] = Field(default="text", description="text | code | system")
    reply_to: Optional[str] = Field(default=None, description="message_id being replied to")


# ==========================================
# 6. Inline Code Comment Schemas
# ==========================================

class CommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1)
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    parent_comment_id: Optional[str] = None


class CommentUpdateRequest(BaseModel):
    body: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = Field(default=None, description="open | resolved")


# ==========================================
# 7. Task Board Schemas
# ==========================================

class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    assignee_student_id: Optional[str] = None
    status: Optional[str] = Field(default="todo", description="todo | in_progress | review | done")
    priority: Optional[str] = Field(default="medium", description="low | medium | high")
    due_date: Optional[str] = None
    labels: Optional[List[str]] = None


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    assignee_student_id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    labels: Optional[List[str]] = None


# ==========================================
# 8. AI Assistant & Code Run Schemas
# ==========================================

class AssistantAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    file_id: Optional[str] = None
    code: Optional[str] = None


class CodeRunRequest(BaseModel):
    code: str = Field(..., min_length=1)
    stdin: Optional[str] = ""
    file_id: Optional[str] = None


# ==========================================
# 9. Lifecycle Schemas
# ==========================================

class OwnershipTransferRequest(BaseModel):
    new_owner_student_id: str
