import sys
import pathlib
import types
import os

CONFTEST_DIR = pathlib.Path(__file__).resolve().parent
SERVICE_DIR = CONFTEST_DIR.parents[1] / "services/peer-learning"
sys.path.insert(0, str(SERVICE_DIR))

# Ensure LLM calls take the deterministic "fallback / dummy key" branch in the
# service code so that NO real network LLM call is ever made.
os.environ.setdefault("OPENAI_API_KEY", "dummy_key")


# ---------------------------------------------------------------------------
# Stub the third-party packages that are NOT installed on the host but are
# imported (sometimes unconditionally) at module-import time by the service.
# The service only uses these symbols at *runtime* for LLM calls, which we
# never reach because we force the fallback paths (dummy API key) and override
# the DB layer below.
# ---------------------------------------------------------------------------

def _make_openai_stub():
    mod = types.ModuleType("openai")

    class _OpenAIClient:
        def __init__(self, *args, **kwargs):
            # student_agent creates `client = OpenAI(api_key=...)` at import time.
            pass

    mod.OpenAI = _OpenAIClient
    mod.OpenAIError = Exception
    return mod


def _make_langchain_openai_stub():
    mod = types.ModuleType("langchain_openai")

    class _ChatOpenAI:
        def __init__(self, *args, **kwargs):
            self.content = "{}"

        def invoke(self, *args, **kwargs):
            class _Resp:
                content = "{}"

            return _Resp()

    class _OpenAIEmbeddings:
        def __init__(self, *args, **kwargs):
            pass

        def embed_documents(self, texts):
            return [[0.0] * 4] * len(texts)

        def embed_query(self, text):
            return [0.0] * 4

    mod.ChatOpenAI = _ChatOpenAI
    mod.OpenAIEmbeddings = _OpenAIEmbeddings
    return mod


def _make_socketio_stub():
    mod = types.ModuleType("socketio")

    class _AsyncServer:
        def __init__(self, *args, **kwargs):
            pass

        def event(self, fn):
            return fn

        async def enter_room(self, *a, **k):
            pass

        async def emit(self, *a, **k):
            pass

    class _ASGIApp:
        def __init__(self, *args, **kwargs):
            pass

    mod.AsyncServer = _AsyncServer
    mod.ASGIApp = _ASGIApp
    return mod


for _name, _factory in [
    ("openai", _make_openai_stub),
    ("langchain_openai", _make_langchain_openai_stub),
    ("socketio", _make_socketio_stub),
]:
    if _name not in sys.modules:
        sys.modules[_name] = _factory()


# ---------------------------------------------------------------------------
# In-memory fake MongoDB backend so the service runs with zero real DB.
# ---------------------------------------------------------------------------

def _matches(doc, query):
    """Very small pymongo-query matcher: supports dict equality and $in."""

    def _one(key, expected, value):
        if key.startswith("$"):
            return True
        # dotted keys are not used by this codebase beyond trivial nesting
        if isinstance(expected, dict) and not key.startswith("$"):
            # operators like {"$in": [...]} or {"$gt": ...}
            if "$in" in expected:
                return value in expected["$in"]
            if "$gt" in expected:
                return value is not None and value > expected["$gt"]
            # nested compound match on same value (rare in this codebase)
            return all(False for _ in range(0))
        return expected is None or value == expected

    for key, expected in (query or {}).items():
        if not _one(key, expected, doc.get(key)):
            return False
    return True


def _apply_update(doc, update):
    for key, value in (update or {}).items():
        if key == "$set":
            doc.update(value)
        elif key == "$setOnInsert":
            pass
        elif key == "$push":
            for k, v in value.items():
                doc.setdefault(k, []).append(v)
        elif key == "$pull":
            for k, v in value.items():
                if isinstance(doc.get(k), list):
                    doc[k] = [item for item in doc[k] if item != v]


class _Seq:
    def __init__(self, start):
        self._n = start

    def __call__(self):
        self._n += 1
        return self._n


