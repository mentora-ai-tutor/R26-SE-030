from typing import List, Literal, Optional

from pydantic import BaseModel, Field

WorkspaceRole = Literal["leader", "member", "viewer"]
WorkspaceStatus = Literal["active", "archived", "closed"]
TaskStatus = Literal["todo", "in_progress", "review", "done"]
TaskPriority = Literal["low", "medium", "high"]
CodeLanguage = Literal["java", "python", "javascript", "json", "markdown", "text"]


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    visibility: Literal["private", "invite"] = "private"
    peer_pool_id: Optional[str] = Field(default=None, max_length=100)
    project_id: Optional[str] = Field(default=None, max_length=100)


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    visibility: Optional[Literal["private", "invite"]] = None
    status: Optional[WorkspaceStatus] = None


class WorkspaceInviteRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=100)
    role: Literal["member", "viewer"] = "member"


class WorkspaceMemberUpdateRequest(BaseModel):
    role: Literal["member", "viewer"] = "member"


class OwnershipTransferRequest(BaseModel):
    new_owner_student_id: str = Field(..., min_length=1, max_length=100)


class JoinKeyCreateRequest(BaseModel):
    expires_in_hours: Optional[int] = Field(default=24, ge=1, le=168)
    max_uses: Optional[int] = Field(default=1, ge=1, le=100)
    role: Literal["member", "viewer"] = "member"


class JoinByKeyRequest(BaseModel):
    join_key: str = Field(
        ...,
        min_length=14,
        max_length=14,
        pattern=r"^[A-Za-z0-9]{4}(?:-[A-Za-z0-9]{4}){2}$",
    )


class FileCreateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    path: Optional[str] = Field(default=None, max_length=512)
    parent_path: Optional[str] = Field(default=None, max_length=512)
    type: Literal["file", "folder"] = "file"
    content: str = Field(default="", max_length=1_048_576)
    language: Optional[str] = Field(default="java", max_length=32)


class FileUpdateRequest(BaseModel):
    content: Optional[str] = Field(default=None, max_length=1_048_576)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    language: Optional[str] = Field(default=None, max_length=32)


class FileMoveRequest(BaseModel):
    new_path: str = Field(..., min_length=1, max_length=512)


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20_000)
    message_type: Literal["text", "code", "system"] = "text"
    reply_to: Optional[str] = Field(default=None, max_length=100)
    mentions: List[str] = Field(default_factory=list, max_length=50)
    file_id: Optional[str] = Field(default=None, max_length=100)
    line_number: Optional[int] = Field(default=None, ge=1)
    code_language: Optional[CodeLanguage] = None


class ChatMessageUpdateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20_000)


class CommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=10_000)
    file_id: Optional[str] = Field(default=None, max_length=100)
    line_start: Optional[int] = Field(default=None, ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    parent_comment_id: Optional[str] = Field(default=None, max_length=100)


class CommentUpdateRequest(BaseModel):
    body: Optional[str] = Field(default=None, min_length=1, max_length=10_000)
    status: Optional[Literal["open", "resolved"]] = None


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    assignee_student_id: Optional[str] = Field(default=None, max_length=100)
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_date: Optional[str] = Field(default=None, max_length=40)
    labels: Optional[List[str]] = Field(default=None, max_length=10)
    file_id: Optional[str] = Field(default=None, max_length=100)


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    assignee_student_id: Optional[str] = Field(default=None, max_length=100)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[str] = Field(default=None, max_length=40)
    labels: Optional[List[str]] = Field(default=None, max_length=10)
    file_id: Optional[str] = Field(default=None, max_length=100)


class AssistantAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    file_id: Optional[str] = Field(default=None, max_length=100)
    code: Optional[str] = Field(default=None, max_length=20_000)
    use_rag: bool = True


class CodeRunRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=200_000)
    stdin: Optional[str] = Field(default="", max_length=10_000)
    file_id: Optional[str] = Field(default=None, max_length=100)
    language: str = Field(default="java", max_length=16)
