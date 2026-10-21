"""Contract tests for the Project Workspace collaboration module.

These tests exercise the REST router (app/api/workspace_routes.py) and the
collaboration WebSocket (app/api/workspace_ws.py) against an in-memory fake
MongoDB, so they run without a live database or network access.
"""

import base64
import copy
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import workspace_routes, workspace_ws
from app.config import settings
from app.main import app

client = TestClient(app)

NOW = '2026-10-21T00:00:00+00:00'

STUDENTS = {
    'student-1': ('Asha Leader', 'asha@example.edu'),
    'student-2': ('Ben Member', 'ben@example.edu'),
    'student-3': ('Cara Member', 'cara@example.edu'),
    'student-4': ('Dev Viewer', 'dev@example.edu'),
}


# ---------------------------------------------------------------------------
# Fake MongoDB harness
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, matched_count=0, deleted_count=0, upserted_id=None):
        self.matched_count = matched_count
        self.deleted_count = deleted_count
        self.upserted_id = upserted_id


def _resolve(document, path):
    """Return candidate values for a (possibly dotted) query path."""
    current = [document]
    for segment in path.split('.'):
        nxt = []
        for item in current:
            if not isinstance(item, dict) or segment not in item:
                continue
            value = item[segment]
            if isinstance(value, list):
                nxt.extend(value)
            else:
                nxt.append(value)
        current = nxt
    return current


def _match(document, query):
    for key, expected in query.items():
        if key == '$or':
            if not any(_match(document, sub) for sub in expected):
                return False
        elif key == '$and':
            if not all(_match(document, sub) for sub in expected):
                return False
        else:
            values = _resolve(document, key)
            if isinstance(expected, dict) and any(
                str(operator).startswith('$') for operator in expected
            ):
                for operator, operand in expected.items():
                    if operator == '$ne':
                        if any(value == operand for value in values):
                            return False
                    elif operator == '$nin':
                        if any(value in operand for value in values):
                            return False
                    elif operator == '$in':
                        if not any(value in operand for value in values):
                            return False
                    elif operator == '$gt':
                        if not any(
                            value is not None and value > operand for value in values
                        ):
                            return False
                    elif operator == '$lt':
                        if not any(
                            value is not None and value < operand for value in values
                        ):
                            return False
                    elif operator == '$regex':
                        flags = (
                            re.IGNORECASE
                            if 'i' in str(expected.get('$options', ''))
                            else 0
                        )
                        if not any(
                            re.search(operand, str(value), flags)
                            for value in values
                            if value is not None
                        ):
                            return False
                    elif operator == '$options':
                        continue
                    else:
                        raise NotImplementedError(
                            f'Unsupported query operator {operator}'
                        )
            else:
                if not any(value == expected for value in values):
                    return False
    return True


def _apply_update(document, update, is_insert):
    for operator, fields in update.items():
        if operator == '$set':
            for key, value in fields.items():
                document[key] = copy.deepcopy(value)
        elif operator == '$setOnInsert':
            if is_insert:
                for key, value in fields.items():
                    document[key] = copy.deepcopy(value)
        elif operator == '$inc':
            for key, value in fields.items():
                document[key] = document.get(key, 0) + value
        elif operator == '$push':
            for key, value in fields.items():
                document.setdefault(key, []).append(copy.deepcopy(value))
        else:
            raise NotImplementedError(f'Unsupported update operator {operator}')


def _project(document, projection):
    if not projection:
        return document
    inclusion = any(value for key, value in projection.items() if value)
    if inclusion:
        result = {}
        if projection.get('_id', 1):
            result['_id'] = document['_id']
        for key, value in projection.items():
            if not value or key == '_id':
                continue
            root = key.split('.')[0]
            if root in document:
                result[root] = copy.deepcopy(document[root])
        return result
    result = copy.deepcopy(document)
    for key, value in projection.items():
        if not value:
            result.pop(key, None)
    return result


class FakeCursor:
    def __init__(self, documents):
        self._documents = documents

    def sort(self, key, direction=1):
        present = [doc for doc in self._documents if doc.get(key) is not None]
        missing = [doc for doc in self._documents if doc.get(key) is None]
        present.sort(key=lambda doc: doc[key], reverse=(direction == -1))
        self._documents = (missing + present) if direction == 1 else (present + missing)
        return self

    def limit(self, count):
        self._documents = self._documents[:count]
        return self

    def __iter__(self):
        return iter(self._documents)


class FakeCollection:
    def __init__(self):
        self._documents = []
        self._counter = 0

    def _next_id(self):
        self._counter += 1
        return f'fake-{self._counter}'

    def insert_one(self, document):
        if '_id' not in document:
            document['_id'] = self._next_id()
        self._documents.append(copy.deepcopy(document))
        return FakeResult()

    def insert_many(self, documents, ordered=True):
        for document in documents:
            self.insert_one(document)
        return FakeResult()

    def _matches(self, query):
        return [doc for doc in self._documents if _match(doc, query)]

    def find(self, query=None, projection=None):
        return FakeCursor(
            [
                _project(copy.deepcopy(doc), projection)
                for doc in self._matches(query or {})
            ]
        )

    def find_one(self, query=None, projection=None):
        for doc in self._matches(query or {}):
            return _project(copy.deepcopy(doc), projection)
        return None

    def update_one(self, query, update, upsert=False):
        for doc in self._matches(query):
            _apply_update(doc, update, is_insert=False)
            return FakeResult(matched_count=1)
        if upsert:
            new_doc = {}
            for key, value in query.items():
                if str(key).startswith('$'):
                    continue
                if isinstance(value, dict) and any(
                    str(operator).startswith('$') for operator in value
                ):
                    continue
                new_doc[key] = copy.deepcopy(value)
            if '_id' not in new_doc:
                new_doc['_id'] = self._next_id()
            _apply_update(new_doc, update, is_insert=True)
            self._documents.append(new_doc)
            return FakeResult(matched_count=0, upserted_id=new_doc['_id'])
        return FakeResult(matched_count=0)

    def update_many(self, query, update):
        matched = self._matches(query)
        for doc in matched:
            _apply_update(doc, update, is_insert=False)
        return FakeResult(matched_count=len(matched))

    def delete_one(self, query):
        for index, doc in enumerate(self._documents):
            if _match(doc, query):
                del self._documents[index]
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    def delete_many(self, query):
        remaining = [doc for doc in self._documents if not _match(doc, query)]
        deleted = len(self._documents) - len(remaining)
        self._documents = remaining
        return FakeResult(deleted_count=deleted)

    def count_documents(self, query):
        return len(self._matches(query))


