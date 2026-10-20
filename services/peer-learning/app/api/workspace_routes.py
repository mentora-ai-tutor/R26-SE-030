import hashlib
import io
import logging
import posixpath
import re
import secrets
import stat
import string
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pymongo.errors import DuplicateKeyError

from app.agents.workspace_assistant import ask_assistant, java_sandbox
from app.api.student_routes import verify_jwt_student
from app.models.workspace_schemas import (
    AssistantAskRequest,
    ChatMessageRequest,
    ChatMessageUpdateRequest,
    CodeRunRequest,
    CommentCreateRequest,
    CommentUpdateRequest,
    FileCreateRequest,
    FileMoveRequest,
    FileUpdateRequest,
    JoinByKeyRequest,
    JoinKeyCreateRequest,
    OwnershipTransferRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceInviteRequest,
    WorkspaceMemberUpdateRequest,
    WorkspaceUpdateRequest,
)
from app.services.mongodb import get_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/workspaces', tags=['Project Workspaces'])

MAX_WORKSPACE_ENTRIES = 500
MAX_WORKSPACE_FILE_BYTES = 1_048_576
MAX_WORKSPACE_TOTAL_BYTES = 10_485_760
MAX_WORKSPACE_ARCHIVE_BYTES = 10_485_760
MAX_VERSIONS_PER_FILE = 50
TRASH_RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _workspace_response(document: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in document.items() if key != '_id'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish_workspace_event(workspace_id: str, event: Dict[str, Any]) -> None:
    try:
        from app.api.workspace_ws import manager

        manager.publish_json(workspace_id, event)
    except Exception:
        logger.exception('Failed to publish workspace event %s', event.get('type'))


def _publish_file_tree_event(
    workspace_id: str,
    action: str,
    files: List[Dict[str, Any]],
    student_id: str,
    **metadata,
) -> None:
    _publish_workspace_event(
        workspace_id,
        {
            'type': 'FILE_TREE',
            'action': action,
            'student_id': student_id,
            'files': [
                {
                    key: file.get(key)
                    for key in ('id', 'name', 'path', 'type', 'updated_at')
                    if key in file
                }
                for file in files
            ],
            **metadata,
        },
    )


def _check_rate_limit(scope: str, value: str, limit=5, window_seconds=60):
    now = datetime.now(timezone.utc)
    window_start = int(now.timestamp() // window_seconds) * window_seconds
    counter_id = hashlib.sha256(
        f'{scope}:{value}:{window_start}'.encode('utf-8')
    ).hexdigest()
    counter = get_collection('workspace_join_attempts')
    try:
        try:
            counter.update_one(
                {'_id': counter_id},
                {
                    '$inc': {'attempts': 1},
                    '$setOnInsert': {
                        'expires_at': datetime.fromtimestamp(
                            window_start + (2 * window_seconds),
                            timezone.utc,
                        )
                    },
                },
                upsert=True,
            )
        except DuplicateKeyError:
            counter.update_one({'_id': counter_id}, {'$inc': {'attempts': 1}})
        attempt = counter.find_one({'_id': counter_id}, {'attempts': 1})
    except Exception as error:
        logger.exception('Workspace join rate limiter is unavailable')
        raise HTTPException(status_code=503, detail='Join service is temporarily unavailable.') from error
    if not attempt or attempt.get('attempts', 0) > limit:
        raise HTTPException(status_code=429, detail='Too many attempts. Please try again later.')


def _log_join_failure(student_id: str, client_ip: str, reason: str) -> None:
    logger.warning(
        'Workspace join attempt rejected student=%s ip=%s reason=%s',
        student_id,
        client_ip,
        reason,
    )


def _normalize_role(role: Optional[str]) -> str:
    return {
        'owner': 'leader',
        'leader': 'leader',
        'editor': 'member',
        'member': 'member',
        'viewer': 'viewer',
    }.get(role or '', 'viewer')


def _is_leader(role: str) -> bool:
    return role in {'owner', 'leader'}


def _parse_expiry(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return None


def _record_workspace_activity(
    workspace_id: str,
    student_id: str,
    action: str,
    target=None,
) -> None:
    activity = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'student_id': student_id,
        'action': action,
        'target': target,
        'timestamp': _now(),
    }
    try:
        get_collection('activity_log').insert_one(activity)
    except Exception:
        logger.exception('Failed to record workspace activity %s', action)
        return
    _publish_workspace_event(workspace_id, {'type': 'ACTIVITY', 'activity': activity})


def _notify_student(
    workspace_id: str,
    student_id: str,
    notification_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    notification = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'student_id': student_id,
        'type': notification_type,
        'status': 'unread',
        'created_at': _now(),
        **(payload or {}),
    }
    try:
        get_collection('workspace_notifications').insert_one(notification)
    except Exception:
        logger.exception('Failed to create workspace notification %s', notification_type)
        return
    from app.api.workspace_ws import manager

    try:
        manager.publish_student_json(
            workspace_id,
            student_id,
            {'type': 'NOTIFICATION', 'notification': _workspace_response(notification)},
        )
    except Exception:
        logger.exception('Failed to publish workspace notification')


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _generate_join_key() -> str:
    chars = string.ascii_uppercase + string.digits

    def part() -> str:
        return ''.join(secrets.choice(chars) for _ in range(4))

    return part() + '-' + part() + '-' + part()


# ---------------------------------------------------------------------------
# Path validation and file-tree helpers
# ---------------------------------------------------------------------------


def _validate_path(path):
    if not isinstance(path, str) or not path.strip():
        raise HTTPException(status_code=422, detail='Path cannot be blank.')
    path = path.strip()
    if len(path) > 512 or path.startswith(('/', '\\')) or '\\' in path:
        raise HTTPException(status_code=422, detail='Invalid path.')
    parts = path.split('/')
    if any(
        not part
        or part in {'.', '..'}
        or len(part) > 100
        or part.endswith(('.', ' '))
        or re.match(r'^[A-Za-z]:', part)
        or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
        for part in parts
    ):
        raise HTTPException(status_code=422, detail='Invalid path.')
    return '/'.join(parts)


def _parent_paths(path: str):
    parent = posixpath.dirname(path)
    while parent:
        yield parent
        parent = posixpath.dirname(parent)


def _active_workspace_files(workspace_id: str) -> List[Dict[str, Any]]:
    try:
        files = list(get_collection('workspace_files').find({'workspace_id': workspace_id}))
    except Exception as error:
        logger.exception('Failed to load workspace file tree %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not load workspace files.') from error
    for file in files:
        if not file.get('path') and file.get('name'):
            file['path'] = file['name']
    return files


def _file_path(document: Dict[str, Any]) -> str:
    return document.get('path') or document.get('name', '')


def _normalize_file(document: Dict[str, Any]) -> Dict[str, Any]:
    if not document.get('path') and document.get('name'):
        document['path'] = document['name']
    return document


def _workspace_file_by_id(workspace_id: str, file_id: str) -> Dict[str, Any]:
    document = _find_workspace_record('workspace_files', workspace_id, file_id)
    if not document:
        raise HTTPException(status_code=404, detail='Workspace file not found.')
    return _normalize_file(document)


def _resolve_file_path(name: str, parent_path: Optional[str] = None) -> str:
    clean_name = _validate_path(name)
    if '/' in clean_name:
        raise HTTPException(status_code=422, detail='File or folder name must be a single path segment.')
    if parent_path:
        clean_parent = _validate_path(parent_path)
        return _validate_path(posixpath.join(clean_parent, clean_name))
    return clean_name


def _check_path_available(
    workspace_id: str,
    path: str,
    exclude_ids: Optional[set] = None,
) -> None:
    exclude_ids = exclude_ids or set()
    if any(
        document.get('id') not in exclude_ids and _file_path(document) == path
        for document in _active_workspace_files(workspace_id)
    ):
        raise HTTPException(status_code=409, detail='A file or folder already exists at this path.')


def _check_parent_folder(
    workspace_id: str,
    path: str,
    allowed_paths: Optional[set] = None,
) -> None:
    parent = posixpath.dirname(path)
    if not parent:
        return
    if allowed_paths and parent in allowed_paths:
        return
    folder = next(
        (
            document
            for document in _active_workspace_files(workspace_id)
            if _file_path(document) == parent and document.get('type') == 'folder'
        ),
        None,
    )
    if not folder:
        raise HTTPException(status_code=404, detail='Parent folder not found.')


def _check_workspace_quota(
    workspace_id: str,
    additions: List[Dict[str, Any]],
    excluded_ids: Optional[set] = None,
) -> None:
    excluded_ids = excluded_ids or set()
    current = [
        document
        for document in _active_workspace_files(workspace_id)
        if document.get('id') not in excluded_ids
    ]
    if len(current) + len(additions) > MAX_WORKSPACE_ENTRIES:
        raise HTTPException(status_code=413, detail='Workspace file and folder limit reached.')
    current_size = sum(
        len((document.get('content') or '').encode('utf-8'))
        for document in current
        if document.get('type', 'file') == 'file'
    )
    added_size = 0
    for document in additions:
        if document.get('type', 'file') == 'file':
            size = len((document.get('content') or '').encode('utf-8'))
            if size > MAX_WORKSPACE_FILE_BYTES:
                raise HTTPException(status_code=413, detail='File exceeds the 1 MiB limit.')
            added_size += size
    if current_size + added_size > MAX_WORKSPACE_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail='Workspace content exceeds the 10 MiB limit.')


def _insert_workspace_files(documents: List[Dict[str, Any]], workspace_id: str) -> None:
    if not documents:
        return
    try:
        get_collection('workspace_files').insert_many(documents, ordered=True)
    except Exception as error:
        logger.exception('Failed to save workspace files for %s', workspace_id)
        try:
            get_collection('workspace_files').delete_many(
                {
                    'workspace_id': workspace_id,
                    'id': {'$in': [document['id'] for document in documents]},
                }
            )
        except Exception:
            logger.exception('Failed to roll back workspace file insert')
        if isinstance(error, DuplicateKeyError):
            raise HTTPException(
                status_code=409,
                detail='A file or folder already exists at this path.',
            ) from error
        raise HTTPException(status_code=500, detail='Could not save workspace files.') from error


def _trash_workspace_files(
    workspace_id: str,
    files: List[Dict[str, Any]],
    student_id: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    trash = {
        'trash_id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'items': [_workspace_response(document) for document in files],
        'deleted_by': student_id,
        'deleted_at': now.isoformat(),
        'expires_at': now + timedelta(days=TRASH_RETENTION_DAYS),
    }
    try:
        get_collection('workspace_trash').insert_one(trash)
        get_collection('workspace_files').delete_many(
            {'workspace_id': workspace_id, 'id': {'$in': [item['id'] for item in files]}}
        )
    except Exception as error:
        logger.exception('Failed to move workspace files to trash')
        raise HTTPException(status_code=500, detail='Could not delete workspace files.') from error
    return trash


# ---------------------------------------------------------------------------
# Access control helpers
# ---------------------------------------------------------------------------


def _workspace_access(workspace_id: str, student_id: str) -> tuple:
    try:
        collection = get_collection('workspaces')
        workspace = collection.find_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id}
        )
        if workspace:
            return workspace, 'leader'
        workspace = collection.find_one(
            {'workspace_id': workspace_id, 'members.student_id': student_id}
        )
    except Exception as error:
        logger.exception('Failed to verify access to workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not access workspace.') from error
    if not workspace:
        raise HTTPException(status_code=404, detail='Workspace not found.')
    member = next(
        (
            member
            for member in workspace.get('members', [])
            if member.get('student_id') == student_id
        ),
        None,
    )
    return workspace, _normalize_role(member.get('role') if member else None)


