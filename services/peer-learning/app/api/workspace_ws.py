import asyncio
import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.student_routes import decode_student_token
from app.services.mongodb import get_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/workspaces', tags=['Project Workspace'])

COLOR_PALETTE = [
    '#2563eb', '#dc2626', '#059669', '#d97706',
    '#7c3aed', '#db2777', '#0891b2', '#65a30d',
]

MAX_MESSAGE_BYTES = 2 * 1024 * 1024
RATE_LIMIT_MESSAGES_PER_MINUTE = 600
RATE_LIMIT_BYTES_PER_MINUTE = 20 * 1024 * 1024
MEMBERSHIP_REVALIDATE_SECONDS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _color_for(student_id: str) -> str:
    if not student_id:
        return COLOR_PALETTE[0]
    index = int.from_bytes(hashlib.sha256(student_id.encode('utf-8')).digest()[:4], 'big')
    return COLOR_PALETTE[index % len(COLOR_PALETTE)]


def _student_name(student_id: str) -> str:
    try:
        doc = get_collection('students').find_one({'student_id': student_id})
        if doc and doc.get('name'):
            return str(doc['name'])
    except Exception:
        logger.debug('Failed to resolve student name for %s', student_id, exc_info=True)
    return student_id


def _normalize_role(role: Optional[str]) -> str:
    return {
        'owner': 'leader',
        'leader': 'leader',
        'editor': 'member',
        'member': 'member',
        'viewer': 'viewer',
    }.get(role or '', 'viewer')


def _resolve_membership(workspace_id: str, student_id: str) -> Optional[Dict[str, Any]]:
    """Return {'role', 'status'} for a member, or None when not a member."""
    try:
        collection = get_collection('workspaces')
        workspace = collection.find_one(
            {'workspace_id': workspace_id, 'owner_student_id': student_id}
        )
        if workspace:
            return {
                'role': 'leader',
                'status': workspace.get('status', 'active'),
            }
        workspace = collection.find_one(
            {'workspace_id': workspace_id, 'members.student_id': student_id}
        )
        if not workspace:
            return None
        member = next(
            (
                item
                for item in workspace.get('members', [])
                if item.get('student_id') == student_id
            ),
            None,
        )
        return {
            'role': _normalize_role(member.get('role') if member else None),
            'status': workspace.get('status', 'active'),
        }
    except Exception:
        logger.exception('Failed to resolve workspace membership for %s', workspace_id)
        return None


def _can_edit(membership: Dict[str, Any]) -> bool:
    return membership.get('role') in {'leader', 'member'} and membership.get('status') == 'active'