class FakeDatabase:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        return self._collections.setdefault(name, FakeCollection())

    def raw(self, name):
        return self.collection(name)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(workspace_routes, 'get_collection', database.collection)
    monkeypatch.setattr(workspace_ws, 'get_collection', database.collection)
    workspace_ws.manager.snapshots.clear()
    workspace_ws.manager.connections.clear()
    for student_id, (name, email) in STUDENTS.items():
        database.collection('students').insert_one(
            {'student_id': student_id, 'name': name, 'email': email}
        )
    return database


def auth(student_id):
    token = jwt.encode(
        {
            'sub': student_id,
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {'Authorization': f'Bearer {token}'}


def token_for(student_id):
    return jwt.encode(
        {
            'sub': student_id,
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_workspace(owner='student-1', name='Algo Squad'):
    response = client.post(
        '/api/workspaces', json={'name': name}, headers=auth(owner)
    )
    assert response.status_code == 200
    return response.json()['workspace']


def seed_workspace(db, owner='student-1', members=None, status='active', wid='ws-1'):
    member_entries = [
        {'student_id': student_id, 'role': role, 'joined_at': NOW}
        for student_id, role in (members or [])
    ]
    db.collection('workspaces').insert_one(
        {
            'workspace_id': wid,
            'name': 'Algo Squad',
            'description': 'DSA practice',
            'visibility': 'private',
            'status': status,
            'owner_student_id': owner,
            'peer_pool_id': None,
            'project_id': None,
            'member_count': 1 + len(member_entries),
            'created_at': NOW,
            'updated_at': NOW,
            'members': [
                {'student_id': owner, 'role': 'leader', 'joined_at': NOW}
            ]
            + member_entries,
        }
    )
    return wid


def seed_file(
    db,
    wid='ws-1',
    file_id='file-1',
    path='Main.java',
    content='class Main {}',
    kind='file',
    owner='student-1',
):
    db.collection('workspace_files').insert_one(
        {
            'id': file_id,
            'workspace_id': wid,
            'name': path.rsplit('/', 1)[-1],
            'path': path,
            'type': kind,
            'content': content,
            'language': None if kind == 'folder' else 'java',
            'created_by': owner,
            'created_at': NOW,
            'updated_at': NOW,
        }
    )
    return file_id


def invite_and_accept(workspace_id, leader, invitee, role='member'):
    response = client.post(
        f'/api/workspaces/{workspace_id}/invite',
        json={'student_id': invitee, 'role': role},
        headers=auth(leader),
    )
    assert response.status_code == 200
    invite_id = response.json()['invitation']['id']
    accepted = client.post(
        f'/api/workspaces/invitations/{invite_id}/accept',
        headers=auth(invitee),
    )
    assert accepted.status_code == 200
    return invite_id


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------


def test_endpoints_require_authentication():
    assert client.get('/api/workspaces').status_code == 401
    assert client.post('/api/workspaces', json={'name': 'X'}).status_code == 401
    assert client.get('/api/workspaces/whatever').status_code == 401


def test_create_workspace_persists_owner_and_returns_leader_role():
    response = client.post(
        '/api/workspaces',
        json={'name': '  Algo Squad ', 'description': ' DSA practice '},
        headers=auth('student-1'),
    )
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'success'
    workspace = data['workspace']
    assert workspace['name'] == 'Algo Squad'
    assert workspace['description'] == 'DSA practice'
    assert workspace['role'] == 'leader'
    assert workspace['status'] == 'active'
    assert workspace['owner_student_id'] == 'student-1'
    assert workspace['workspace_id']

    fetched = client.get(
        f"/api/workspaces/{workspace['workspace_id']}", headers=auth('student-1')
    ).json()['workspace']
    assert fetched['role'] == 'leader'
    assert fetched['member_count'] == 1


def test_create_workspace_rejects_blank_name():
    response = client.post(
        '/api/workspaces', json={'name': '   '}, headers=auth('student-1')
    )
    assert response.status_code == 422


def test_list_workspaces_reports_roles_and_member_count():
    owned = create_workspace('student-1', 'Mine')
    shared = create_workspace('student-2', 'Theirs')
    invite_and_accept(shared['workspace_id'], 'student-2', 'student-1', role='viewer')

    response = client.get('/api/workspaces', headers=auth('student-1'))
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    by_name = {workspace['name']: workspace for workspace in data['workspaces']}
    assert by_name['Mine']['role'] == 'leader'
    assert by_name['Theirs']['role'] == 'viewer'
    assert by_name['Theirs']['member_count'] == 2


def test_update_archive_unarchive_and_purge_cascade():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    renamed = client.patch(
        f'/api/workspaces/{wid}',
        json={'name': 'Renamed Squad', 'description': 'now with goals'},
        headers=auth('student-1'),
    )
    assert renamed.status_code == 200
    fetched = client.get(f'/api/workspaces/{wid}', headers=auth('student-1')).json()[
        'workspace'
    ]
    assert fetched['name'] == 'Renamed Squad'
    assert fetched['description'] == 'now with goals'

    blank = client.patch(
        f'/api/workspaces/{wid}', json={'name': '  '}, headers=auth('student-1')
    )
    assert blank.status_code == 422

    archived = client.delete(f'/api/workspaces/{wid}', headers=auth('student-1'))
    assert archived.status_code == 200

    listed = client.get('/api/workspaces', headers=auth('student-1')).json()
    assert listed['total'] == 0
    listed_all = client.get(
        '/api/workspaces?include_archived=true', headers=auth('student-1')
    ).json()
    assert listed_all['total'] == 1
    assert listed_all['workspaces'][0]['status'] == 'archived'

    unarchived = client.post(f'/api/workspaces/{wid}/unarchive', headers=auth('student-1'))
    assert unarchived.status_code == 200
    fetched = client.get(f'/api/workspaces/{wid}', headers=auth('student-1')).json()[
        'workspace'
    ]
    assert fetched['status'] == 'active'


def test_purge_workspace_removes_workspace_documents(fake_db):
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']
    seed_file(fake_db, wid=wid)
    client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'goodbye notes'},
        headers=auth('student-1'),
    )

    purged = client.delete(f'/api/workspaces/{wid}/purge', headers=auth('student-1'))
    assert purged.status_code == 200
    assert client.get(f'/api/workspaces/{wid}', headers=auth('student-1')).status_code == 404
    assert fake_db.collection('workspace_files').count_documents({'workspace_id': wid}) == 0
    assert fake_db.collection('workspace_chat').count_documents({'workspace_id': wid}) == 0


def test_non_owner_cannot_update_or_archive():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']
    invite_and_accept(wid, 'student-1', 'student-2')

    assert (
        client.patch(
            f'/api/workspaces/{wid}', json={'name': 'Hijacked'}, headers=auth('student-2')
        ).status_code
        == 404
    )
    assert (
        client.delete(f'/api/workspaces/{wid}', headers=auth('student-2')).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Members, invitations, join keys
# ---------------------------------------------------------------------------


def test_invite_requires_registered_student_and_handles_duplicates():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    ghost = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'ghost-9'},
        headers=auth('student-1'),
    )
    assert ghost.status_code == 404

    first = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-2', 'role': 'viewer'},
        headers=auth('student-1'),
    )
    assert first.status_code == 200
    assert first.json()['invitation']['status'] == 'pending'
    assert first.json()['invitation']['role'] == 'viewer'

    duplicate = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-2'},
        headers=auth('student-1'),
    )
    assert duplicate.status_code == 409

    owner_invite = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-1'},
        headers=auth('student-1'),
    )
    assert owner_invite.status_code == 409