def _require_editor(workspace_id: str, student_id: str) -> Dict[str, Any]:
    workspace, role = _workspace_access(workspace_id, student_id)
    if role not in {'leader', 'member'}:
        raise HTTPException(status_code=403, detail='Workspace member access is required.')
    if workspace.get('status', 'active') != 'active':
        raise HTTPException(status_code=403, detail='Workspace is read-only.')
    return workspace


def _student_profiles(student_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    unique_ids = list({sid for sid in student_ids if sid})
    if not unique_ids:
        return {}
    try:
        return {
            document.get('student_id'): {
                'name': document.get('name'),
                'email': document.get('email'),
            }
            for document in get_collection('students').find(
                {'student_id': {'$in': unique_ids}},
                {'_id': 0, 'student_id': 1, 'name': 1, 'email': 1},
            )
        }
    except Exception:
        logger.debug('Failed to load student profiles', exc_info=True)
        return {}


def _workspace_members(workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    members = list(workspace.get('members', []))
    for member in members:
        member['role'] = _normalize_role(member.get('role'))
    owner_id = workspace['owner_student_id']
    if not any(member.get('student_id') == owner_id for member in members):
        members.insert(0, {'student_id': owner_id, 'role': 'leader'})
    profiles = _student_profiles([member.get('student_id') for member in members])
    for member in members:
        profile = profiles.get(member.get('student_id')) or {}
        member['name'] = profile.get('name')
        member['email'] = profile.get('email')
        member['color'] = _color_for(member.get('student_id') or '')
    return members


def _color_for(student_id: str) -> str:
    palette = [
        '#2563eb', '#dc2626', '#059669', '#d97706',
        '#7c3aed', '#db2777', '#0891b2', '#65a30d',
    ]
    if not student_id:
        return palette[0]
    index = int.from_bytes(hashlib.sha256(student_id.encode('utf-8')).digest()[:4], 'big')
    return palette[index % len(palette)]


# ---------------------------------------------------------------------------
# Generic record helpers
# ---------------------------------------------------------------------------


def _find_workspace_record(collection_name: str, workspace_id: str, record_id: str):
    try:
        return get_collection(collection_name).find_one(
            {'workspace_id': workspace_id, 'id': record_id}
        )
    except Exception as error:
        logger.exception('Failed to find %s record %s', collection_name, record_id)
        raise HTTPException(status_code=500, detail='Could not load workspace data.') from error


def _list_workspace_records(collection_name: str, workspace_id: str) -> List[Dict[str, Any]]:
    try:
        return [
            _workspace_response(document)
            for document in get_collection(collection_name)
            .find({'workspace_id': workspace_id})
            .sort('created_at', 1)
        ]
    except Exception as error:
        logger.exception('Failed to list %s for workspace %s', collection_name, workspace_id)
        raise HTTPException(status_code=500, detail='Could not load workspace data.') from error


def _insert_workspace_record(collection_name: str, document: Dict[str, Any]) -> Dict[str, Any]:
    try:
        get_collection(collection_name).insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(status_code=409, detail='Workspace data already exists.') from error
    except Exception as error:
        logger.exception(
            'Failed to insert %s record for workspace %s',
            collection_name,
            document.get('workspace_id'),
        )
        raise HTTPException(status_code=500, detail='Could not save workspace data.') from error
    return _workspace_response(document)


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------


def _validate_chat_message_relations(
    workspace_id: str,
    student_id: str,
    request: ChatMessageRequest,
) -> List[str]:
    if request.reply_to and not _find_workspace_record(
        'workspace_chat', workspace_id, request.reply_to
    ):
        raise HTTPException(status_code=404, detail='Reply target not found.')
    if request.file_id:
        file = _workspace_file_by_id(workspace_id, request.file_id)
        if file.get('type', 'file') != 'file':
            raise HTTPException(status_code=422, detail='Chat references must target a file.')
    elif request.line_number is not None:
        raise HTTPException(status_code=422, detail='line_number requires a file_id.')
    return _validate_chat_mentions(workspace_id, student_id, request.mentions)


def _validate_chat_mentions(
    workspace_id: str,
    student_id: str,
    mentioned_student_ids: List[str],
) -> List[str]:
    workspace, _ = _workspace_access(workspace_id, student_id)
    member_ids = {member.get('student_id') for member in _workspace_members(workspace)}
    mentions = list(dict.fromkeys(mentioned_student_ids))
    if len(mentions) > 50 or any(
        not isinstance(mentioned_id, str)
        or not mentioned_id.strip()
        or mentioned_id not in member_ids
        for mentioned_id in mentions
    ):
        raise HTTPException(status_code=422, detail='Mentions must identify workspace members.')
    return mentions


def _persist_chat_mentions(
    workspace_id: str,
    message_id: str,
    sender_id: str,
    mentioned_student_ids: List[str],
) -> None:
    for mentioned_id in mentioned_student_ids:
        if mentioned_id == sender_id:
            continue
        _notify_student(
            workspace_id,
            mentioned_id,
            'chat_mention',
            {'message_id': message_id, 'created_by': sender_id},
        )


def _save_workspace_chat_message(
    document: Dict[str, Any],
    mentioned_student_ids: List[str],
) -> Dict[str, Any]:
    saved = _insert_workspace_record('workspace_chat', document)
    try:
        _persist_chat_mentions(
            document['workspace_id'],
            document['id'],
            document['student_id'],
            mentioned_student_ids,
        )
    except Exception:
        try:
            get_collection('workspace_chat').delete_one(
                {'workspace_id': document['workspace_id'], 'id': document['id']}
            )
        except Exception:
            logger.exception('Failed to roll back workspace chat message')
        raise
    _publish_workspace_event(document['workspace_id'], saved)
    return saved


def _workspace_chat_unread_count(workspace_id: str, student_id: str) -> int:
    query: Dict[str, Any] = {
        'workspace_id': workspace_id,
        'student_id': {'$ne': student_id},
    }
    try:
        marker = get_collection('workspace_chat_reads').find_one(
            {'workspace_id': workspace_id, 'student_id': student_id}
        )
        if marker and marker.get('last_read_at'):
            query['created_at'] = {'$gt': marker['last_read_at']}
        return get_collection('workspace_chat').count_documents(query)
    except Exception as error:
        logger.exception('Failed to count unread workspace chat messages')
        raise HTTPException(status_code=500, detail='Could not load unread chat count.') from error


def _chat_document_from_request(
    workspace_id: str,
    student_id: str,
    request: ChatMessageRequest,
    mentions: List[str],
) -> Dict[str, Any]:
    from app.api.workspace_ws import _color_for as ws_color_for
    from app.api.workspace_ws import _student_name

    now = _now()
    return {
        'id': uuid.uuid4().hex,
        'type': 'CHAT_MESSAGE',
        'workspace_id': workspace_id,
        'student_id': student_id,
        'name': _student_name(student_id),
        'color': ws_color_for(student_id),
        'message': request.message.strip(),
        'message_type': request.message_type,
        'reply_to': request.reply_to,
        'mentions': mentions,
        'file_id': request.file_id,
        'line_number': request.line_number,
        'code_language': request.code_language,
        'timestamp': now,
        'created_at': now,
    }


# ---------------------------------------------------------------------------
# File version snapshots
# ---------------------------------------------------------------------------


def _snapshot_file_version(
    workspace_id: str,
    file: Dict[str, Any],
    student_id: str,
) -> None:
    """Persist an automatic snapshot for a file after its content changed."""
    version = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'file_id': file['id'],
        'path': _file_path(file),
        'name': file.get('name'),
        'content': file.get('content') or '',
        'size': len((file.get('content') or '').encode('utf-8')),
        'student_id': student_id,
        'created_at': _now(),
    }
    try:
        versions = get_collection('file_versions')
        versions.insert_one(version)
        total = versions.count_documents({'workspace_id': workspace_id, 'file_id': file['id']})
        if total > MAX_VERSIONS_PER_FILE:
            surplus = (
                versions.find({'workspace_id': workspace_id, 'file_id': file['id']})
                .sort('created_at', 1)
                .limit(total - MAX_VERSIONS_PER_FILE)
            )
            for old in surplus:
                versions.delete_one({'_id': old['_id']})
    except Exception:
        logger.exception('Failed to snapshot workspace file %s', file.get('id'))


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


@router.get('')
def list_workspaces(
    include_archived: bool = Query(default=False),
    student_id: str = Depends(verify_jwt_student),
):
    query = {
        '$or': [
            {'owner_student_id': student_id},
            {'members.student_id': student_id},
        ]
    }
    if not include_archived:
        query['status'] = {'$nin': ['archived', 'closed']}

    try:
        workspaces = []
        for workspace in (
            get_collection('workspaces').find(query).sort('updated_at', -1)
        ):
            response = _workspace_response(workspace)
            member = next(
                (
                    member
                    for member in workspace.get('members', [])
                    if member.get('student_id') == student_id
                ),
                None,
            )
            response['role'] = (
                'leader'
                if workspace.get('owner_student_id') == student_id
                else _normalize_role(member.get('role') if member else None)
            )
            response['member_count'] = len(_workspace_members(workspace))
            workspaces.append(response)
    except Exception as error:
        logger.exception('Failed to list workspaces for student %s', student_id)
        raise HTTPException(status_code=500, detail='Could not load workspaces.') from error

    return {'status': 'success', 'total': len(workspaces), 'workspaces': workspaces}


@router.get('/{workspace_id}')
def get_workspace(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    response = _workspace_response(workspace)
    response['role'] = role
    response['member_count'] = len(_workspace_members(workspace))
    return {'status': 'success', 'workspace': response}


@router.post('')
def create_workspace(
    request: WorkspaceCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail='Workspace name cannot be blank.')

    now = _now()
    workspace = {
        'workspace_id': uuid.uuid4().hex,
        'name': name,
        'description': (request.description or '').strip(),
        'visibility': request.visibility,
        'status': 'active',
        'owner_student_id': student_id,
        'peer_pool_id': request.peer_pool_id,
        'project_id': request.project_id,
        'member_count': 1,
        'created_at': now,
        'updated_at': now,
        'members': [{'student_id': student_id, 'role': 'leader', 'joined_at': now}],
    }

    try:
        get_collection('workspaces').insert_one(workspace)
    except Exception as error:
        logger.exception('Failed to create workspace for student %s', student_id)
        raise HTTPException(status_code=500, detail='Could not create workspace.') from error

    response = _workspace_response(workspace)
    response['role'] = 'leader'
    return {'status': 'success', 'workspace': response}


@router.patch('/{workspace_id}')
async def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    data = request.model_dump(exclude_unset=True)
    updates = {
        key: value.strip() if key in {'name', 'description'} else value
        for key, value in data.items()
        if value is not None
    }
    if 'name' in updates and not updates['name']:
        raise HTTPException(status_code=422, detail='Workspace name cannot be blank.')
    if not updates:
        raise HTTPException(status_code=422, detail='No valid updates provided.')
    updates['updated_at'] = _now()
    try:
        result = get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id},
            {'$set': updates},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail='Workspace not found.')
        if updates.get('status') in {'archived', 'closed'}:
            get_collection('join_keys').update_many(
                {'workspace_id': workspace_id, 'revoked': False},
                {'$set': {'revoked': True}},
            )
            from app.api.workspace_ws import manager

            await manager.disconnect_workspace(workspace_id)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to update workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not update workspace.') from error
    return {'status': 'success'}


@router.delete('/{workspace_id}')
async def archive_workspace(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can archive the workspace.')
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id},
            {'$set': {'status': 'archived', 'updated_at': _now()}},
        )
        get_collection('join_keys').update_many(
            {'workspace_id': workspace_id, 'revoked': False},
            {'$set': {'revoked': True}},
        )
        from app.api.workspace_ws import manager

        await manager.disconnect_workspace(workspace_id)
    except Exception as error:
        logger.exception('Failed to archive workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not archive workspace.') from error
    _record_workspace_activity(workspace_id, student_id, 'archived_workspace')
    return {'status': 'success', 'message': 'Workspace archived.'}