class FakeCollection:
    """Minimal read-only in-memory collection implementing the pymongo surface
    the peer-learning service actually touches."""

    def __init__(self, name, docs):
        self.name = name
        self._docs = docs
        self._ids = _Seq(0)

    def insert_one(self, document):
        doc = dict(document)
        if "_id" not in doc:
            doc["_id"] = self._ids()
        self._docs.append(doc)
        return _Result(doc["_id"])

    def insert_many(self, documents):
        ids = []
        for document in documents:
            ids.append(self.insert_one(document).inserted_id)
        return _Result(ids)

    def find_one(self, query=None, sort=None):
        for doc in self._docs:
            if _matches(doc, query):
                return doc
        return None

    def find(self, query=None, sort=None, projection=None):
        return [doc for doc in self._docs if _matches(doc, query)]

    def update_one(self, query, update, upsert=False):
        for doc in self._docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                return _UpdateResult(1, 1)
        if upsert:
            new_doc = dict(query or {})
            _apply_update(new_doc, update)
            self.insert_one(new_doc)
            return _UpdateResult(1, 1)
        return _UpdateResult(0, 0)

    def update_many(self, query, update):
        n = 0
        for doc in self._docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                n += 1
        return _UpdateResult(n, n)

    def delete_many(self, query):
        before = len(self._docs)
        self._docs[:] = [doc for doc in self._docs if not _matches(doc, query)]
        return _UpdateResult(before - len(self._docs), 0)

    def count_documents(self, query=None):
        return sum(1 for doc in self._docs if _matches(doc, query))

    def create_index(self, *args, **kwargs):
        return "idx"


class _Result:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _UpdateResult:
    matched_count = 0
    modified_count = 0

    def __init__(self, matched, modified):
        self.matched_count = matched
        self.modified_count = modified


_FAKE_STORE = {}


def reset_fake_db():
    """Clear all fake collections (used between tests)."""
    _FAKE_STORE.clear()


def fake_get_collection(name):
    if name not in _FAKE_STORE:
        _FAKE_STORE[name] = []
    return FakeCollection(name, _FAKE_STORE[name])


# Patch the mongodb service module NOW (before the app, and thus the routers,
# are imported) so every `from app.services.mongodb import get_collection`
# binding inside the routers picks up the fake, network-free implementation.
import app.services.mongodb as _mongodb

_mongodb.get_collection = fake_get_collection
_mongodb.get_db = lambda: {"__fake__": True}
_mongodb.init_db = lambda: False
_mongodb.close_db = lambda: None
_mongodb.insert_record = lambda coll, rec: fake_get_collection(coll).insert_one(rec).inserted_id


# ---------------------------------------------------------------------------
# Shared TestClient + auth override fixtures
# ---------------------------------------------------------------------------

import pytest
from fastapi.testclient import TestClient
from app.api.student_routes import verify_jwt_student
from app.main import fastapi_app as _fastapi_app
import app.main as _main_module

TEST_STUDENT_ID = "STU_TEST_001"
_JWT_STUDENT = {"current": TEST_STUDENT_ID}


def _fake_auth():
    return _JWT_STUDENT["current"]


def set_auth_student(student_id):
    _JWT_STUDENT["current"] = student_id


@pytest.fixture()
def client():
    reset_fake_db()
    _fastapi_app.dependency_overrides[verify_jwt_student] = _fake_auth
    try:
        with TestClient(_fastapi_app) as c:
            yield c
    finally:
        _fastapi_app.dependency_overrides.pop(verify_jwt_student, None)
        reset_fake_db()


@pytest.fixture()
def real_client():
    """TestClient WITHOUT the auth dependency override, so the real JWT
    verification (verify_jwt_student) runs. DB is still faked."""
    reset_fake_db()
    try:
        with TestClient(_fastapi_app) as c:
            yield c
    finally:
        reset_fake_db()


@pytest.fixture()
def auth_student():
    def _set(student_id):
        set_auth_student(student_id)
    return _set


@pytest.fixture(autouse=True)
def _clean_state():
    reset_fake_db()
    yield
    reset_fake_db()