def test_member_cannot_invite():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']
    invite_and_accept(wid, 'student-1', 'student-2')

    response = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-3'},
        headers=auth('student-2'),
    )
    assert response.status_code == 403


def test_invite_accept_flow_updates_membership_and_pending_list(fake_db):
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    response = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-2', 'role': 'viewer'},
        headers=auth('student-1'),
    )
    invite_id = response.json()['invitation']['id']

    pending = client.get(
        '/api/workspaces/invitations/pending', headers=auth('student-2')
    ).json()
    assert len(pending['invitations']) == 1
    assert pending['invitations'][0]['id'] == invite_id
    assert pending['invitations'][0]['workspace']['name'] == 'Algo Squad'

    accepted = client.post(
        f'/api/workspaces/invitations/{invite_id}/accept', headers=auth('student-2')
    )
    assert accepted.status_code == 200
    assert accepted.json()['workspace_id'] == wid

    members = client.get(
        f'/api/workspaces/{wid}/members', headers=auth('student-1')
    ).json()
    assert members['total'] == 2
    roles = {member['student_id']: member['role'] for member in members['members']}
    assert roles == {'student-1': 'leader', 'student-2': 'viewer'}
    profiles = {
        member['student_id']: member['name'] for member in members['members']
    }
    assert profiles['student-2'] == 'Ben Member'

    listed = client.get('/api/workspaces', headers=auth('student-2')).json()
    assert listed['total'] == 1
    assert listed['workspaces'][0]['role'] == 'viewer'

    again = client.post(
        f'/api/workspaces/invitations/{invite_id}/accept', headers=auth('student-2')
    )
    assert again.status_code == 404

    owner_notification = fake_db.collection('workspace_notifications').find_one(
        {'workspace_id': wid, 'student_id': 'student-1', 'type': 'member_joined'}
    )
    assert owner_notification is not None


def test_role_update_remove_and_leave():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']
    invite_and_accept(wid, 'student-1', 'student-2', role='viewer')
    invite_and_accept(wid, 'student-1', 'student-3')

    promoted = client.patch(
        f'/api/workspaces/{wid}/members/student-2',
        json={'role': 'member'},
        headers=auth('student-1'),
    )
    assert promoted.status_code == 200
    members = client.get(
        f'/api/workspaces/{wid}/members', headers=auth('student-1')
    ).json()
    roles = {member['student_id']: member['role'] for member in members['members']}
    assert roles['student-2'] == 'member'

    self_promote = client.patch(
        f'/api/workspaces/{wid}/members/student-2',
        json={'role': 'viewer'},
        headers=auth('student-2'),
    )
    assert self_promote.status_code == 403

    removed = client.delete(
        f'/api/workspaces/{wid}/members/student-3', headers=auth('student-1')
    )
    assert removed.status_code == 200
    assert (
        client.get(f'/api/workspaces/{wid}', headers=auth('student-3')).status_code
        == 404
    )

    left = client.post(f'/api/workspaces/{wid}/leave', headers=auth('student-2'))
    assert left.status_code == 200
    assert (
        client.get(f'/api/workspaces/{wid}', headers=auth('student-2')).status_code
        == 404
    )

    leader_leave = client.post(f'/api/workspaces/{wid}/leave', headers=auth('student-1'))
    assert leader_leave.status_code == 409