class WorkspaceManager:
    """Tracks live sockets per workspace and publishes events to them.

    ``publish_json`` / ``publish_student_json`` are synchronous so REST
    handlers (which may run in FastAPI's threadpool) can emit events; they
    schedule the async broadcast on the captured event loop.
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.connections: Dict[str, Dict[WebSocket, Dict[str, Any]]] = {}
        self.snapshots: Dict[str, Dict[str, str]] = {}

    # -- connection bookkeeping -------------------------------------------

    def register(
        self,
        workspace_id: str,
        websocket: WebSocket,
        student_id: str,
        membership: Dict[str, Any],
    ) -> None:
        self._loop = asyncio.get_running_loop()
        self.connections.setdefault(workspace_id, {})[websocket] = {
            'student_id': student_id,
            'role': membership.get('role', 'viewer'),
            'can_edit': _can_edit(membership),
            'name': _student_name(student_id),
            'color': _color_for(student_id),
            'last_revalidated': asyncio.get_running_loop().time(),
        }

    def unregister(self, workspace_id: str, websocket: WebSocket) -> Dict[str, Any]:
        room = self.connections.get(workspace_id, {})
        meta = room.pop(websocket, {})
        if not room:
            self.connections.pop(workspace_id, None)
        return meta

    def student_meta(self, workspace_id: str, websocket: WebSocket) -> Dict[str, Any]:
        return self.connections.get(workspace_id, {}).get(websocket, {})

    def refresh_meta(self, workspace_id: str, websocket: WebSocket, membership: Dict[str, Any]) -> None:
        meta = self.connections.get(workspace_id, {}).get(websocket)
        if meta is None:
            return
        meta['role'] = membership.get('role', 'viewer')
        meta['can_edit'] = _can_edit(membership)
        meta['last_revalidated'] = self._loop.time() if self._loop else 0.0

    def presence_list(self, workspace_id: str) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for meta in self.connections.get(workspace_id, {}).values():
            student_id = meta.get('student_id')
            if not student_id or student_id in seen:
                continue
            seen[student_id] = {
                'student_id': student_id,
                'name': meta.get('name', student_id),
                'color': meta.get('color'),
            }
        return list(seen.values())

    # -- broadcasting ------------------------------------------------------

    async def broadcast_json(
        self,
        workspace_id: str,
        event: Dict[str, Any],
        exclude: Optional[WebSocket] = None,
    ) -> None:
        dead: List[WebSocket] = []
        for websocket in list(self.connections.get(workspace_id, {})):
            if websocket is exclude:
                continue
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.unregister(workspace_id, websocket)

    async def send_json(self, websocket: WebSocket, event: Dict[str, Any]) -> bool:
        try:
            await websocket.send_json(event)
            return True
        except Exception:
            logger.debug('Failed to send workspace event %s', event.get('type'), exc_info=True)
            return False

    def publish_json(self, workspace_id: str, event: Dict[str, Any]) -> None:
        self._schedule(self.broadcast_json(workspace_id, event))

    def publish_student_json(
        self,
        workspace_id: str,
        student_id: str,
        event: Dict[str, Any],
    ) -> None:
        self._schedule(self._broadcast_to_student(workspace_id, student_id, event))

    async def _broadcast_to_student(
        self,
        workspace_id: str,
        student_id: str,
        event: Dict[str, Any],
    ) -> None:
        for websocket, meta in list(self.connections.get(workspace_id, {}).items()):
            if meta.get('student_id') != student_id:
                continue
            await self.send_json(websocket, event)

    def _schedule(self, coro) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            coro.close()
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            coro.close()

    # -- forced disconnects -------------------------------------------------

    async def disconnect_student(self, workspace_id: str, student_id: str) -> None:
        for websocket, meta in list(self.connections.get(workspace_id, {}).items()):
            if meta.get('student_id') != student_id:
                continue
            await self._close(websocket, 4403, 'Workspace access changed.')
            self.unregister(workspace_id, websocket)

    async def disconnect_workspace(self, workspace_id: str) -> None:
        for websocket in list(self.connections.get(workspace_id, {})):
            await self._close(websocket, 4403, 'Workspace is no longer available.')
            self.unregister(workspace_id, websocket)

    @staticmethod
    async def _close(websocket: WebSocket, code: int, reason: str) -> None:
        try:
            await websocket.close(code=code, reason=reason)
        except Exception:
            logger.debug('Failed to close workspace socket', exc_info=True)

    # -- document snapshots -------------------------------------------------

    def load_snapshot(self, workspace_id: str, file_id: str) -> Optional[str]:
        workspace_snaps = self.snapshots.get(workspace_id)
        if workspace_snaps is not None and file_id in workspace_snaps:
            return workspace_snaps[file_id]
        try:
            record = get_collection('workspace_sync').find_one(
                {'workspace_id': workspace_id, 'file_id': file_id}
            )
        except Exception:
            logger.exception('Failed to load workspace snapshot for %s', file_id)
            return None
        state = record.get('state') if record else None
        if state is not None:
            self.snapshots.setdefault(workspace_id, {})[file_id] = state
        return state

    def synced_file_ids(self, workspace_id: str) -> List[str]:
        if workspace_id not in self.snapshots:
            loaded: Dict[str, str] = {}
            try:
                records = get_collection('workspace_sync').find(
                    {'workspace_id': workspace_id}, {'file_id': 1, 'state': 1}
                )
                for record in records:
                    state = record.get('state')
                    if state:
                        loaded[record['file_id']] = state
            except Exception:
                logger.exception('Failed to list synced files for %s', workspace_id)
            self.snapshots[workspace_id] = loaded
        return [file_id for file_id, state in self.snapshots[workspace_id].items() if state]

    def save_snapshot(self, workspace_id: str, file_id: str, state_b64: str, student_id: Optional[str] = None) -> bool:
        self.snapshots.setdefault(workspace_id, {})[file_id] = state_b64
        try:
            get_collection('workspace_sync').update_one(
                {'workspace_id': workspace_id, 'file_id': file_id},
                {
                    '$set': {
                        'workspace_id': workspace_id,
                        'file_id': file_id,
                        'state': state_b64,
                        'updated_by': student_id,
                        'updated_at': _now_iso(),
                    }
                },
                upsert=True,
            )
            return True
        except Exception:
            logger.exception('Failed to save workspace snapshot for %s', file_id)
            return False

    def drop_snapshots_for_file(self, workspace_id: str, file_id: str) -> None:
        self.snapshots.get(workspace_id, {}).pop(file_id, None)
        try:
            get_collection('workspace_sync').delete_many(
                {'workspace_id': workspace_id, 'file_id': file_id}
            )
        except Exception:
            logger.debug('Failed to drop workspace snapshot for %s', file_id, exc_info=True)


manager = WorkspaceManager()


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------


class _RateLimiter:
    def __init__(self) -> None:
        self.window_start = 0.0
        self.messages = 0
        self.bytes = 0

    def check(self, size: int, loop_time: float) -> Optional[str]:
        window = int(loop_time // 60) * 60
        if window != self.window_start:
            self.window_start = window
            self.messages = 0
            self.bytes = 0
        self.messages += 1
        self.bytes += size
        if self.messages > RATE_LIMIT_MESSAGES_PER_MINUTE:
            return 'Too many messages. Slow down.'
        if self.bytes > RATE_LIMIT_BYTES_PER_MINUTE:
            return 'Message volume too high. Slow down.'
        return None


def _decode_state(update_value: Any) -> Optional[str]:
    """Validate a Yjs update payload and return it as a base64 string."""
    if isinstance(update_value, str):
        try:
            base64.b64decode(update_value, validate=True)
        except Exception:
            return None
        return update_value
    if isinstance(update_value, list) and all(isinstance(item, int) and 0 <= item <= 255 for item in update_value):
        return base64.b64encode(bytes(update_value)).decode('ascii')
    return None


def _build_chat_document(
    workspace_id: str,
    student_id: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    message = str(payload.get('message') or '').strip()
    if not message:
        return None
    now = _now_iso()
    return {
        'id': uuid.uuid4().hex,
        'type': 'CHAT_MESSAGE',
        'workspace_id': workspace_id,
        'student_id': student_id,
        'name': _student_name(student_id),
        'color': _color_for(student_id),
        'message': message,
        'message_type': payload.get('message_type') or 'text',
        'reply_to': payload.get('reply_to'),
        'mentions': list(payload.get('mentions') or []),
        'file_id': payload.get('file_id'),
        'line_number': payload.get('line_number'),
        'code_language': payload.get('code_language'),
        'timestamp': now,
        'created_at': now,
    }


def _persist_chat_document(document: Dict[str, Any]) -> bool:
    try:
        get_collection('workspace_chat').insert_one(dict(document))
        return True
    except Exception:
        logger.exception(
            'Failed to persist workspace chat message in %s',
            document.get('workspace_id'),
        )
        return False


def _notify_mentions(
    workspace_id: str,
    sender_id: str,
    document: Dict[str, Any],
) -> None:
    mentions = document.get('mentions') or []
    if not isinstance(mentions, list):
        return
    for mentioned_id in mentions:
        if not isinstance(mentioned_id, str) or not mentioned_id or mentioned_id == sender_id:
            continue
        notification = {
            'id': uuid.uuid4().hex,
            'workspace_id': workspace_id,
            'student_id': mentioned_id,
            'type': 'chat_mention',
            'status': 'unread',
            'message_id': document.get('id'),
            'created_by': sender_id,
            'created_at': _now_iso(),
        }
        try:
            get_collection('workspace_notifications').insert_one(notification)
        except Exception:
            logger.exception('Failed to create chat mention notification')
            continue
        notification.pop('_id', None)
        manager.publish_student_json(
            workspace_id,
            mentioned_id,
            {'type': 'NOTIFICATION', 'notification': notification},
        )


def _chat_relations_valid(workspace_id: str, payload: Dict[str, Any]) -> bool:
    reply_to = payload.get('reply_to')
    if reply_to:
        try:
            if not get_collection('workspace_chat').find_one(
                {'workspace_id': workspace_id, 'id': reply_to}
            ):
                return False
        except Exception:
            logger.exception('Failed to verify chat reply target')
            return False
    file_id = payload.get('file_id')
    if file_id:
        try:
            target = get_collection('workspace_files').find_one(
                {'workspace_id': workspace_id, 'id': file_id}
            )
        except Exception:
            logger.exception('Failed to verify chat file reference')
            return False
        if not target or target.get('type', 'file') != 'file':
            return False
    elif payload.get('line_number') is not None:
        return False
    return True


def _mentions_are_members(workspace_id: str, mentions: Any) -> List[str]:
    if not isinstance(mentions, list):
        return []
    cleaned = list(dict.fromkeys(item for item in mentions if isinstance(item, str) and item.strip()))
    if len(cleaned) > 50:
        return []
    if not cleaned:
        return []
    try:
        workspace = get_collection('workspaces').find_one(
            {'workspace_id': workspace_id},
            {'members.student_id': 1, 'owner_student_id': 1},
        )
    except Exception:
        logger.exception('Failed to verify chat mentions for %s', workspace_id)
        return []
    if not workspace:
        return []
    member_ids = {workspace.get('owner_student_id')}
    member_ids.update(member.get('student_id') for member in workspace.get('members', []))
    if any(mentioned not in member_ids for mentioned in cleaned):
        return []
    return cleaned


async def _handle_chat_message(
    websocket: WebSocket,
    workspace_id: str,
    student_id: str,
    payload: Dict[str, Any],
) -> None:
    if not _chat_relations_valid(workspace_id, payload):
        await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Chat message references an unknown target.'})
        return
    document = _build_chat_document(workspace_id, student_id, payload)
    if document is None:
        await manager.send_json(websocket, {'type': 'ERROR', 'message': "CHAT_MESSAGE requires a non-empty 'message'."})
        return
    document['mentions'] = _mentions_are_members(workspace_id, document.get('mentions'))
    if not _persist_chat_document(document):
        await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Could not save chat message.'})
        return
    await manager.broadcast_json(workspace_id, document)
    try:
        _notify_mentions(workspace_id, student_id, document)
    except Exception:
        logger.exception('Failed to notify workspace chat mentions')


async def _handle_yjs_update(
    websocket: WebSocket,
    workspace_id: str,
    payload: Dict[str, Any],
) -> None:
    meta = manager.student_meta(workspace_id, websocket)
    if not meta.get('can_edit'):
        await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Editor access is required.'})
        return
    file_id = payload.get('file_id')
    state_b64 = _decode_state(payload.get('update'))
    if not file_id or state_b64 is None:
        await manager.send_json(websocket, {'type': 'ERROR', 'message': "YJS_UPDATE requires 'file_id' and a valid 'update'."})
        return
    if not manager.save_snapshot(workspace_id, file_id, state_b64, meta.get('student_id')):
        await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Could not save workspace changes.'})
        return
    await manager.broadcast_json(
        workspace_id,
        {'type': 'YJS_UPDATE', 'file_id': file_id, 'update': state_b64, 'student_id': meta.get('student_id')},
        exclude=websocket,
    )


async def _handle_sync_request(websocket: WebSocket, workspace_id: str, payload: Dict[str, Any]) -> None:
    file_id = payload.get('file_id')
    if file_id:
        state = manager.load_snapshot(workspace_id, file_id)
        await manager.send_json(websocket, {'type': 'SYNC_STATE', 'file_id': file_id, 'state': state})
        return
    states = {
        candidate: manager.load_snapshot(workspace_id, candidate)
        for candidate in manager.synced_file_ids(workspace_id)
    }
    await manager.send_json(websocket, {'type': 'SYNC_STATE', 'file_id': None, 'states': states})


async def _handle_payload(
    websocket: WebSocket,
    workspace_id: str,
    student_id: str,
    payload: Dict[str, Any],
) -> None:
    msg_type = payload.get('type')
    if msg_type == 'PING':
        await manager.send_json(websocket, {'type': 'PONG'})
        return
    if msg_type == 'YJS_UPDATE':
        await _handle_yjs_update(websocket, workspace_id, payload)
        return
    if msg_type == 'SYNC_REQUEST':
        await _handle_sync_request(websocket, workspace_id, payload)
        return
    if msg_type == 'CHAT_MESSAGE':
        await _handle_chat_message(websocket, workspace_id, student_id, payload)
        return
    if msg_type == 'AWARENESS':
        payload = dict(payload)
        payload['student_id'] = student_id
        await manager.broadcast_json(workspace_id, payload, exclude=websocket)
        return
    logger.debug('Ignoring unknown workspace message type %s', msg_type)


async def _revalidate_membership(
    websocket: WebSocket,
    workspace_id: str,
    student_id: str,
) -> bool:
    membership = _resolve_membership(workspace_id, student_id)
    if membership is None:
        await manager._close(websocket, 4403, 'Workspace access changed.')
        return False
    manager.refresh_meta(workspace_id, websocket, membership)
    return True


@router.websocket('/ws/{workspace_id}')
async def workspace_socket_endpoint(
    websocket: WebSocket,
    workspace_id: str,
    token: Optional[str] = Query(default=None),
):
    if not token:
        auth = websocket.headers.get('authorization') or ''
        if auth.lower().startswith('bearer '):
            token = auth.split(' ', 1)[1].strip()
    if not token:
        await websocket.close(code=4401)
        return

    try:
        student_id = decode_student_token(token)
    except WebSocketDisconnect:
        raise
    except Exception:
        await websocket.close(code=4401)
        return

    membership = _resolve_membership(workspace_id, student_id)
    if membership is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    manager.register(workspace_id, websocket, student_id, membership)
    loop = asyncio.get_running_loop()

    try:
        await manager.send_json(
            websocket,
            {
                'type': 'INIT_STATE',
                'workspace_id': workspace_id,
                'student_id': student_id,
                'name': _student_name(student_id),
                'color': _color_for(student_id),
                'role': membership.get('role'),
                'can_edit': _can_edit(membership),
                'status': membership.get('status'),
                'presence': manager.presence_list(workspace_id),
                'synced_files': manager.synced_file_ids(workspace_id),
                'server_time': _now_iso(),
            },
        )
        await manager.broadcast_json(
            workspace_id,
            {
                'type': 'PRESENCE_JOINED',
                'student_id': student_id,
                'name': _student_name(student_id),
                'color': _color_for(student_id),
            },
            exclude=websocket,
        )

        limiter = _RateLimiter()
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=MEMBERSHIP_REVALIDATE_SECONDS,
                )
            except asyncio.TimeoutError:
                if not await _revalidate_membership(websocket, workspace_id, student_id):
                    break
                continue

            if raw.get('type') == 'websocket.disconnect':
                break
            text = raw.get('text')
            if text is None:
                await manager.send_json(
                    websocket,
                    {'type': 'ERROR', 'message': 'Binary frames are not supported. Send JSON text messages.'},
                )
                continue

            size = len(text.encode('utf-8'))
            if size > MAX_MESSAGE_BYTES:
                await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Message too large.'})
                continue
            violation = limiter.check(size, loop.time())
            if violation:
                await manager.send_json(websocket, {'type': 'ERROR', 'message': violation})
                continue

            try:
                payload = json.loads(text)
            except Exception:
                await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Invalid JSON payload.'})
                continue
            if not isinstance(payload, dict):
                await manager.send_json(websocket, {'type': 'ERROR', 'message': 'Payload must be a JSON object.'})
                continue

            try:
                await _handle_payload(websocket, workspace_id, student_id, payload)
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception('Workspace socket failed handling %s', payload.get('type'))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception('Workspace socket error in %s', workspace_id)
    finally:
        meta = manager.unregister(workspace_id, websocket)
        if meta:
            still_connected = any(
                other_meta.get('student_id') == student_id
                for other_meta in manager.connections.get(workspace_id, {}).values()
            )
            if not still_connected:
                await manager.broadcast_json(
                    workspace_id,
                    {'type': 'PRESENCE_LEFT', 'student_id': student_id},
                )