@router.post('/{workspace_id}/unarchive')
async def unarchive_workspace(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can unarchive the workspace.')
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id},
            {'$set': {'status': 'active', 'updated_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to unarchive workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not unarchive workspace.') from error
    _record_workspace_activity(workspace_id, student_id, 'unarchived_workspace')
    return {'status': 'success', 'message': 'Workspace restored.'}


@router.delete('/{workspace_id}/purge')
async def purge_workspace(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can delete the workspace.')
    try:
        result = get_collection('workspaces').delete_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id}
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail='Workspace not found.')
        for collection_name in (
            'workspace_invites',
            'join_keys',
            'workspace_notifications',
            'workspace_files',
            'file_versions',
            'workspace_chat',
            'workspace_chat_reads',
            'workspace_comments',
            'workspace_tasks',
            'workspace_sync',
            'workspace_trash',
            'activity_log',
        ):
            get_collection(collection_name).delete_many({'workspace_id': workspace_id})
        from app.api.workspace_ws import manager

        await manager.disconnect_workspace(workspace_id)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to purge workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not delete workspace.') from error
    return {'status': 'success', 'message': 'Workspace deleted permanently.'}


@router.post('/{workspace_id}/leave')
async def leave_workspace(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    workspace, role = _workspace_access(workspace_id, student_id)
    if _is_leader(role):
        raise HTTPException(
            status_code=409,
            detail='Transfer ownership before leaving the workspace.',
        )
    members = [
        member
        for member in _workspace_members(workspace)
        if member.get('student_id') != student_id
    ]
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id},
            {
                '$set': {
                    'members': members,
                    'member_count': len(members),
                    'updated_at': _now(),
                }
            },
        )
    except Exception as error:
        logger.exception('Failed to leave workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not leave workspace.') from error
    from app.api.workspace_ws import manager

    await manager.disconnect_student(workspace_id, student_id)
    _record_workspace_activity(workspace_id, student_id, 'left_workspace')
    return {'status': 'success', 'message': 'You left the workspace.'}


@router.post('/{workspace_id}/transfer-ownership')
async def transfer_workspace_ownership(
    workspace_id: str,
    request: OwnershipTransferRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can transfer ownership.')
    new_owner_id = request.new_owner_student_id.strip()
    if not new_owner_id or new_owner_id == student_id:
        raise HTTPException(status_code=422, detail='Choose another workspace member.')
    members = _workspace_members(workspace)
    new_owner = next(
        (member for member in members if member.get('student_id') == new_owner_id),
        None,
    )
    if not new_owner:
        raise HTTPException(status_code=422, detail='New owner must already be a workspace member.')
    for member in members:
        if member.get('student_id') == student_id:
            member['role'] = 'member'
        if member.get('student_id') == new_owner_id:
            member['role'] = 'leader'
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id},
            {
                '$set': {
                    'owner_student_id': new_owner_id,
                    'members': members,
                    'updated_at': _now(),
                }
            },
        )
    except Exception as error:
        logger.exception('Failed to transfer workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not transfer workspace ownership.') from error
    _notify_student(workspace_id, new_owner_id, 'ownership_transferred')
    _record_workspace_activity(workspace_id, student_id, 'transferred_ownership', new_owner_id)
    from app.api.workspace_ws import manager

    await manager.disconnect_workspace(workspace_id)
    return {'status': 'success', 'owner_student_id': new_owner_id}