def test_join_key_create_join_exhaust_and_revoke(fake_db):
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    created = client.post(
        f'/api/workspaces/{wid}/join-keys',
        json={'max_uses': 1, 'role': 'member'},
        headers=auth('student-1'),
    )
    assert created.status_code == 200
    join_key = created.json()['join_key']
    key_id = created.json()['key_id']
    assert re.fullmatch(r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}', join_key)

    joined = client.post(
        '/api/workspaces/join',
        json={'join_key': join_key},
        headers=auth('student-2'),
    )
    assert joined.status_code == 200
    assert joined.json() == {
        'status': 'success',
        'workspace_id': wid,
        'role': 'member',
    }

    members = client.get(
        f'/api/workspaces/{wid}/members', headers=auth('student-1')
    ).json()
    assert any(member['student_id'] == 'student-2' for member in members['members'])

    stored_key = fake_db.collection('join_keys').find_one({'id': key_id})
    assert stored_key['uses'] == 1
    assert stored_key['key_hash'] != join_key

    exhausted = client.post(
        '/api/workspaces/join',
        json={'join_key': join_key},
        headers=auth('student-3'),
    )
    assert exhausted.status_code == 403
    assert 'maximum uses' in exhausted.json()['detail']

    second = client.post(
        f'/api/workspaces/{wid}/join-keys',
        json={'max_uses': 5},
        headers=auth('student-1'),
    ).json()
    revoked = client.delete(
        f"/api/workspaces/{wid}/join-keys/{second['key_id']}",
        headers=auth('student-1'),
    )
    assert revoked.status_code == 200
    rejected = client.post(
        '/api/workspaces/join',
        json={'join_key': second['join_key']},
        headers=auth('student-3'),
    )
    assert rejected.status_code == 403
    assert 'revoked' in rejected.json()['detail']

    invalid = client.post(
        '/api/workspaces/join',
        json={'join_key': 'NOT-A-REAL-KEY-XX'},
        headers=auth('student-3'),
    )
    assert invalid.status_code == 422

    unknown = client.post(
        '/api/workspaces/join',
        json={'join_key': 'AAAA-BBBB-CCCC'},
        headers=auth('student-3'),
    )
    assert unknown.status_code == 404

    listed = client.get(
        f'/api/workspaces/{wid}/join-keys', headers=auth('student-1')
    ).json()
    assert len(listed['keys']) == 2
    assert listed['keys'][1]['is_active'] is False

    member_create = client.post(
        f'/api/workspaces/{wid}/join-keys',
        json={},
        headers=auth('student-2'),
    )
    assert member_create.status_code == 403


def test_join_rate_limited_after_five_attempts():
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    statuses = []
    for _ in range(6):
        response = client.post(
            '/api/workspaces/join',
            json={'join_key': 'AAAA-BBBB-CCCC'},
            headers=auth('student-2'),
        )
        statuses.append(response.status_code)
    assert statuses[:5] == [404] * 5
    assert statuses[5] == 429


def test_workspace_search_students():
    response = client.get(
        '/api/workspaces/students/search?q=ben', headers=auth('student-1')
    )
    assert response.status_code == 200
    students = response.json()['students']
    assert [student['student_id'] for student in students] == ['student-2']
    assert students[0]['name'] == 'Ben Member'


# ---------------------------------------------------------------------------
# Files, versions, trash
# ---------------------------------------------------------------------------


def test_files_crud_move_duplicate_versions_and_trash(fake_db):
    workspace = create_workspace('student-1')
    wid = workspace['workspace_id']

    folder = client.post(
        f'/api/workspaces/{wid}/folders',
        json={'name': 'src'},
        headers=auth('student-1'),
    )
    assert folder.status_code == 200
    assert folder.json()['file']['path'] == 'src'
    assert folder.json()['file']['type'] == 'folder'

    created = client.post(
        f'/api/workspaces/{wid}/files',
        json={
            'name': 'Main.java',
            'parent_path': 'src',
            'content': 'class Main {}',
        },
        headers=auth('student-1'),
    )
    assert created.status_code == 200
    file_id = created.json()['file']['id']
    assert created.json()['file']['path'] == 'src/Main.java'
    assert created.json()['file']['language'] == 'java'

    duplicate_path = client.post(
        f'/api/workspaces/{wid}/files',
        json={'name': 'Main.java', 'parent_path': 'src'},
        headers=auth('student-1'),
    )
    assert duplicate_path.status_code == 409

    orphan = client.post(
        f'/api/workspaces/{wid}/files',
        json={'name': 'Orphan.java', 'parent_path': 'missing'},
        headers=auth('student-1'),
    )
    assert orphan.status_code == 404

    updated = client.put(
        f'/api/workspaces/{wid}/files/{file_id}',
        json={'content': 'class Main { int x; }'},
        headers=auth('student-1'),
    )
    assert updated.status_code == 200
    assert updated.json()['file']['content'] == 'class Main { int x; }'

    client.put(
        f'/api/workspaces/{wid}/files/{file_id}',
        json={'content': 'class Main { int x; int y; }'},
        headers=auth('student-1'),
    )

    versions = client.get(
        f'/api/workspaces/{wid}/files/{file_id}/versions', headers=auth('student-1')
    ).json()
    assert versions['total'] == 2
    assert all('content' not in version for version in versions['versions'])
    assert all(version['name'] == 'Asha Leader' for version in versions['versions'])
    assert all(version['student_id'] == 'student-1' for version in versions['versions'])

    v2_id = None
    for version in versions['versions']:
        detail = client.get(
            f"/api/workspaces/{wid}/files/{file_id}/versions/{version['id']}",
            headers=auth('student-1'),
        ).json()['version']
        if detail['content'] == 'class Main { int x; }':
            v2_id = detail['id']
    assert v2_id

    restored = client.post(
        f'/api/workspaces/{wid}/files/{file_id}/versions/{v2_id}/restore',
        headers=auth('student-1'),
    )
    assert restored.status_code == 200
    assert restored.json()['content'] == 'class Main { int x; }'
    after_restore = client.get(
        f'/api/workspaces/{wid}/files/{file_id}', headers=auth('student-1')
    ).json()['file']
    assert after_restore['content'] == 'class Main { int x; }'
    assert (
        client.get(
            f'/api/workspaces/{wid}/files/{file_id}/versions', headers=auth('student-1')
        ).json()['total']
        == 3
    )

    moved = client.post(
        f'/api/workspaces/{wid}/files/{file_id}/move',
        json={'new_path': 'Main.java'},
        headers=auth('student-1'),
    )
    assert moved.status_code == 200
    assert moved.json()['path'] == 'Main.java'

    duplicated = client.post(
        f'/api/workspaces/{wid}/files/{file_id}/duplicate',
        headers=auth('student-1'),
    )
    assert duplicated.status_code == 200
    assert duplicated.json()['files'][0]['path'] == 'Main-copy.java'

    listed = client.get(f'/api/workspaces/{wid}/files', headers=auth('student-1')).json()
    assert listed['total'] == 3
    assert {file['path'] for file in listed['files']} == {
        'src',
        'Main.java',
        'Main-copy.java',
    }
    listed_slim = client.get(
        f'/api/workspaces/{wid}/files?include_content=false', headers=auth('student-1')
    ).json()
    assert all('content' not in file for file in listed_slim['files'])

    deleted = client.delete(
        f'/api/workspaces/{wid}/files/{file_id}', headers=auth('student-1')
    )
    assert deleted.status_code == 200
    trash_id = deleted.json()['trash_id']

    trash = client.get(f'/api/workspaces/{wid}/trash', headers=auth('student-1')).json()
    assert len(trash['items']) == 1
    assert trash['items'][0]['trash_id'] == trash_id

    restored_trash = client.post(
        f'/api/workspaces/{wid}/trash/{trash_id}/restore', headers=auth('student-1')
    )
    assert restored_trash.status_code == 200
    assert restored_trash.json()['files'][0]['path'] == 'Main.java'

    trash_again = client.delete(
        f'/api/workspaces/{wid}/files/{file_id}', headers=auth('student-1')
    ).json()
    purged = client.delete(
        f"/api/workspaces/{wid}/trash/{trash_again['trash_id']}",
        headers=auth('student-1'),
    )
    assert purged.status_code == 200
    assert (
        client.get(f'/api/workspaces/{wid}/trash', headers=auth('student-1')).json()[
            'items'
        ]
        == []
    )


def test_viewer_cannot_edit_files_but_can_read(fake_db):
    wid = seed_workspace(
        fake_db, members=[('student-4', 'viewer')]
    )
    seed_file(fake_db, wid=wid)

    assert (
        client.post(
            f'/api/workspaces/{wid}/files',
            json={'name': 'Nope.java'},
            headers=auth('student-4'),
        ).status_code
        == 403
    )
    assert (
        client.put(
            f'/api/workspaces/{wid}/files/file-1',
            json={'content': 'hacked'},
            headers=auth('student-4'),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f'/api/workspaces/{wid}/files/file-1', headers=auth('student-4')
        ).status_code
        == 403
    )
    readable = client.get(f'/api/workspaces/{wid}/files', headers=auth('student-4'))
    assert readable.status_code == 200
    assert readable.json()['total'] == 1


def test_archived_workspace_is_read_only(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    seed_file(fake_db, wid=wid)

    archived = client.delete(f'/api/workspaces/{wid}', headers=auth('student-1'))
    assert archived.status_code == 200

    assert (
        client.post(
            f'/api/workspaces/{wid}/files',
            json={'name': 'New.java'},
            headers=auth('student-2'),
        ).status_code
        == 403
    )
    assert (
        client.put(
            f'/api/workspaces/{wid}/files/file-1',
            json={'content': 'nope'},
            headers=auth('student-2'),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f'/api/workspaces/{wid}/chat',
            json={'message': 'still talking'},
            headers=auth('student-2'),
        ).status_code
        == 403
    )
    invite = client.post(
        f'/api/workspaces/{wid}/invite',
        json={'student_id': 'student-3'},
        headers=auth('student-1'),
    )
    assert invite.status_code == 409

    readable = client.get(f'/api/workspaces/{wid}/files', headers=auth('student-2'))
    assert readable.status_code == 200


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def test_chat_post_unread_read_edit_and_delete(fake_db):
    wid = seed_workspace(
        fake_db,
        members=[('student-2', 'member'), ('student-4', 'viewer')],
    )

    invalid_mention = client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'hello @ghost', 'mentions': ['ghost-9']},
        headers=auth('student-1'),
    )
    assert invalid_mention.status_code == 422

    bad_reply = client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'reply', 'reply_to': 'missing-id'},
        headers=auth('student-1'),
    )
    assert bad_reply.status_code == 404

    posted = client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'Hey @Ben, review src/Main.java', 'mentions': ['student-2']},
        headers=auth('student-1'),
    )
    assert posted.status_code == 200
    message = posted.json()['message']
    assert message['type'] == 'CHAT_MESSAGE'
    assert message['name'] == 'Asha Leader'
    assert message['color'].startswith('#')
    assert message['mentions'] == ['student-2']

    unread = client.get(
        f'/api/workspaces/{wid}/chat/unread', headers=auth('student-2')
    ).json()
    assert unread['unread_count'] == 1

    history = client.get(
        f'/api/workspaces/{wid}/chat?limit=10', headers=auth('student-2')
    ).json()
    assert history['total'] == 1
    assert history['unread_count'] == 1
    assert history['messages'][0]['id'] == message['id']

    read = client.post(f'/api/workspaces/{wid}/chat/read', headers=auth('student-2'))
    assert read.status_code == 200
    assert read.json()['unread_count'] == 0
    assert (
        client.get(
            f'/api/workspaces/{wid}/chat/unread', headers=auth('student-2')
        ).json()['unread_count']
        == 0
    )

    notification = fake_db.collection('workspace_notifications').find_one(
        {'workspace_id': wid, 'student_id': 'student-2', 'type': 'chat_mention'}
    )
    assert notification is not None
    assert notification['message_id'] == message['id']

    by_other = client.patch(
        f"/api/workspaces/{wid}/chat/{message['id']}",
        json={'message': 'hijacked'},
        headers=auth('student-2'),
    )
    assert by_other.status_code == 403

    edited = client.patch(
        f"/api/workspaces/{wid}/chat/{message['id']}",
        json={'message': 'Hey Ben, ping me'},
        headers=auth('student-1'),
    )
    assert edited.status_code == 200
    assert edited.json()['message']['message'] == 'Hey Ben, ping me'

    delete_by_viewer = client.delete(
        f"/api/workspaces/{wid}/chat/{message['id']}", headers=auth('student-4')
    )
    assert delete_by_viewer.status_code == 403

    deleted = client.delete(
        f"/api/workspaces/{wid}/chat/{message['id']}", headers=auth('student-1')
    )
    assert deleted.status_code == 200
    assert (
        client.get(f'/api/workspaces/{wid}/chat', headers=auth('student-1')).json()[
            'total'
        ]
        == 0
    )
    assert (
        fake_db.collection('workspace_notifications').count_documents(
            {'workspace_id': wid, 'message_id': message['id']}
        )
        == 0
    )