# ---------------------------------------------------------------------------
# Members and invitations
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/members')
def list_workspace_members(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, _ = _workspace_access(workspace_id, student_id)
    members = _workspace_members(workspace)
    return {'status': 'success', 'total': len(members), 'members': members}


@router.get('/students/search')
def search_workspace_students(
    q: str = Query(..., min_length=2, max_length=100),
    student_id: str = Depends(verify_jwt_student),
):
    search_term = re.escape(q.strip())
    if len(search_term) < 2:
        raise HTTPException(status_code=422, detail='Search query must contain at least 2 characters.')
    query = {
        '$and': [
            {
                '$or': [
                    {'name': {'$regex': search_term, '$options': 'i'}},
                    {'email': {'$regex': search_term, '$options': 'i'}},
                    {'student_id': {'$regex': search_term, '$options': 'i'}},
                ]
            },
            {'student_id': {'$ne': student_id}},
            {'is_deleted': {'$ne': True}},
            {'is_active': {'$ne': False}},
        ]
    }
    try:
        students = []
        for student in get_collection('students').find(
            query,
            {'_id': 0, 'student_id': 1, 'name': 1, 'email': 1},
        ):
            students.append(
                {
                    'student_id': student.get('student_id'),
                    'name': student.get('name'),
                    'email': student.get('email'),
                }
            )
            if len(students) >= 20:
                break
    except Exception as error:
        logger.exception('Failed to search workspace students')
        raise HTTPException(status_code=500, detail='Could not search students.') from error
    return {'status': 'success', 'students': students}


@router.post('/{workspace_id}/members')
@router.post('/{workspace_id}/invite')
def invite_workspace_member(
    workspace_id: str,
    request: WorkspaceInviteRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can invite members.')
    if workspace.get('status', 'active') != 'active':
        raise HTTPException(status_code=409, detail='Workspace is closed to new members.')
    invited_student_id = request.student_id.strip()
    if not invited_student_id:
        raise HTTPException(status_code=422, detail='Student ID cannot be blank.')
    if invited_student_id == workspace['owner_student_id']:
        raise HTTPException(status_code=409, detail='The workspace owner is already a member.')
    try:
        registered_student = get_collection('students').find_one(
            {
                'student_id': invited_student_id,
                'is_deleted': {'$ne': True},
                'is_active': {'$ne': False},
            }
        )
        existing_invite = get_collection('workspace_invites').find_one(
            {
                'workspace_id': workspace_id,
                'student_id': invited_student_id,
                'status': 'pending',
            }
        )
    except Exception as error:
        logger.exception('Failed to validate workspace invitation')
        raise HTTPException(status_code=500, detail='Could not invite workspace member.') from error
    members = _workspace_members(workspace)
    if any(member.get('student_id') == invited_student_id for member in members):
        raise HTTPException(status_code=409, detail='Student is already a workspace member.')
    if not registered_student:
        raise HTTPException(status_code=404, detail='Registered student not found.')
    if existing_invite:
        raise HTTPException(status_code=409, detail='A pending invitation already exists.')
    invite = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'student_id': invited_student_id,
        'role': _normalize_role(request.role),
        'status': 'pending',
        'invited_by': student_id,
        'workspace_name': workspace.get('name'),
        'created_at': _now(),
    }
    try:
        get_collection('workspace_invites').insert_one(invite)
    except DuplicateKeyError as error:
        raise HTTPException(status_code=409, detail='A pending invitation already exists.') from error
    except Exception as error:
        logger.exception('Failed to create invitation for workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not invite workspace member.') from error
    _notify_student(
        workspace_id,
        invited_student_id,
        'workspace_invitation',
        {'invite_id': invite['id']},
    )
    _record_workspace_activity(workspace_id, student_id, 'invited_member', invited_student_id)
    return {'status': 'success', 'invitation': _workspace_response(invite)}


@router.get('/{workspace_id}/invites')
def list_workspace_invites(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can list invitations.')
    try:
        invites = [
            _workspace_response(document)
            for document in get_collection('workspace_invites')
            .find({'workspace_id': workspace_id})
            .sort('created_at', -1)
        ]
    except Exception as error:
        logger.exception('Failed to list workspace invitations')
        raise HTTPException(status_code=500, detail='Could not load invitations.') from error
    return {'status': 'success', 'invites': invites}


@router.delete('/{workspace_id}/invites/{invite_id}')
def revoke_workspace_invite(
    workspace_id: str,
    invite_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can revoke invitations.')
    try:
        result = get_collection('workspace_invites').update_one(
            {'workspace_id': workspace_id, 'id': invite_id, 'status': 'pending'},
            {'$set': {'status': 'revoked', 'revoked_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to revoke workspace invitation')
        raise HTTPException(status_code=500, detail='Could not revoke invitation.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Invitation not found.')
    return {'status': 'success'}


@router.patch('/{workspace_id}/members/{target_student_id}')
async def update_workspace_member(
    workspace_id: str,
    target_student_id: str,
    request: WorkspaceMemberUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can update members.')
    if target_student_id == workspace['owner_student_id']:
        raise HTTPException(status_code=422, detail='Transfer ownership to change the owner role.')
    members = _workspace_members(workspace)
    member = next(
        (item for item in members if item.get('student_id') == target_student_id),
        None,
    )
    if not member:
        raise HTTPException(status_code=404, detail='Workspace member not found.')
    member['role'] = _normalize_role(request.role)
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id},
            {'$set': {'members': members, 'updated_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to update member in workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not update workspace member.') from error
    _notify_student(workspace_id, target_student_id, 'role_changed', {'role': member['role']})
    _record_workspace_activity(
        workspace_id, student_id, 'changed_role', f'{target_student_id}:{member["role"]}'
    )
    from app.api.workspace_ws import manager

    await manager.disconnect_student(workspace_id, target_student_id)
    return {'status': 'success', 'member': member}


@router.delete('/{workspace_id}/members/{target_student_id}')
async def remove_workspace_member(
    workspace_id: str,
    target_student_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role) and target_student_id != student_id:
        raise HTTPException(status_code=403, detail='Only the owner can remove another member.')
    if target_student_id == workspace['owner_student_id']:
        raise HTTPException(status_code=422, detail='The workspace owner cannot be removed.')
    current_members = _workspace_members(workspace)
    members = [
        member
        for member in current_members
        if member.get('student_id') != target_student_id
    ]
    if len(members) == len(current_members):
        raise HTTPException(status_code=404, detail='Workspace member not found.')
    try:
        get_collection('workspaces').update_one(
            {'workspace_id': workspace_id, 'owner_student_id': workspace['owner_student_id']},
            {'$set': {'members': members, 'member_count': len(members), 'updated_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to remove member from workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not remove workspace member.') from error
    _record_workspace_activity(workspace_id, student_id, 'removed_member', target_student_id)
    from app.api.workspace_ws import manager

    await manager.disconnect_student(workspace_id, target_student_id)
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Join keys
# ---------------------------------------------------------------------------


def _create_join_key(
    workspace_id: str,
    student_id: str,
    request: JoinKeyCreateRequest,
) -> Dict[str, Any]:
    key = _generate_join_key()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=request.expires_in_hours or 24)
    document = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'key_hash': _hash_key(key),
        'role': _normalize_role(request.role),
        'max_uses': request.max_uses or 1,
        'uses': 0,
        'expires_at': expires_at,
        'revoked': False,
        'created_by': student_id,
        'created_at': now.isoformat(),
    }
    try:
        get_collection('join_keys').insert_one(document)
    except Exception as error:
        logger.exception('Failed to create join key for workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not create join key.') from error
    _record_workspace_activity(workspace_id, student_id, 'created_join_key')
    return {
        'status': 'success',
        'join_key': key,
        'expires_at': expires_at.isoformat(),
        'max_uses': document['max_uses'],
        'key_id': document['id'],
    }


@router.post('/{workspace_id}/join-keys')
def create_workspace_join_key(
    workspace_id: str,
    request: JoinKeyCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can create join keys.')
    return _create_join_key(workspace_id, student_id, request)


@router.get('/{workspace_id}/join-keys')
def list_workspace_join_keys(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can list join keys.')
    try:
        keys = []
        now = datetime.now(timezone.utc)
        for doc in (
            get_collection('join_keys').find({'workspace_id': workspace_id}).sort('created_at', -1)
        ):
            expires_at = _parse_expiry(doc.get('expires_at'))
            is_active = (
                not doc.get('revoked', False)
                and int(doc.get('uses', 0)) < int(doc.get('max_uses', 1))
                and (expires_at is None or expires_at > now)
            )
            keys.append({
                'id': doc.get('id'),
                'role': doc.get('role'),
                'max_uses': doc.get('max_uses'),
                'uses': doc.get('uses', 0),
                'revoked': doc.get('revoked', False),
                'is_active': is_active,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'created_at': doc.get('created_at'),
            })
    except Exception as error:
        logger.exception('Failed to list join keys for workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not list join keys.') from error
    return {'status': 'success', 'keys': keys}


@router.delete('/{workspace_id}/join-keys/{key_id}')
def revoke_workspace_join_key(
    workspace_id: str,
    key_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace owner can revoke join keys.')
    try:
        result = get_collection('join_keys').update_one(
            {'workspace_id': workspace_id, 'id': key_id},
            {'$set': {'revoked': True}},
        )
    except Exception as error:
        logger.exception('Failed to revoke join key %s', key_id)
        raise HTTPException(status_code=500, detail='Could not revoke join key.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Join key not found.')
    _record_workspace_activity(workspace_id, student_id, 'revoked_join_key')
    return {'status': 'success'}


@router.post('/{workspace_id}/join-keys/{key_id}/regenerate')
def regenerate_workspace_join_key(
    workspace_id: str,
    key_id: str,
    request: JoinKeyCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    _, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace leader can regenerate join keys.')
    try:
        result = get_collection('join_keys').update_one(
            {'workspace_id': workspace_id, 'id': key_id, 'revoked': False},
            {'$set': {'revoked': True}},
        )
    except Exception as error:
        logger.exception('Failed to revoke join key %s during regeneration', key_id)
        raise HTTPException(status_code=500, detail='Could not regenerate join key.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Active join key not found.')
    return _create_join_key(workspace_id, student_id, request)


@router.post('/join')
def join_workspace_by_key(
    request: JoinByKeyRequest,
    request_obj: Request,
    student_id: str = Depends(verify_jwt_student),
):
    key = request.join_key.strip().upper()
    client_ip = request_obj.client.host if request_obj.client else 'unknown'
    try:
        _check_rate_limit('ip', client_ip)
        _check_rate_limit('student', student_id)
    except HTTPException:
        _log_join_failure(student_id, client_ip, 'rate_limited')
        raise
    key_hash = _hash_key(key)
    try:
        key_collection = get_collection('join_keys')
        join_key = key_collection.find_one({'key_hash': key_hash})
    except Exception as error:
        logger.exception('Failed to lookup join key')
        raise HTTPException(status_code=500, detail='Could not process join request.') from error
    if not join_key:
        _log_join_failure(student_id, client_ip, 'invalid_key')
        raise HTTPException(status_code=404, detail='Invalid join key.')
    if join_key.get('revoked'):
        _log_join_failure(student_id, client_ip, 'revoked_key')
        raise HTTPException(status_code=403, detail='Join key has been revoked.')
    now = datetime.now(timezone.utc)
    try:
        expires_at = _parse_expiry(join_key.get('expires_at'))
    except (ValueError, TypeError):
        _log_join_failure(student_id, client_ip, 'invalid_expiry')
        raise HTTPException(status_code=403, detail='Join key is invalid or expired.')
    if expires_at and expires_at <= now:
        _log_join_failure(student_id, client_ip, 'expired_key')
        raise HTTPException(status_code=403, detail='Join key has expired.')
    max_uses = int(join_key.get('max_uses', 1))
    if int(join_key.get('uses', 0)) >= max_uses:
        _log_join_failure(student_id, client_ip, 'exhausted_key')
        raise HTTPException(status_code=403, detail='Join key has reached maximum uses.')
    workspace_id = join_key['workspace_id']
    try:
        workspace = get_collection('workspaces').find_one({'workspace_id': workspace_id})
    except Exception as error:
        logger.exception('Failed to load workspace for join')
        raise HTTPException(status_code=500, detail='Could not process join request.') from error
    if not workspace:
        _log_join_failure(student_id, client_ip, 'missing_workspace')
        raise HTTPException(status_code=404, detail='Workspace not found.')
    if workspace.get('owner_student_id') == student_id:
        _log_join_failure(student_id, client_ip, 'already_member')
        raise HTTPException(status_code=409, detail='You are already the workspace owner.')
    if any(m.get('student_id') == student_id for m in workspace.get('members', [])):
        _log_join_failure(student_id, client_ip, 'already_member')
        raise HTTPException(status_code=409, detail='You are already a workspace member.')
    role = _normalize_role(join_key.get('role', 'member'))
    if role == 'leader':
        role = 'member'
    now_iso = now.isoformat()
    expiry_condition = (
        {'$gt': now}
        if isinstance(join_key.get('expires_at'), datetime)
        else {'$gt': now_iso}
    )
    key_query = {
        'id': join_key['id'],
        'revoked': False,
        'uses': {'$lt': max_uses},
    }
    if join_key.get('expires_at') is not None:
        key_query['expires_at'] = expiry_condition
    key_claimed = False
    try:
        claimed_key = key_collection.update_one(key_query, {'$inc': {'uses': 1}})
        if not claimed_key.matched_count:
            _log_join_failure(student_id, client_ip, 'key_unavailable')
            raise HTTPException(status_code=403, detail='Join key is no longer available.')
        key_claimed = True
        membership_result = get_collection('workspaces').update_one(
            {
                'workspace_id': workspace_id,
                'status': {'$nin': ['archived', 'closed']},
                'owner_student_id': {'$ne': student_id},
                'members.student_id': {'$ne': student_id},
            },
            {
                '$push': {
                    'members': {'student_id': student_id, 'role': role, 'joined_at': now_iso}
                },
                '$inc': {'member_count': 1},
                '$set': {'updated_at': now_iso},
            },
        )
        if not membership_result.matched_count:
            key_claimed = False
            key_collection.update_one({'id': join_key['id']}, {'$inc': {'uses': -1}})
            _log_join_failure(student_id, client_ip, 'membership_not_added')
            raise HTTPException(status_code=409, detail='Workspace is closed or you are already a member.')
    except Exception as error:
        if key_claimed:
            try:
                key_collection.update_one(
                    {'id': join_key['id'], 'uses': {'$gt': 0}},
                    {'$inc': {'uses': -1}},
                )
            except Exception:
                logger.exception('Failed to release workspace join-key use after join failure')
        if isinstance(error, HTTPException):
            raise
        logger.exception('Failed to join workspace with key')
        raise HTTPException(status_code=500, detail='Could not join workspace.') from error
    if workspace.get('owner_student_id'):
        _notify_student(workspace_id, workspace['owner_student_id'], 'member_joined', {'member_student_id': student_id})
    _record_workspace_activity(workspace_id, student_id, 'joined_with_key')
    return {'status': 'success', 'workspace_id': workspace_id, 'role': role}


# ---------------------------------------------------------------------------
# Invitations (pending)
# ---------------------------------------------------------------------------


@router.get('/invitations/pending')
def list_pending_invitations(student_id: str = Depends(verify_jwt_student)):
    try:
        invites = []
        for invite in (
            get_collection('workspace_invites')
            .find({'student_id': student_id, 'status': 'pending'})
            .sort('created_at', -1)
        ):
            result = _workspace_response(invite)
            workspace = get_collection('workspaces').find_one(
                {'workspace_id': invite['workspace_id']}
            )
            if workspace:
                result['workspace'] = {
                    'workspace_id': workspace.get('workspace_id'),
                    'name': workspace.get('name'),
                    'description': workspace.get('description', ''),
                    'owner_student_id': workspace.get('owner_student_id'),
                }
            invites.append(result)
    except Exception as error:
        logger.exception('Failed to list pending invitations')
        raise HTTPException(status_code=500, detail='Could not load invitations.') from error
    return {'status': 'success', 'invitations': invites}


@router.post('/invitations/{invite_id}/accept')
def accept_invitation(invite_id: str, student_id: str = Depends(verify_jwt_student)):
    try:
        invite_collection = get_collection('workspace_invites')
        invite = invite_collection.find_one(
            {'id': invite_id, 'student_id': student_id, 'status': 'pending'}
        )
    except Exception as error:
        logger.exception('Failed to load invitation')
        raise HTTPException(status_code=500, detail='Could not accept invitation.') from error
    if not invite:
        raise HTTPException(status_code=404, detail='Invitation not found.')
    try:
        claim = invite_collection.update_one(
            {'id': invite_id, 'student_id': student_id, 'status': 'pending'},
            {'$set': {'status': 'accepting'}},
        )
    except Exception as error:
        logger.exception('Failed to claim invitation %s', invite_id)
        raise HTTPException(status_code=500, detail='Could not accept invitation.') from error
    if not claim.matched_count:
        raise HTTPException(status_code=409, detail='Invitation is no longer pending.')
    workspace_id = invite['workspace_id']
    role = _normalize_role(invite.get('role', 'member'))
    if role == 'leader':
        role = 'member'
    now = _now()
    try:
        workspace = get_collection('workspaces').find_one({'workspace_id': workspace_id})
        if not workspace or workspace.get('status', 'active') != 'active':
            raise HTTPException(status_code=404, detail='Workspace is no longer available.')
        if workspace.get('owner_student_id') != student_id and not any(
            m.get('student_id') == student_id for m in workspace.get('members', [])
        ):
            member_result = get_collection('workspaces').update_one(
                {
                    'workspace_id': workspace_id,
                    'status': {'$nin': ['archived', 'closed']},
                    'owner_student_id': {'$ne': student_id},
                    'members.student_id': {'$ne': student_id},
                },
                {
                    '$push': {
                        'members': {'student_id': student_id, 'role': role, 'joined_at': now}
                    },
                    '$inc': {'member_count': 1},
                    '$set': {'updated_at': now},
                },
            )
            if not member_result.matched_count:
                workspace = get_collection('workspaces').find_one({'workspace_id': workspace_id})
                if not workspace or not any(
                    member.get('student_id') == student_id
                    for member in workspace.get('members', [])
                ):
                    raise HTTPException(status_code=409, detail='Could not add workspace member.')
        invite_result = invite_collection.update_one(
            {'id': invite_id, 'student_id': student_id, 'status': 'accepting'},
            {'$set': {'status': 'accepted', 'accepted_at': now}},
        )
        if not invite_result.matched_count:
            raise HTTPException(status_code=409, detail='Invitation is no longer pending.')
    except Exception as error:
        try:
            invite_collection.update_one(
                {'id': invite_id, 'student_id': student_id, 'status': 'accepting'},
                {'$set': {'status': 'pending'}},
            )
        except Exception:
            logger.exception('Failed to restore invitation %s after accept failure', invite_id)
        if isinstance(error, HTTPException):
            raise
        logger.exception('Failed to accept invitation')
        raise HTTPException(status_code=500, detail='Could not accept invitation.') from error
    try:
        get_collection('workspace_notifications').update_one(
            {'invite_id': invite_id, 'student_id': student_id},
            {'$set': {'status': 'read', 'read_at': now}},
        )
    except Exception:
        logger.exception('Failed to mark invitation notification as read')
    if workspace.get('owner_student_id'):
        _notify_student(workspace_id, workspace['owner_student_id'], 'member_joined', {'member_student_id': student_id})
    _record_workspace_activity(workspace_id, student_id, 'accepted_invitation')
    return {'status': 'success', 'workspace_id': workspace_id}


@router.post('/invitations/{invite_id}/decline')
def decline_invitation(invite_id: str, student_id: str = Depends(verify_jwt_student)):
    try:
        result = get_collection('workspace_invites').update_one(
            {'id': invite_id, 'student_id': student_id, 'status': 'pending'},
            {'$set': {'status': 'declined', 'declined_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to decline invitation')
        raise HTTPException(status_code=500, detail='Could not decline invitation.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Invitation not found.')
    try:
        get_collection('workspace_notifications').update_one(
            {'invite_id': invite_id, 'student_id': student_id},
            {'$set': {'status': 'read', 'read_at': _now()}},
        )
    except Exception:
        logger.exception('Failed to mark declined invitation notification as read')
    invite = get_collection('workspace_invites').find_one({'id': invite_id})
    if invite:
        _record_workspace_activity(invite['workspace_id'], student_id, 'declined_invitation')
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/files')
def list_workspace_files(
    workspace_id: str,
    include_content: bool = Query(default=True),
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    files = sorted(
        (_workspace_response(file) for file in _active_workspace_files(workspace_id)),
        key=lambda file: _file_path(file).casefold(),
    )
    if not include_content:
        for file in files:
            file.pop('content', None)
    return {'status': 'success', 'total': len(files), 'files': files}


@router.get('/{workspace_id}/files/{file_id}')
def get_workspace_file(
    workspace_id: str,
    file_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    file = _workspace_file_by_id(workspace_id, file_id)
    return {'status': 'success', 'file': _workspace_response(file)}


def _create_workspace_entry(
    workspace_id: str,
    request: FileCreateRequest,
    student_id: str,
    force_folder: bool = False,
):
    _require_editor(workspace_id, student_id)
    is_folder = force_folder or request.type == 'folder'
    if request.path:
        if request.parent_path:
            raise HTTPException(status_code=422, detail='Use either path or parent_path, not both.')
        path = _validate_path(request.path)
        name = posixpath.basename(path)
        if request.name and request.name.strip() != name:
            raise HTTPException(status_code=422, detail='File name must match the path basename.')
    else:
        if not request.name:
            raise HTTPException(status_code=422, detail='File or folder name is required.')
        name = request.name.strip()
        path = _resolve_file_path(name, request.parent_path)
    if is_folder and request.content:
        raise HTTPException(status_code=422, detail='Folders cannot contain file content.')
    _check_parent_folder(workspace_id, path)
    _check_path_available(workspace_id, path)
    now = _now()
    document = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'name': name,
        'path': path,
        'type': 'folder' if is_folder else 'file',
        'content': '' if is_folder else request.content,
        'language': None if is_folder else (request.language or 'java').strip().lower(),
        'created_by': student_id,
        'created_at': now,
        'updated_at': now,
    }
    _check_workspace_quota(workspace_id, [document])
    file = _insert_workspace_record('workspace_files', document)
    _record_workspace_activity(
        workspace_id,
        student_id,
        'created_folder' if is_folder else 'created_file',
        path,
    )
    _publish_file_tree_event(workspace_id, 'created', [file], student_id)
    return {'status': 'success', 'file': file}


@router.post('/{workspace_id}/files')
def create_workspace_file(
    workspace_id: str,
    request: FileCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    return _create_workspace_entry(workspace_id, request, student_id)


@router.post('/{workspace_id}/folders')
def create_workspace_folder(
    workspace_id: str,
    request: FileCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    return _create_workspace_entry(workspace_id, request, student_id, force_folder=True)


@router.put('/{workspace_id}/files/{file_id}')
def update_workspace_file(
    workspace_id: str,
    file_id: str,
    request: FileUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    file = _workspace_file_by_id(workspace_id, file_id)
    updates = request.model_dump(exclude_unset=True)
    if 'name' in updates and updates['name'] is not None:
        updates['name'] = updates['name'].strip()
        if not updates['name']:
            raise HTTPException(status_code=422, detail='File name cannot be blank.')
        if '/' in updates['name'] or '\\' in updates['name']:
            raise HTTPException(status_code=422, detail='Renamed entry must be a single path segment.')
        new_path = _resolve_file_path(updates['name'], posixpath.dirname(_file_path(file)) or None)
        _check_path_available(workspace_id, new_path, {file_id})
        _check_parent_folder(workspace_id, new_path)
        updates['path'] = new_path
    if 'language' in updates and updates['language'] is not None:
        updates['language'] = updates['language'].strip().lower()
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        raise HTTPException(status_code=422, detail='No file updates provided.')
    if file.get('type') == 'folder' and ('content' in updates or 'language' in updates):
        raise HTTPException(status_code=422, detail='Folder content and language cannot be updated.')
    if 'content' in updates:
        _check_workspace_quota(
            workspace_id,
            [{'id': file_id, 'type': 'file', 'content': updates['content']}],
            {file_id},
        )
    updates['updated_at'] = _now()
    old_path = _file_path(file)
    new_path = updates.get('path')
    descendants = []
    descendant_updates = []
    if file.get('type') == 'folder' and new_path and new_path != old_path:
        descendants = [
            item
            for item in _active_workspace_files(workspace_id)
            if item.get('id') != file_id and _file_path(item).startswith(old_path + '/')
        ]
        replacements = {
            item['id']: new_path + _file_path(item)[len(old_path):]
            for item in descendants
        }
        for destination in replacements.values():
            _check_path_available(workspace_id, destination, {file_id, *replacements})
        for item in descendants:
            descendant_updates.append(
                (
                    item,
                    {
                        'path': replacements[item['id']],
                        'name': posixpath.basename(replacements[item['id']]),
                        'updated_at': updates['updated_at'],
                    },
                )
            )
    changed_descendants = []
    root_updated = False

    def _rollback_folder_rename() -> None:
        for descendant in changed_descendants:
            try:
                get_collection('workspace_files').update_one(
                    {'workspace_id': workspace_id, 'id': descendant['id']},
                    {
                        '$set': {
                            'path': _file_path(descendant),
                            'name': descendant.get('name'),
                            'updated_at': descendant.get('updated_at'),
                        }
                    },
                )
            except Exception:
                logger.exception('Failed to roll back workspace folder rename')
        if root_updated:
            try:
                get_collection('workspace_files').update_one(
                    {'workspace_id': workspace_id, 'id': file_id},
                    {
                        '$set': {
                            'path': old_path,
                            'name': file.get('name'),
                            'updated_at': file.get('updated_at'),
                        }
                    },
                )
            except Exception:
                logger.exception('Failed to roll back workspace folder root rename')

    try:
        result = get_collection('workspace_files').update_one(
            {'workspace_id': workspace_id, 'id': file_id},
            {'$set': updates},
        )
        if not result.matched_count:
            raise HTTPException(status_code=404, detail='Workspace file not found.')
        root_updated = True
        for descendant, descendant_values in descendant_updates:
            result = get_collection('workspace_files').update_one(
                {'workspace_id': workspace_id, 'id': descendant['id']},
                {'$set': descendant_values},
            )
            if not result.matched_count:
                raise RuntimeError('Workspace folder descendant was not found.')
            changed_descendants.append(descendant)
    except HTTPException:
        _rollback_folder_rename()
        raise
    except Exception as error:
        _rollback_folder_rename()
        logger.exception('Failed to update workspace file %s', file_id)
        raise HTTPException(status_code=500, detail='Could not update file.') from error

    file = _find_workspace_record('workspace_files', workspace_id, file_id)
    if 'content' in updates:
        _snapshot_file_version(workspace_id, file, student_id)
        action = 'edited_file'
    elif 'name' in updates:
        action = 'renamed_file'
    else:
        action = 'updated_file'
    _record_workspace_activity(workspace_id, student_id, action, file.get('path'))
    changed_tree = [file]
    if file.get('type') == 'folder' and new_path and new_path != old_path:
        changed_tree.extend(
            _find_workspace_record('workspace_files', workspace_id, item['id'])
            for item in descendants
        )
    _publish_file_tree_event(workspace_id, 'updated', changed_tree, student_id)
    return {'status': 'success', 'file': _workspace_response(file)}


@router.post('/{workspace_id}/files/{file_id}/move')
def move_workspace_file(
    workspace_id: str,
    file_id: str,
    request: FileMoveRequest,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    file = _workspace_file_by_id(workspace_id, file_id)
    old_path = _file_path(file)
    new_path = _validate_path(request.new_path)
    if file.get('type') == 'folder' and (
        new_path == old_path or new_path.startswith(old_path + '/')
    ):
        raise HTTPException(status_code=422, detail='A folder cannot be moved inside itself.')
    _check_parent_folder(workspace_id, new_path)
    moving = [
        item
        for item in _active_workspace_files(workspace_id)
        if item.get('id') == file_id
        or (file.get('type') == 'folder' and _file_path(item).startswith(old_path + '/'))
    ]
    destinations = {
        item['id']: new_path + _file_path(item)[len(old_path):] for item in moving
    }
    moving_ids = set(destinations)
    if len(set(destinations.values())) != len(destinations):
        raise HTTPException(status_code=409, detail='Move would create duplicate paths.')
    for destination in destinations.values():
        _check_path_available(workspace_id, destination, moving_ids)
    changed = []
    try:
        for item in moving:
            destination = destinations[item['id']]
            get_collection('workspace_files').update_one(
                {'workspace_id': workspace_id, 'id': item['id']},
                {
                    '$set': {
                        'path': destination,
                        'name': posixpath.basename(destination),
                        'updated_at': _now(),
                    }
                },
            )
            changed.append(item)
    except Exception as error:
        for item in changed:
            try:
                get_collection('workspace_files').update_one(
                    {'workspace_id': workspace_id, 'id': item['id']},
                    {'$set': {'path': _file_path(item), 'name': item['name']}},
                )
            except Exception:
                logger.exception('Failed to roll back workspace file move')
        logger.exception('Failed to move workspace file %s', file_id)
        raise HTTPException(status_code=500, detail='Could not move workspace file.') from error
    _record_workspace_activity(workspace_id, student_id, 'moved_file', new_path)
    moved_files = [
        {
            **item,
            'path': destinations[item['id']],
            'name': posixpath.basename(destinations[item['id']]),
        }
        for item in moving
    ]
    _publish_file_tree_event(workspace_id, 'moved', moved_files, student_id)
    return {'status': 'success', 'path': new_path}


@router.post('/{workspace_id}/files/{file_id}/duplicate')
def duplicate_workspace_file(
    workspace_id: str,
    file_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    source = _workspace_file_by_id(workspace_id, file_id)
    old_path = _file_path(source)
    extension = posixpath.splitext(source['name'])[1] if source.get('type') != 'folder' else ''
    stem = source['name'][:-len(extension)] if extension else source['name']
    parent = posixpath.dirname(old_path)
    existing_paths = {_file_path(item) for item in _active_workspace_files(workspace_id)}
    suffix = 1
    while True:
        copy_name = f'{stem}-copy{"" if suffix == 1 else f"-{suffix}"}{extension}'
        new_root = _resolve_file_path(copy_name, parent or None)
        if new_root not in existing_paths:
            break
        suffix += 1
    _check_parent_folder(workspace_id, new_root)
    sources = [
        item
        for item in _active_workspace_files(workspace_id)
        if item.get('id') == file_id
        or (source.get('type') == 'folder' and _file_path(item).startswith(old_path + '/'))
    ]
    new_documents = []
    now = _now()
    for item in sources:
        old_item_path = _file_path(item)
        new_item_path = new_root + old_item_path[len(old_path):]
        new_document = {
            key: value
            for key, value in item.items()
            if key not in {'_id', 'id', 'created_at', 'updated_at'}
        }
        new_document.update(
            {
                'id': uuid.uuid4().hex,
                'path': new_item_path,
                'name': posixpath.basename(new_item_path),
                'created_by': student_id,
                'created_at': now,
                'updated_at': now,
            }
        )
        new_documents.append(new_document)
    if any(document['path'] in existing_paths for document in new_documents):
        raise HTTPException(status_code=409, detail='A file or folder already exists at a duplicate path.')
    _check_workspace_quota(workspace_id, new_documents)
    _insert_workspace_files(new_documents, workspace_id)
    _record_workspace_activity(workspace_id, student_id, 'duplicated_file', new_root)
    _publish_file_tree_event(workspace_id, 'duplicated', new_documents, student_id)
    return {
        'status': 'success',
        'files': [_workspace_response(item) for item in new_documents],
    }


@router.delete('/{workspace_id}/files/{file_id}')
def delete_workspace_file(
    workspace_id: str,
    file_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    file = _workspace_file_by_id(workspace_id, file_id)
    path = _file_path(file)
    files = [
        item
        for item in _active_workspace_files(workspace_id)
        if item.get('id') == file_id
        or (file.get('type') == 'folder' and _file_path(item).startswith(path + '/'))
    ]
    file_ids = {item['id'] for item in files}
    try:
        trash = _trash_workspace_files(workspace_id, files, student_id)
        get_collection('file_versions').delete_many(
            {'workspace_id': workspace_id, 'file_id': {'$in': list(file_ids)}}
        )
    except Exception as error:
        if isinstance(error, HTTPException):
            raise
        logger.exception('Failed to delete workspace file %s', file_id)
        raise HTTPException(status_code=500, detail='Could not delete file.') from error
    _record_workspace_activity(workspace_id, student_id, 'deleted_file', path)
    _publish_file_tree_event(
        workspace_id, 'deleted', files, student_id, trash_id=trash['trash_id']
    )
    return {'status': 'success', 'trash_id': trash['trash_id']}


# ---------------------------------------------------------------------------
# File versions
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/files/{file_id}/versions')
def list_file_versions(
    workspace_id: str,
    file_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    _workspace_file_by_id(workspace_id, file_id)
    try:
        versions = [
            _workspace_response(document)
            for document in get_collection('file_versions')
            .find({'workspace_id': workspace_id, 'file_id': file_id})
            .sort('created_at', -1)
        ]
    except Exception as error:
        logger.exception('Failed to list file versions')
        raise HTTPException(status_code=500, detail='Could not load file versions.') from error
    profiles = _student_profiles([version.get('student_id') for version in versions])
    for version in versions:
        profile = profiles.get(version.get('student_id')) or {}
        version['name'] = profile.get('name')
        version.pop('content', None)
    return {'status': 'success', 'total': len(versions), 'versions': versions}


@router.get('/{workspace_id}/files/{file_id}/versions/{version_id}')
def get_file_version(
    workspace_id: str,
    file_id: str,
    version_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    version = _find_workspace_record('file_versions', workspace_id, version_id)
    if not version or version.get('file_id') != file_id:
        raise HTTPException(status_code=404, detail='File version not found.')
    return {'status': 'success', 'version': _workspace_response(version)}


@router.post('/{workspace_id}/files/{file_id}/versions/{version_id}/restore')
def restore_file_version(
    workspace_id: str,
    file_id: str,
    version_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    file = _workspace_file_by_id(workspace_id, file_id)
    version = _find_workspace_record('file_versions', workspace_id, version_id)
    if not version or version.get('file_id') != file_id:
        raise HTTPException(status_code=404, detail='File version not found.')
    _snapshot_file_version(workspace_id, file, student_id)
    now = _now()
    try:
        result = get_collection('workspace_files').update_one(
            {'workspace_id': workspace_id, 'id': file_id},
            {'$set': {'content': version.get('content') or '', 'updated_at': now}},
        )
        if not result.matched_count:
            raise HTTPException(status_code=404, detail='Workspace file not found.')
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to restore file version %s', version_id)
        raise HTTPException(status_code=500, detail='Could not restore file version.') from error
    file = _find_workspace_record('workspace_files', workspace_id, file_id)
    _record_workspace_activity(workspace_id, student_id, 'restored_version', _file_path(file))
    _publish_file_tree_event(workspace_id, 'updated', [file], student_id)
    return {
        'status': 'success',
        'file': _workspace_response(file),
        'content': version.get('content') or '',
    }


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/trash')
def list_trash(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    _workspace_access(workspace_id, student_id)
    try:
        items = []
        now = datetime.now(timezone.utc)
        for doc in (
            get_collection('workspace_trash').find({'workspace_id': workspace_id}).sort('deleted_at', -1)
        ):
            expires_at = _parse_expiry(doc.get('expires_at'))
            if expires_at and expires_at <= now:
                continue
            items.append({k: v for k, v in doc.items() if k != '_id'})
    except Exception as error:
        logger.exception('Failed to load trash')
        raise HTTPException(status_code=500, detail='Could not load trash.') from error
    return {'status': 'success', 'items': items}


@router.post('/{workspace_id}/trash/{trash_id}/restore')
def restore_workspace_trash(
    workspace_id: str,
    trash_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    try:
        trash = get_collection('workspace_trash').find_one(
            {'workspace_id': workspace_id, 'trash_id': trash_id}
        )
    except Exception as error:
        logger.exception('Failed to load workspace trash item %s', trash_id)
        raise HTTPException(status_code=500, detail='Could not restore workspace files.') from error
    if not trash:
        raise HTTPException(status_code=404, detail='Trash item not found.')
    expires_at = _parse_expiry(trash.get('expires_at'))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail='Trash item has expired.')
    items = trash.get('items', [])
    if not items:
        raise HTTPException(status_code=409, detail='Trash item contains no files.')
    existing_paths = {_file_path(item) for item in _active_workspace_files(workspace_id)}
    restored = []
    for item in items:
        path = _validate_path(_file_path(item))
        if path in existing_paths:
            raise HTTPException(status_code=409, detail=f'An entry already exists at {path}.')
        restored_item = {key: value for key, value in item.items() if key != '_id'}
        restored_item.update(
            {
                'workspace_id': workspace_id,
                'path': path,
                'name': posixpath.basename(path),
                'type': item.get('type', 'file'),
                'updated_at': _now(),
            }
        )
        restored.append(restored_item)
        existing_paths.add(path)
    allowed_folders = {
        _file_path(item) for item in restored if item.get('type') == 'folder'
    }
    for item in restored:
        _check_parent_folder(workspace_id, _file_path(item), allowed_folders)
    _check_workspace_quota(workspace_id, restored)
    _insert_workspace_files(restored, workspace_id)
    try:
        result = get_collection('workspace_trash').delete_one(
            {'workspace_id': workspace_id, 'trash_id': trash_id}
        )
        if not result.deleted_count:
            raise RuntimeError('Trash item was removed during restore.')
    except Exception as error:
        try:
            get_collection('workspace_files').delete_many(
                {
                    'workspace_id': workspace_id,
                    'id': {'$in': [item['id'] for item in restored]},
                }
            )
        except Exception:
            logger.exception('Failed to roll back restored workspace files')
        logger.exception('Failed to remove restored trash item %s', trash_id)
        raise HTTPException(status_code=500, detail='Could not complete file restore.') from error
    _record_workspace_activity(workspace_id, student_id, 'restored_file', trash_id)
    _publish_file_tree_event(workspace_id, 'restored', restored, student_id)
    return {
        'status': 'success',
        'files': [_workspace_response(item) for item in restored],
    }


@router.delete('/{workspace_id}/trash/{trash_id}')
def permanently_delete_workspace_trash(
    workspace_id: str,
    trash_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    try:
        result = get_collection('workspace_trash').delete_one(
            {'workspace_id': workspace_id, 'trash_id': trash_id}
        )
    except Exception as error:
        logger.exception('Failed to permanently delete workspace trash %s', trash_id)
        raise HTTPException(status_code=500, detail='Could not permanently delete trash item.') from error
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail='Trash item not found.')
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Import / export
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/export')
def export_workspace(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    _workspace_access(workspace_id, student_id)
    try:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
            for item in _active_workspace_files(workspace_id):
                path = _validate_path(_file_path(item))
                if item.get('type') == 'folder':
                    zip_file.writestr(path.rstrip('/') + '/', '')
                else:
                    zip_file.writestr(path, item.get('content') or '')
        archive.seek(0)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to export workspace %s', workspace_id)
        raise HTTPException(status_code=500, detail='Could not export workspace.') from error
    return StreamingResponse(
        archive,
        media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="workspace.zip"'},
    )


@router.post('/{workspace_id}/import')
async def import_workspace_archive(
    workspace_id: str,
    request: Request,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    archive_data = bytearray()
    async for chunk in request.stream():
        archive_data.extend(chunk)
        if len(archive_data) > MAX_WORKSPACE_ARCHIVE_BYTES:
            raise HTTPException(status_code=413, detail='Archive exceeds the 10 MiB limit.')
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as zip_file:
            infos = zip_file.infolist()
            if len(infos) > MAX_WORKSPACE_ENTRIES:
                raise HTTPException(status_code=413, detail='Archive contains too many entries.')
            entries: Dict[str, Dict[str, Any]] = {}
            explicit_paths = set()
            total_size = 0
            for info in infos:
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode):
                    raise HTTPException(status_code=422, detail='Symbolic links are not allowed in workspace archives.')
                is_folder = info.is_dir() or info.filename.endswith('/')
                raw_path = info.filename.rstrip('/') if is_folder else info.filename
                if not raw_path:
                    continue
                path = _validate_path(raw_path)
                if info.file_size > MAX_WORKSPACE_FILE_BYTES:
                    raise HTTPException(status_code=413, detail='An archive file exceeds the 1 MiB limit.')
                if info.file_size > max(info.compress_size, 1) * 1000:
                    raise HTTPException(status_code=413, detail='Archive contains an excessively compressed entry.')
                if not is_folder:
                    total_size += info.file_size
                    if total_size > MAX_WORKSPACE_TOTAL_BYTES:
                        raise HTTPException(status_code=413, detail='Archive content exceeds the 10 MiB limit.')
                    content_bytes = bytearray()
                    with zip_file.open(info) as archive_file:
                        while True:
                            chunk = archive_file.read(
                                min(65_536, MAX_WORKSPACE_FILE_BYTES + 1 - len(content_bytes))
                            )
                            if not chunk:
                                break
                            content_bytes.extend(chunk)
                            if len(content_bytes) > MAX_WORKSPACE_FILE_BYTES:
                                raise HTTPException(
                                    status_code=413,
                                    detail='An archive file exceeds the 1 MiB limit.',
                                )
                    if len(content_bytes) != info.file_size:
                        raise HTTPException(status_code=422, detail='Archive entry size is invalid.')
                    try:
                        content = content_bytes.decode('utf-8')
                    except UnicodeDecodeError as error:
                        raise HTTPException(status_code=415, detail='Only UTF-8 text files can be imported.') from error
                else:
                    content = ''
                for parent in reversed(list(_parent_paths(path))):
                    existing_parent = entries.get(parent)
                    if existing_parent and existing_parent['type'] != 'folder':
                        raise HTTPException(status_code=422, detail='Archive contains conflicting file paths.')
                    entries.setdefault(parent, {'type': 'folder', 'content': ''})
                existing_entry = entries.get(path)
                if path in explicit_paths:
                    raise HTTPException(status_code=422, detail='Archive contains duplicate paths.')
                if existing_entry and (is_folder is False or existing_entry['type'] != 'folder'):
                    raise HTTPException(status_code=422, detail='Archive contains conflicting file paths.')
                if not is_folder and any(key.startswith(path + '/') for key in entries):
                    raise HTTPException(status_code=422, detail='Archive file conflicts with a folder path.')
                entries[path] = {'type': 'folder' if is_folder else 'file', 'content': content}
                explicit_paths.add(path)
            if len(entries) > MAX_WORKSPACE_ENTRIES:
                raise HTTPException(status_code=413, detail='Archive contains too many files and folders.')
    except HTTPException:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail='Invalid or unsupported ZIP archive.') from error

    existing_files = _active_workspace_files(workspace_id)
    existing_paths = {_file_path(item): item for item in existing_files}
    for path, entry in entries.items():
        if path in existing_paths and not (
            entry['type'] == 'folder' and existing_paths[path].get('type') == 'folder'
        ):
            raise HTTPException(status_code=409, detail=f'An entry already exists at {path}.')
        parent = posixpath.dirname(path)
        if parent and parent in existing_paths and existing_paths[parent].get('type') != 'folder':
            raise HTTPException(status_code=409, detail='An existing file conflicts with an imported folder.')
        if entry['type'] == 'file' and any(
            existing_path.startswith(path + '/') for existing_path in existing_paths
        ):
            raise HTTPException(status_code=409, detail='An existing folder conflicts with an imported file.')
    now = _now()
    documents = []
    for path, entry in entries.items():
        if path in existing_paths and entry['type'] == 'folder':
            continue
        name = posixpath.basename(path)
        documents.append(
            {
                'id': uuid.uuid4().hex,
                'workspace_id': workspace_id,
                'name': name,
                'path': path,
                'type': entry['type'],
                'content': entry['content'],
                'language': None if entry['type'] == 'folder' else posixpath.splitext(name)[1].lstrip('.').lower(),
                'created_by': student_id,
                'created_at': now,
                'updated_at': now,
            }
        )
    _check_workspace_quota(workspace_id, documents)
    _insert_workspace_files(documents, workspace_id)
    _record_workspace_activity(workspace_id, student_id, 'imported_archive')
    _publish_file_tree_event(workspace_id, 'imported', documents, student_id)
    return {
        'status': 'success',
        'total': len(documents),
        'files': [_workspace_response(item) for item in documents],
    }


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/chat')
def list_workspace_chat(
    workspace_id: str,
    before: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    query: Dict[str, Any] = {'workspace_id': workspace_id}
    if before:
        try:
            parsed_before = datetime.fromisoformat(before.replace('Z', '+00:00'))
            if parsed_before.tzinfo is None:
                raise ValueError('Pagination cursor must include a timezone.')
            query['created_at'] = {'$lt': parsed_before.isoformat()}
        except ValueError as error:
            raise HTTPException(status_code=422, detail='Invalid chat pagination cursor.') from error
    try:
        cursor = get_collection('workspace_chat').find(query).sort('created_at', -1)
        page = []
        has_more = False
        for document in cursor:
            if len(page) == limit:
                has_more = True
                break
            page.append(document)
    except Exception as error:
        logger.exception('Failed to load workspace chat history')
        raise HTTPException(status_code=500, detail='Could not load chat history.') from error
    messages = [_workspace_response(document) for document in reversed(page)]
    next_before = messages[0].get('created_at') if messages and has_more else None
    return {
        'status': 'success',
        'total': len(messages),
        'messages': messages,
        'has_more': has_more,
        'next_before': next_before,
        'unread_count': _workspace_chat_unread_count(workspace_id, student_id),
    }


@router.post('/{workspace_id}/chat')
def create_workspace_chat_message(
    workspace_id: str,
    request: ChatMessageRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, _ = _workspace_access(workspace_id, student_id)
    if workspace.get('status', 'active') != 'active':
        raise HTTPException(status_code=403, detail='Workspace is read-only.')
    if not request.message.strip():
        raise HTTPException(status_code=422, detail='Chat message cannot be blank.')
    mentions = _validate_chat_message_relations(workspace_id, student_id, request)
    document = _chat_document_from_request(workspace_id, student_id, request, mentions)
    saved = _save_workspace_chat_message(document, mentions)
    return {
        'status': 'success',
        'message': saved,
        'unread_count': _workspace_chat_unread_count(workspace_id, student_id),
    }


@router.get('/{workspace_id}/chat/unread')
def get_workspace_chat_unread_count(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    return {
        'status': 'success',
        'unread_count': _workspace_chat_unread_count(workspace_id, student_id),
    }


@router.post('/{workspace_id}/chat/read')
def mark_workspace_chat_read(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    now = _now()
    try:
        get_collection('workspace_chat_reads').update_one(
            {'workspace_id': workspace_id, 'student_id': student_id},
            {
                '$set': {'last_read_at': now, 'updated_at': now},
                '$setOnInsert': {'id': uuid.uuid4().hex},
            },
            upsert=True,
        )
    except Exception as error:
        logger.exception('Failed to mark workspace chat as read')
        raise HTTPException(status_code=500, detail='Could not mark chat as read.') from error
    return {'status': 'success', 'unread_count': 0}


@router.patch('/{workspace_id}/chat/{message_id}')
def update_workspace_chat_message(
    workspace_id: str,
    message_id: str,
    request: ChatMessageUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, _ = _workspace_access(workspace_id, student_id)
    if workspace.get('status', 'active') != 'active':
        raise HTTPException(status_code=403, detail='Workspace is read-only.')
    message = _find_workspace_record('workspace_chat', workspace_id, message_id)
    if not message:
        raise HTTPException(status_code=404, detail='Chat message not found.')
    if message.get('student_id') != student_id:
        raise HTTPException(status_code=403, detail='You can only edit your own chat messages.')
    updated_message = request.message.strip()
    if not updated_message:
        raise HTTPException(status_code=422, detail='Chat message cannot be blank.')
    updated_at = _now()
    try:
        get_collection('workspace_chat').update_one(
            {'workspace_id': workspace_id, 'id': message_id},
            {'$set': {'message': updated_message, 'updated_at': updated_at}},
        )
    except Exception as error:
        logger.exception('Failed to edit workspace chat message %s', message_id)
        raise HTTPException(status_code=500, detail='Could not edit chat message.') from error
    message['message'] = updated_message
    message['updated_at'] = updated_at
    _publish_workspace_event(
        workspace_id,
        {'type': 'CHAT_MESSAGE_EDITED', 'message': _workspace_response(message)},
    )
    return {'status': 'success', 'message': _workspace_response(message)}


@router.delete('/{workspace_id}/chat/{message_id}')
def delete_workspace_chat_message(
    workspace_id: str,
    message_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    message = _find_workspace_record('workspace_chat', workspace_id, message_id)
    if not message:
        raise HTTPException(status_code=404, detail='Chat message not found.')
    if message.get('student_id') != student_id and not _is_leader(role):
        raise HTTPException(
            status_code=403,
            detail='Only the message author or workspace leader can delete this message.',
        )
    try:
        result = get_collection('workspace_chat').delete_one(
            {'workspace_id': workspace_id, 'id': message_id}
        )
        if not result.deleted_count:
            raise HTTPException(status_code=404, detail='Chat message not found.')
        get_collection('workspace_notifications').delete_many(
            {'workspace_id': workspace_id, 'message_id': message_id}
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to delete workspace chat message %s', message_id)
        raise HTTPException(status_code=500, detail='Could not delete chat message.') from error
    _publish_workspace_event(
        workspace_id,
        {'type': 'CHAT_MESSAGE_DELETED', 'message_id': message_id},
    )
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Inline code comments
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/comments')
def list_workspace_comments(
    workspace_id: str,
    file_id: Optional[str] = None,
    status: Optional[str] = Query(default=None, max_length=20),
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    comments = _list_workspace_records('workspace_comments', workspace_id)
    if file_id:
        comments = [comment for comment in comments if comment.get('file_id') == file_id]
    if status:
        comments = [comment for comment in comments if comment.get('status') == status]
    profiles = _student_profiles([comment.get('student_id') for comment in comments])
    for comment in comments:
        profile = profiles.get(comment.get('student_id')) or {}
        comment['name'] = profile.get('name')
    return {'status': 'success', 'total': len(comments), 'comments': comments}


@router.post('/{workspace_id}/comments')
def create_workspace_comment(
    workspace_id: str,
    request: CommentCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    body = request.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail='Comment cannot be blank.')
    if request.file_id:
        file = _workspace_file_by_id(workspace_id, request.file_id)
        if file.get('type', 'file') != 'file':
            raise HTTPException(status_code=422, detail='Comments must target a file.')
    if request.parent_comment_id and not _find_workspace_record(
        'workspace_comments', workspace_id, request.parent_comment_id
    ):
        raise HTTPException(status_code=404, detail='Parent comment not found.')
    now = _now()
    document = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        'file_id': request.file_id,
        'student_id': student_id,
        'body': body,
        'line_start': request.line_start,
        'line_end': request.line_end,
        'parent_comment_id': request.parent_comment_id,
        'status': 'open',
        'created_at': now,
        'updated_at': now,
    }
    comment = _insert_workspace_record('workspace_comments', document)
    _record_workspace_activity(workspace_id, student_id, 'created_comment', request.file_id)
    _publish_workspace_event(workspace_id, {'type': 'COMMENT_EVENT', 'action': 'created'})
    return {'status': 'success', 'comment': comment}


@router.patch('/{workspace_id}/comments/{comment_id}')
def update_workspace_comment(
    workspace_id: str,
    comment_id: str,
    request: CommentUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    comment = _find_workspace_record('workspace_comments', workspace_id, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail='Workspace comment not found.')
    if comment.get('student_id') != student_id and not _is_leader(role):
        raise HTTPException(status_code=403, detail='You can only edit your own comments.')
    updates = request.model_dump(exclude_unset=True)
    if 'body' in updates and updates['body'] is not None:
        updates['body'] = updates['body'].strip()
        if not updates['body']:
            raise HTTPException(status_code=422, detail='Comment cannot be blank.')
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        raise HTTPException(status_code=422, detail='No comment updates provided.')
    updates['updated_at'] = _now()
    try:
        result = get_collection('workspace_comments').update_one(
            {'workspace_id': workspace_id, 'id': comment_id},
            {'$set': updates},
        )
    except Exception as error:
        logger.exception('Failed to update workspace comment %s', comment_id)
        raise HTTPException(status_code=500, detail='Could not update comment.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Workspace comment not found.')
    comment = _find_workspace_record('workspace_comments', workspace_id, comment_id)
    if updates.get('status') == 'resolved':
        _record_workspace_activity(workspace_id, student_id, 'resolved_comment', comment.get('file_id'))
    _publish_workspace_event(workspace_id, {'type': 'COMMENT_EVENT', 'action': 'updated'})
    return {'status': 'success', 'comment': _workspace_response(comment)}


@router.delete('/{workspace_id}/comments/{comment_id}')
def delete_workspace_comment(
    workspace_id: str,
    comment_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, role = _workspace_access(workspace_id, student_id)
    comment = _find_workspace_record('workspace_comments', workspace_id, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail='Workspace comment not found.')
    if comment.get('student_id') != student_id and not _is_leader(role):
        raise HTTPException(
            status_code=403,
            detail='Only the comment author or workspace leader can delete this comment.',
        )
    try:
        result = get_collection('workspace_comments').delete_one(
            {'workspace_id': workspace_id, 'id': comment_id}
        )
        if not result.deleted_count:
            raise HTTPException(status_code=404, detail='Workspace comment not found.')
        get_collection('workspace_comments').update_many(
            {'workspace_id': workspace_id, 'parent_comment_id': comment_id},
            {'$set': {'parent_comment_id': None}},
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception('Failed to delete workspace comment %s', comment_id)
        raise HTTPException(status_code=500, detail='Could not delete comment.') from error
    _publish_workspace_event(workspace_id, {'type': 'COMMENT_EVENT', 'action': 'deleted'})
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Task board
# ---------------------------------------------------------------------------


@router.get('/{workspace_id}/tasks')
def list_workspace_tasks(
    workspace_id: str,
    status: Optional[str] = Query(default=None, max_length=30),
    assignee: Optional[str] = Query(default=None, max_length=100),
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    tasks = _list_workspace_records('workspace_tasks', workspace_id)
    if status:
        tasks = [task for task in tasks if task.get('status') == status]
    if assignee:
        tasks = [task for task in tasks if task.get('assignee_student_id') == assignee]
    return {'status': 'success', 'total': len(tasks), 'tasks': tasks}


@router.post('/{workspace_id}/tasks')
def create_workspace_task(
    workspace_id: str,
    request: TaskCreateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace = _require_editor(workspace_id, student_id)
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail='Task title cannot be blank.')
    if request.assignee_student_id and not any(
        member.get('student_id') == request.assignee_student_id
        for member in _workspace_members(workspace)
    ):
        raise HTTPException(status_code=422, detail='Assignee must be a workspace member.')
    now = _now()
    document = {
        'id': uuid.uuid4().hex,
        'workspace_id': workspace_id,
        **request.model_dump(),
        'title': title,
        'created_by': student_id,
        'created_at': now,
        'updated_at': now,
    }
    task = _insert_workspace_record('workspace_tasks', document)
    if request.assignee_student_id and request.assignee_student_id != student_id:
        _notify_student(
            workspace_id,
            request.assignee_student_id,
            'task_assigned',
            {'task_id': task['id'], 'title': title},
        )
    _record_workspace_activity(workspace_id, student_id, 'created_task', title)
    _publish_workspace_event(workspace_id, {'type': 'TASK_EVENT', 'action': 'created'})
    return {'status': 'success', 'task': task}


@router.patch('/{workspace_id}/tasks/{task_id}')
def update_workspace_task(
    workspace_id: str,
    task_id: str,
    request: TaskUpdateRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace = _require_editor(workspace_id, student_id)
    updates = request.model_dump(exclude_unset=True)
    if 'title' in updates and updates['title'] is not None:
        updates['title'] = updates['title'].strip()
        if not updates['title']:
            raise HTTPException(status_code=422, detail='Task title cannot be blank.')
    assignee_id = updates.get('assignee_student_id')
    if assignee_id and not any(
        member.get('student_id') == assignee_id
        for member in _workspace_members(workspace)
    ):
        raise HTTPException(status_code=422, detail='Assignee must be a workspace member.')
    for field in ('title', 'status', 'priority'):
        if updates.get(field) is None:
            updates.pop(field, None)
    if not updates:
        raise HTTPException(status_code=422, detail='No task updates provided.')
    updates['updated_at'] = _now()
    try:
        result = get_collection('workspace_tasks').update_one(
            {'workspace_id': workspace_id, 'id': task_id},
            {'$set': updates},
        )
    except Exception as error:
        logger.exception('Failed to update workspace task %s', task_id)
        raise HTTPException(status_code=500, detail='Could not update task.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Workspace task not found.')
    task = _find_workspace_record('workspace_tasks', workspace_id, task_id)
    if updates.get('status') == 'done':
        _record_workspace_activity(workspace_id, student_id, 'completed_task', task.get('title'))
        if task.get('created_by') and task.get('created_by') != student_id:
            _notify_student(
                workspace_id,
                task['created_by'],
                'task_completed',
                {'task_id': task_id, 'title': task.get('title')},
            )
    _publish_workspace_event(workspace_id, {'type': 'TASK_EVENT', 'action': 'updated'})
    return {'status': 'success', 'task': _workspace_response(task)}


@router.delete('/{workspace_id}/tasks/{task_id}')
def delete_workspace_task(
    workspace_id: str,
    task_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    try:
        result = get_collection('workspace_tasks').delete_one(
            {'workspace_id': workspace_id, 'id': task_id}
        )
    except Exception as error:
        logger.exception('Failed to delete workspace task %s', task_id)
        raise HTTPException(status_code=500, detail='Could not delete task.') from error
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail='Workspace task not found.')
    _publish_workspace_event(workspace_id, {'type': 'TASK_EVENT', 'action': 'deleted'})
    return {'status': 'success'}


# ---------------------------------------------------------------------------
# Assistant, sandbox run, activity, analytics, notifications
# ---------------------------------------------------------------------------


@router.post('/{workspace_id}/assistant/ask')
def ask_workspace_assistant(
    workspace_id: str,
    request: AssistantAskRequest,
    student_id: str = Depends(verify_jwt_student),
):
    workspace, _ = _workspace_access(workspace_id, student_id)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail='Question cannot be blank.')
    code = request.code
    file_path = None
    if request.file_id:
        file = _workspace_file_by_id(workspace_id, request.file_id)
        file_path = _file_path(file)
        if code is None:
            code = file.get('content')
    result = ask_assistant(question, student_id, code=code, file_path=file_path)
    if result.get('status') != 'success':
        raise HTTPException(status_code=503, detail=result.get('reply', 'Assistant unavailable.'))
    return {'status': 'success', 'answer': result['reply']}


@router.post('/{workspace_id}/code/run')
def run_workspace_code(
    workspace_id: str,
    request: CodeRunRequest,
    student_id: str = Depends(verify_jwt_student),
):
    _require_editor(workspace_id, student_id)
    result = java_sandbox.run(request.code, stdin=request.stdin or '', language=request.language)
    _record_workspace_activity(workspace_id, student_id, 'ran_code')
    return {'status': 'success', 'result': result}


@router.get('/{workspace_id}/activity')
def list_activity(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
    limit: int = Query(default=100, ge=1, le=500),
    actor_student_id: Optional[str] = Query(default=None, max_length=100),
    action: Optional[str] = Query(default=None, min_length=1, max_length=100),
):
    _workspace_access(workspace_id, student_id)
    query: Dict[str, Any] = {'workspace_id': workspace_id}
    if actor_student_id:
        query['student_id'] = actor_student_id.strip()
    if action:
        query['action'] = action.strip()
    try:
        activities = []
        for doc in get_collection('activity_log').find(query).sort('timestamp', -1):
            if len(activities) >= limit:
                break
            activities.append({k: v for k, v in doc.items() if k != '_id'})
    except Exception as error:
        logger.exception('Failed to load activity log')
        raise HTTPException(status_code=500, detail='Could not load activity.') from error
    profiles = _student_profiles([activity.get('student_id') for activity in activities])
    for activity in activities:
        profile = profiles.get(activity.get('student_id')) or {}
        activity['name'] = profile.get('name')
    return {'status': 'success', 'total': len(activities), 'activities': activities}


@router.get('/{workspace_id}/analytics')
def workspace_analytics(workspace_id: str, student_id: str = Depends(verify_jwt_student)):
    workspace, role = _workspace_access(workspace_id, student_id)
    if not _is_leader(role):
        raise HTTPException(status_code=403, detail='Only the workspace leader can view analytics.')
    members = _workspace_members(workspace)
    try:
        files = _active_workspace_files(workspace_id)
        versions = list(get_collection('file_versions').find({'workspace_id': workspace_id}))
        messages = list(get_collection('workspace_chat').find({'workspace_id': workspace_id}))
        comments = list(get_collection('workspace_comments').find({'workspace_id': workspace_id}))
        tasks = list(get_collection('workspace_tasks').find({'workspace_id': workspace_id}))
        activities = list(get_collection('activity_log').find({'workspace_id': workspace_id}))
    except Exception as error:
        logger.exception('Failed to compute workspace analytics')
        raise HTTPException(status_code=500, detail='Could not load analytics.') from error

    member_stats: Dict[str, Dict[str, Any]] = {}
    for member in members:
        member_id = member.get('student_id')
        member_stats[member_id] = {
            'student_id': member_id,
            'name': member.get('name'),
            'color': member.get('color'),
            'role': member.get('role'),
            'joined_at': member.get('joined_at'),
            'edits': 0,
            'lines_changed': 0,
            'messages': 0,
            'comments': 0,
            'tasks_created': 0,
            'tasks_completed': 0,
        }
    for version in versions:
        stats = member_stats.get(version.get('student_id'))
        if stats is not None:
            stats['edits'] += 1
            stats['lines_changed'] += max(
                1, (version.get('content') or '').count('\n') + 1
            )
    for message in messages:
        stats = member_stats.get(message.get('student_id'))
        if stats is not None:
            stats['messages'] += 1
    for comment in comments:
        stats = member_stats.get(comment.get('student_id'))
        if stats is not None:
            stats['comments'] += 1
    for task in tasks:
        creator = member_stats.get(task.get('created_by'))
        if creator is not None:
            creator['tasks_created'] += 1
        if task.get('status') == 'done':
            assignee = member_stats.get(task.get('assignee_student_id'))
            if assignee is not None:
                assignee['tasks_completed'] += 1

    activity_by_day: Dict[str, int] = {}
    for activity in activities:
        timestamp = activity.get('timestamp') or ''
        day = timestamp[:10]
        if day:
            activity_by_day[day] = activity_by_day.get(day, 0) + 1

    return {
        'status': 'success',
        'analytics': {
            'totals': {
                'members': len(members),
                'files': len([f for f in files if f.get('type', 'file') == 'file']),
                'folders': len([f for f in files if f.get('type') == 'folder']),
                'versions': len(versions),
                'messages': len(messages),
                'comments': len(comments),
                'open_comments': len([c for c in comments if c.get('status') == 'open']),
                'tasks': len(tasks),
                'tasks_done': len([t for t in tasks if t.get('status') == 'done']),
                'activities': len(activities),
            },
            'members': list(member_stats.values()),
            'activity_by_day': [
                {'date': day, 'count': count}
                for day, count in sorted(activity_by_day.items())
            ],
        },
    }


@router.get('/{workspace_id}/notifications')
def list_workspace_notifications(
    workspace_id: str,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    query: Dict[str, Any] = {'workspace_id': workspace_id, 'student_id': student_id}
    if unread_only:
        query['status'] = 'unread'
    try:
        notifications = []
        for item in (
            get_collection('workspace_notifications').find(query).sort('created_at', -1)
        ):
            if len(notifications) >= limit:
                break
            notifications.append(_workspace_response(item))
        unread_count = get_collection('workspace_notifications').count_documents(
            {'workspace_id': workspace_id, 'student_id': student_id, 'status': 'unread'}
        )
    except Exception as error:
        logger.exception('Failed to list workspace notifications')
        raise HTTPException(status_code=500, detail='Could not load notifications.') from error
    return {
        'status': 'success',
        'total': len(notifications),
        'unread_count': unread_count,
        'notifications': notifications,
    }


@router.patch('/{workspace_id}/notifications/{notification_id}/read')
def mark_workspace_notification_read(
    workspace_id: str,
    notification_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    try:
        result = get_collection('workspace_notifications').update_one(
            {'workspace_id': workspace_id, 'student_id': student_id, 'id': notification_id},
            {'$set': {'status': 'read', 'read_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to mark workspace notification as read')
        raise HTTPException(status_code=500, detail='Could not update notification.') from error
    if not result.matched_count:
        raise HTTPException(status_code=404, detail='Notification not found.')
    return {'status': 'success'}


@router.post('/{workspace_id}/notifications/read-all')
def mark_all_workspace_notifications_read(
    workspace_id: str,
    student_id: str = Depends(verify_jwt_student),
):
    _workspace_access(workspace_id, student_id)
    try:
        get_collection('workspace_notifications').update_many(
            {'workspace_id': workspace_id, 'student_id': student_id, 'status': 'unread'},
            {'$set': {'status': 'read', 'read_at': _now()}},
        )
    except Exception as error:
        logger.exception('Failed to mark workspace notifications as read')
        raise HTTPException(status_code=500, detail='Could not update notifications.') from error
    return {'status': 'success'}