def test_chat_leader_can_delete_any_message(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    posted = client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'rule breaking'},
        headers=auth('student-2'),
    ).json()['message']

    deleted = client.delete(
        f"/api/workspaces/{wid}/chat/{posted['id']}", headers=auth('student-1')
    )
    assert deleted.status_code == 200


# ---------------------------------------------------------------------------
# Comments and tasks
# ---------------------------------------------------------------------------


def test_comments_crud_with_author_permissions(fake_db):
    wid = seed_workspace(
        fake_db, members=[('student-2', 'member'), ('student-4', 'viewer')]
    )
    seed_file(fake_db, wid=wid)

    created = client.post(
        f'/api/workspaces/{wid}/comments',
        json={
            'body': 'Consider a guard clause here.',
            'file_id': 'file-1',
            'line_start': 2,
            'line_end': 4,
        },
        headers=auth('student-4'),
    )
    assert created.status_code == 200
    comment = created.json()['comment']
    assert comment['status'] == 'open'
    assert comment['student_id'] == 'student-4'

    listed = client.get(
        f'/api/workspaces/{wid}/comments?file_id=file-1', headers=auth('student-2')
    ).json()
    assert listed['total'] == 1
    assert listed['comments'][0]['name'] == 'Dev Viewer'

    by_other = client.patch(
        f"/api/workspaces/{wid}/comments/{comment['id']}",
        json={'body': 'not mine'},
        headers=auth('student-2'),
    )
    assert by_other.status_code == 403

    resolved = client.patch(
        f"/api/workspaces/{wid}/comments/{comment['id']}",
        json={'status': 'resolved'},
        headers=auth('student-4'),
    )
    assert resolved.status_code == 200
    assert resolved.json()['comment']['status'] == 'resolved'

    open_only = client.get(
        f'/api/workspaces/{wid}/comments?status=open', headers=auth('student-1')
    ).json()
    assert open_only['total'] == 0

    reply = client.post(
        f'/api/workspaces/{wid}/comments',
        json={'body': 'Agreed.', 'parent_comment_id': comment['id']},
        headers=auth('student-2'),
    )
    assert reply.status_code == 200

    deleted = client.delete(
        f"/api/workspaces/{wid}/comments/{reply.json()['comment']['id']}",
        headers=auth('student-2'),
    )
    assert deleted.status_code == 200


def test_tasks_crud_assignee_validation_and_notifications(fake_db):
    wid = seed_workspace(
        fake_db, members=[('student-2', 'member'), ('student-4', 'viewer')]
    )

    viewer_create = client.post(
        f'/api/workspaces/{wid}/tasks',
        json={'title': 'Nope'},
        headers=auth('student-4'),
    )
    assert viewer_create.status_code == 403

    bad_assignee = client.post(
        f'/api/workspaces/{wid}/tasks',
        json={'title': 'Ghost task', 'assignee_student_id': 'ghost-9'},
        headers=auth('student-1'),
    )
    assert bad_assignee.status_code == 422

    created = client.post(
        f'/api/workspaces/{wid}/tasks',
        json={
            'title': 'Write unit tests',
            'assignee_student_id': 'student-2',
            'priority': 'high',
        },
        headers=auth('student-1'),
    )
    assert created.status_code == 200
    task = created.json()['task']
    assert task['status'] == 'todo'
    assert task['created_by'] == 'student-1'

    notification = fake_db.collection('workspace_notifications').find_one(
        {'workspace_id': wid, 'student_id': 'student-2', 'type': 'task_assigned'}
    )
    assert notification is not None

    completed = client.patch(
        f"/api/workspaces/{wid}/tasks/{task['id']}",
        json={'status': 'done'},
        headers=auth('student-2'),
    )
    assert completed.status_code == 200
    assert completed.json()['task']['status'] == 'done'

    activity = fake_db.collection('activity_log').find_one(
        {'workspace_id': wid, 'action': 'completed_task'}
    )
    assert activity is not None
    completion_notice = fake_db.collection('workspace_notifications').find_one(
        {'workspace_id': wid, 'student_id': 'student-1', 'type': 'task_completed'}
    )
    assert completion_notice is not None

    filtered = client.get(
        f'/api/workspaces/{wid}/tasks?status=done&assignee=student-2',
        headers=auth('student-1'),
    ).json()
    assert filtered['total'] == 1

    deleted = client.delete(
        f"/api/workspaces/{wid}/tasks/{task['id']}", headers=auth('student-2')
    )
    assert deleted.status_code == 200
    assert (
        client.get(f'/api/workspaces/{wid}/tasks', headers=auth('student-1')).json()[
            'total'
        ]
        == 0
    )


# ---------------------------------------------------------------------------
# Analytics, assistant, code run, notifications
# ---------------------------------------------------------------------------


def test_analytics_is_leader_only(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    seed_file(fake_db, wid=wid)
    client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'progress update'},
        headers=auth('student-2'),
    )

    denied = client.get(f'/api/workspaces/{wid}/analytics', headers=auth('student-2'))
    assert denied.status_code == 403

    allowed = client.get(f'/api/workspaces/{wid}/analytics', headers=auth('student-1'))
    assert allowed.status_code == 200
    analytics = allowed.json()['analytics']
    assert analytics['totals']['members'] == 2
    assert analytics['totals']['files'] == 1
    assert analytics['totals']['messages'] == 1
    stats = {item['student_id']: item for item in analytics['members']}
    assert stats['student-2']['messages'] == 1
    assert stats['student-1']['role'] == 'leader'


def test_assistant_ask_and_code_run(fake_db, monkeypatch):
    wid = seed_workspace(fake_db, members=[('student-4', 'viewer')])
    seed_file(fake_db, wid=wid)

    def fake_ask(question, student_id, code=None, file_path=None):
        assert question == 'How do loops work?'
        assert student_id == 'student-1'
        assert code == 'class Main {}'
        assert file_path == 'Main.java'
        return {'status': 'success', 'reply': 'Use a for loop.'}

    monkeypatch.setattr(workspace_routes, 'ask_assistant', fake_ask)
    answered = client.post(
        f'/api/workspaces/{wid}/assistant/ask',
        json={'question': 'How do loops work?', 'file_id': 'file-1'},
        headers=auth('student-1'),
    )
    assert answered.status_code == 200
    assert answered.json()['answer'] == 'Use a for loop.'

    class FakeSandbox:
        def run(self, code, stdin='', language='java'):
            assert code.startswith('class Main')
            assert stdin == '42'
            return {'stdout': '42', 'stderr': '', 'exit_code': 0}

    monkeypatch.setattr(workspace_routes, 'java_sandbox', FakeSandbox())
    ran = client.post(
        f'/api/workspaces/{wid}/code/run',
        json={'code': 'class Main {}', 'stdin': '42'},
        headers=auth('student-1'),
    )
    assert ran.status_code == 200
    assert ran.json()['result']['stdout'] == '42'

    viewer_run = client.post(
        f'/api/workspaces/{wid}/code/run',
        json={'code': 'class Main {}'},
        headers=auth('student-4'),
    )
    assert viewer_run.status_code == 403


def test_notifications_list_mark_read_and_read_all(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    client.post(
        f'/api/workspaces/{wid}/chat',
        json={'message': 'ping Ben', 'mentions': ['student-2']},
        headers=auth('student-1'),
    )
    client.post(
        f'/api/workspaces/{wid}/tasks',
        json={'title': 'Task for Ben', 'assignee_student_id': 'student-2'},
        headers=auth('student-1'),
    )

    listed = client.get(
        f'/api/workspaces/{wid}/notifications', headers=auth('student-2')
    ).json()
    assert listed['unread_count'] == 2
    types = {item['type'] for item in listed['notifications']}
    assert types == {'chat_mention', 'task_assigned'}

    unread_only = client.get(
        f'/api/workspaces/{wid}/notifications?unread_only=true',
        headers=auth('student-2'),
    ).json()
    assert unread_only['unread_count'] == 2

    target = listed['notifications'][0]
    read = client.patch(
        f"/api/workspaces/{wid}/notifications/{target['id']}/read",
        headers=auth('student-2'),
    )
    assert read.status_code == 200
    assert (
        client.get(
            f'/api/workspaces/{wid}/notifications', headers=auth('student-2')
        ).json()['unread_count']
        == 1
    )

    read_all = client.post(
        f'/api/workspaces/{wid}/notifications/read-all', headers=auth('student-2')
    )
    assert read_all.status_code == 200
    assert (
        client.get(
            f'/api/workspaces/{wid}/notifications', headers=auth('student-2')
        ).json()['unread_count']
        == 0
    )


def test_activity_log_records_actions(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    client.post(
        f'/api/workspaces/{wid}/files',
        json={'name': 'Main.java'},
        headers=auth('student-2'),
    )
    activity = client.get(
        f'/api/workspaces/{wid}/activity?action=created_file', headers=auth('student-1')
    ).json()
    assert activity['total'] == 1
    assert activity['activities'][0]['student_id'] == 'student-2'
    assert activity['activities'][0]['name'] == 'Ben Member'


def test_color_helpers_match_between_routes_and_ws():
    for student_id in ['a', 'student-1', 'xyz', '']:
        assert workspace_routes._color_for(student_id) == workspace_ws._color_for(
            student_id
        )


# ---------------------------------------------------------------------------
# WebSocket collaboration protocol
# ---------------------------------------------------------------------------


def test_websocket_rejects_missing_and_invalid_tokens(fake_db):
    wid = seed_workspace(fake_db)

    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect(f'/api/workspaces/ws/{wid}'):
            pass
    assert missing.value.code == 4401

    with pytest.raises(WebSocketDisconnect) as invalid:
        with client.websocket_connect(
            f'/api/workspaces/ws/{wid}?token=not-a-jwt'
        ):
            pass
    assert invalid.value.code == 4401


def test_websocket_rejects_non_member(fake_db):
    wid = seed_workspace(fake_db)
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            f'/api/workspaces/ws/{wid}?token={token_for("student-3")}'
        ):
            pass
    assert denied.value.code == 4403


def test_websocket_init_state_shape(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])
    seed_file(fake_db, wid=wid, file_id='synced-1')

    fake_db.collection('workspace_sync').insert_one(
        {'workspace_id': wid, 'file_id': 'synced-1', 'state': 'AAEC'}
    )
    workspace_ws.manager.snapshots.clear()

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-2")}'
    ) as socket:
        init = socket.receive_json()
        assert init['type'] == 'INIT_STATE'
        assert init['workspace_id'] == wid
        assert init['student_id'] == 'student-2'
        assert init['name'] == 'Ben Member'
        assert init['role'] == 'member'
        assert init['can_edit'] is True
        assert init['status'] == 'active'
        assert init['synced_files'] == ['synced-1']
        assert init['server_time']
        presence = init['presence']
        assert presence[0]['student_id'] == 'student-2'
        assert presence[0]['name'] == 'Ben Member'


def test_websocket_member_yjs_update_persists_syncs_and_relays(fake_db):
    wid = seed_workspace(
        fake_db, members=[('student-2', 'member')]
    )
    payload_state = base64.b64encode(b'full-yjs-state-v1').decode('ascii')

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-1")}'
    ) as leader_socket:
        assert leader_socket.receive_json()['type'] == 'INIT_STATE'
        with client.websocket_connect(
            f'/api/workspaces/ws/{wid}?token={token_for("student-2")}'
        ) as member_socket:
            assert member_socket.receive_json()['type'] == 'INIT_STATE'
            assert leader_socket.receive_json()['type'] == 'PRESENCE_JOINED'

            member_socket.send_json(
                {
                    'type': 'YJS_UPDATE',
                    'file_id': 'file-1',
                    'update': payload_state,
                }
            )

            relayed = leader_socket.receive_json()
            assert relayed['type'] == 'YJS_UPDATE'
            assert relayed['file_id'] == 'file-1'
            assert relayed['update'] == payload_state
            assert relayed['student_id'] == 'student-2'

            stored = fake_db.collection('workspace_sync').find_one(
                {'workspace_id': wid, 'file_id': 'file-1'}
            )
            assert stored['state'] == payload_state
            assert stored['updated_by'] == 'student-2'

            member_socket.send_json({'type': 'SYNC_REQUEST', 'file_id': 'file-1'})
            sync = member_socket.receive_json()
            assert sync['type'] == 'SYNC_STATE'
            assert sync['file_id'] == 'file-1'
            assert sync['state'] == payload_state

            member_socket.send_json({'type': 'PING'})
            assert member_socket.receive_json() == {'type': 'PONG'}


def test_websocket_viewer_cannot_edit(fake_db):
    wid = seed_workspace(fake_db, members=[('student-4', 'viewer')])
    state = base64.b64encode(b'nope').decode('ascii')

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-4")}'
    ) as socket:
        init = socket.receive_json()
        assert init['can_edit'] is False
        socket.send_json({'type': 'YJS_UPDATE', 'file_id': 'file-1', 'update': state})
        error = socket.receive_json()
        assert error['type'] == 'ERROR'
        assert error['message'] == 'Editor access is required.'
    assert (
        fake_db.collection('workspace_sync').count_documents({'workspace_id': wid})
        == 0
    )


def test_websocket_chat_broadcasts_to_all_and_persists(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-1")}'
    ) as leader_socket:
        assert leader_socket.receive_json()['type'] == 'INIT_STATE'
        with client.websocket_connect(
            f'/api/workspaces/ws/{wid}?token={token_for("student-2")}'
        ) as member_socket:
            assert member_socket.receive_json()['type'] == 'INIT_STATE'
            assert leader_socket.receive_json()['type'] == 'PRESENCE_JOINED'

            member_socket.send_json(
                {
                    'type': 'CHAT_MESSAGE',
                    'message': 'Hello from Ben',
                    'mentions': ['student-1'],
                }
            )

            from_leader = leader_socket.receive_json()
            from_member = member_socket.receive_json()
            assert from_leader['type'] == 'CHAT_MESSAGE'
            assert from_leader['student_id'] == 'student-2'
            assert from_leader['name'] == 'Ben Member'
            assert from_leader['message'] == 'Hello from Ben'
            assert from_leader['mentions'] == ['student-1']
            assert from_leader['id']
            assert from_member['id'] == from_leader['id']

    stored = fake_db.collection('workspace_chat').find_one({'workspace_id': wid})
    assert stored is not None
    assert stored['message'] == 'Hello from Ben'
    notice = fake_db.collection('workspace_notifications').find_one(
        {'workspace_id': wid, 'student_id': 'student-1', 'type': 'chat_mention'}
    )
    assert notice is not None
    assert notice['message_id'] == from_leader['id']


def test_websocket_rejects_invalid_payloads(fake_db):
    wid = seed_workspace(fake_db)

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-1")}'
    ) as socket:
        assert socket.receive_json()['type'] == 'INIT_STATE'

        socket.send_json(
            {'type': 'YJS_UPDATE', 'file_id': 'file-1', 'update': '!!not-base64!!'}
        )
        error = socket.receive_json()
        assert error['type'] == 'ERROR'
        assert 'valid' in error['message']

        socket.send_json(
            {'type': 'CHAT_MESSAGE', 'message': '   '}
        )
        error = socket.receive_json()
        assert error['type'] == 'ERROR'
        assert 'non-empty' in error['message']

        socket.send_text('not-json')
        error = socket.receive_json()
        assert error['type'] == 'ERROR'
        assert error['message'] == 'Invalid JSON payload.'


def test_websocket_awareness_relayed_with_sender_identity(fake_db):
    wid = seed_workspace(fake_db, members=[('student-2', 'member')])

    with client.websocket_connect(
        f'/api/workspaces/ws/{wid}?token={token_for("student-1")}'
    ) as leader_socket:
        assert leader_socket.receive_json()['type'] == 'INIT_STATE'
        with client.websocket_connect(
            f'/api/workspaces/ws/{wid}?token={token_for("student-2")}'
        ) as member_socket:
            assert member_socket.receive_json()['type'] == 'INIT_STATE'
            assert leader_socket.receive_json()['type'] == 'PRESENCE_JOINED'

            member_socket.send_json(
                {'type': 'AWARENESS', 'cursor': {'line': 3, 'column': 7}}
            )
            awareness = leader_socket.receive_json()
            assert awareness['type'] == 'AWARENESS'
            assert awareness['student_id'] == 'student-2'
            assert awareness['cursor'] == {'line': 3, 'column': 7}
