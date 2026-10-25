"""
Tests for authentication, session ownership, transcript storage and request limits.
"""
import time

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth import TOKEN_ALGORITHM, TOKEN_ISSUER, create_access_token
from app.main import app
from app.services.context_manager import ContextManager
from tests.conftest import auth_headers

OWNER = "student@wpi.edu"
OTHER = "intruder@wpi.edu"
SESSION_ID = "fedcba9876543210fedcba9876543210"


@pytest.fixture
def client(fake_redis):
    return TestClient(app)


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "true")
    monkeypatch.setenv("DEMO_USER_EMAIL", "demo@wpi.edu")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "correct horse battery staple")


@pytest.mark.unit
class TestAuthentication:
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/chat"),
        ("post", "/api/extract-transcript"),
        ("post", "/api/summarize"),
        ("get", "/api/status"),
        ("get", f"/api/chat/history/{SESSION_ID}"),
        ("delete", f"/api/chat/history/{SESSION_ID}"),
        ("post", "/api/admin/rebuild-pdf-index"),
    ])
    def test_protected_routes_require_token(self, client, method, path):
        response = client.request(method.upper(), path, json={} if method == "post" else None)
        assert response.status_code == 401

    def test_health_is_public(self, client):
        assert client.get("/api/health").status_code == 200

    def test_rejects_forged_token(self, client):
        forged = jwt.encode({"sub": OWNER, "iss": TOKEN_ISSUER, "iat": int(time.time()),
                             "exp": int(time.time()) + 60}, "x" * 40, algorithm=TOKEN_ALGORITHM)
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_rejects_expired_token(self, client, monkeypatch):
        monkeypatch.setenv("APP_TOKEN_TTL_SECONDS", "-1")
        response = client.get("/api/auth/me", headers=auth_headers())
        assert response.status_code == 401

    def test_admin_routes_need_admin_role(self, client, monkeypatch):
        response = client.post("/api/admin/rebuild-pdf-index", headers=auth_headers(OWNER))
        assert response.status_code == 403

        monkeypatch.setenv("ADMIN_EMAILS", "admin@wpi.edu")
        response = client.get("/api/chat/memory/stats", headers=auth_headers("admin@wpi.edu"))
        assert response.status_code != 403


@pytest.mark.unit
class TestDemoLogin:
    def test_disabled_by_default(self, client, monkeypatch):
        monkeypatch.delenv("DEMO_LOGIN_ENABLED", raising=False)
        assert client.get("/api/auth/config").json()["demo_login"] is False
        response = client.post("/api/auth/demo-login", json={"email": "demo@wpi.edu", "password": "x"})
        assert response.status_code == 404

    def test_wrong_password(self, client, demo_env):
        response = client.post("/api/auth/demo-login", json={"email": "demo@wpi.edu", "password": "nope"})
        assert response.status_code == 401

    def test_login_returns_working_token(self, client, demo_env):
        response = client.post("/api/auth/demo-login",
                               json={"email": "Demo@WPI.edu", "password": "correct horse battery staple"})
        assert response.status_code == 200
        token = response.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["email"] == "demo@wpi.edu"
        assert me.json()["roles"] == []


@pytest.mark.unit
class TestSessionOwnership:
    def test_other_user_cannot_read_or_delete_history(self, client, fake_redis):
        fake_redis.set(f"session_owner:{SESSION_ID}", OWNER)

        for method in ("get", "delete"):
            response = getattr(client, method)(f"/api/chat/history/{SESSION_ID}", headers=auth_headers(OTHER))
            assert response.status_code == 403

    def test_other_user_cannot_upload_into_session(self, client, fake_redis):
        fake_redis.set(f"session_owner:{SESSION_ID}", OWNER)
        response = client.post("/api/extract-transcript", headers=auth_headers(OTHER),
                               json={"pdf_base64": "JVBERi0=", "session_id": SESSION_ID})
        assert response.status_code == 403

    def test_other_user_cannot_chat_in_session(self, client, fake_redis):
        fake_redis.set(f"session_owner:{SESSION_ID}", OWNER)
        response = client.post("/api/chat", headers=auth_headers(OTHER),
                               json={"message": "hi", "session_id": SESSION_ID})
        assert response.status_code == 403

    def test_first_use_claims_session(self, client, fake_redis):
        from app.auth import User
        from app.services.session_access import claim_session

        claim_session(SESSION_ID, User(id=OWNER, email=OWNER, name="S"))
        assert fake_redis.get(f"session_owner:{SESSION_ID}") == OWNER
        # Owner can claim again (refresh), no exception
        claim_session(SESSION_ID, User(id=OWNER, email=OWNER, name="S"))

    def test_unknown_session_history_is_404(self, client):
        response = client.get(f"/api/chat/history/{SESSION_ID}", headers=auth_headers(OWNER))
        assert response.status_code == 404

    def test_malformed_session_id_rejected(self, client):
        response = client.get("/api/chat/history/short", headers=auth_headers(OWNER))
        assert response.status_code == 400


@pytest.mark.unit
class TestContextStorage:
    TRANSCRIPT = {"student_name": "Jane Roe", "gpa": 3.9, "courses": [{"course_code": "MIS 571"}]}

    def test_encrypted_at_rest_and_shared_across_workers(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        ContextManager(redis).set_student_context(SESSION_ID, self.TRANSCRIPT)

        raw = redis.get(f"student_context:{SESSION_ID}")
        assert "Jane" not in raw and "MIS 571" not in raw

        # A second manager on the same Redis (another worker) sees the same data
        context = ContextManager(redis).get_student_context(SESSION_ID)
        assert context.student_name == "Jane Roe"
        assert context.has_transcript()

    def test_ttl_set_and_clear(self):
        redis = fakeredis.FakeRedis(decode_responses=True)
        manager = ContextManager(redis, ttl_seconds=100)
        manager.set_student_context(SESSION_ID, self.TRANSCRIPT)
        assert 0 < redis.ttl(f"student_context:{SESSION_ID}") <= 100

        manager.clear_student_context(SESSION_ID)
        assert not manager.get_student_context(SESSION_ID).has_transcript()


@pytest.mark.unit
class TestRequestLimits:
    def test_oversized_body_rejected(self, client):
        from app.main import MAX_REQUEST_BYTES
        response = client.post("/api/extract-transcript", headers={
            **auth_headers(), "Content-Type": "application/json",
            "Content-Length": str(MAX_REQUEST_BYTES + 1)}, content=b"{}")
        assert response.status_code == 413

    def test_sse_headers_disable_buffering(self, client, fake_redis):
        response = client.post("/api/chat", headers=auth_headers(), json={"message": "???"})
        assert response.headers["x-accel-buffering"] == "no"
        assert "no-cache" in response.headers["cache-control"]

    def test_chunked_body_without_content_length_rejected(self, client):
        from app.main import MAX_REQUEST_BYTES
        chunk = b"x" * (1024 * 1024)

        def body():
            for _ in range(MAX_REQUEST_BYTES // len(chunk) + 2):
                yield chunk

        # A generator body is sent with Transfer-Encoding: chunked and no Content-Length
        response = client.post("/api/extract-transcript", content=body(),
                               headers={**auth_headers(), "Content-Type": "application/json"})
        assert response.status_code == 413


@pytest.mark.unit
class TestRateLimits:
    def test_chat_per_minute_budget(self, client, monkeypatch):
        monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "2")
        headers = auth_headers()
        # "???" fails the sanity check, so these requests never reach an LLM
        codes = [client.post("/api/chat", headers=headers, json={"message": "???"}).status_code
                 for _ in range(3)]
        assert codes == [200, 200, 429]

        # Budgets are per user
        assert client.post("/api/chat", headers=auth_headers(OTHER), json={"message": "???"}).status_code == 200

    def test_429_carries_retry_after(self, client, monkeypatch):
        monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "1")
        headers = auth_headers()
        client.post("/api/chat", headers=headers, json={"message": "???"})
        response = client.post("/api/chat", headers=headers, json={"message": "???"})
        assert response.status_code == 429
        assert 0 < int(response.headers["retry-after"]) <= 60

    def test_login_lockout_after_failures(self, client, demo_env, monkeypatch):
        monkeypatch.setenv("LOGIN_MAX_FAILURES", "2")
        wrong = {"email": "demo@wpi.edu", "password": "nope"}
        right = {"email": "demo@wpi.edu", "password": "correct horse battery staple"}

        assert client.post("/api/auth/demo-login", json=wrong).status_code == 401
        assert client.post("/api/auth/demo-login", json=wrong).status_code == 401
        # Locked out now, even with the correct password
        response = client.post("/api/auth/demo-login", json=right)
        assert response.status_code == 429
        assert "retry-after" in response.headers

    def test_successful_login_resets_email_counter(self, client, demo_env, monkeypatch, fake_redis):
        monkeypatch.setenv("LOGIN_MAX_FAILURES", "2")
        client.post("/api/auth/demo-login", json={"email": "demo@wpi.edu", "password": "nope"})
        ok = client.post("/api/auth/demo-login",
                         json={"email": "demo@wpi.edu", "password": "correct horse battery staple"})
        assert ok.status_code == 200
        assert fake_redis.get("ratelimit:login-fail:email:demo@wpi.edu") is None


@pytest.mark.unit
class TestProgramDefault:
    def test_no_program_is_invented(self):
        from app.agents.adviser_agent import AdviserAgent
        text = AdviserAgent._format_agent_input(object.__new__(AdviserAgent), "What are the core courses?")
        assert "Program:" not in text
        assert "MSIT" not in text

    def test_explicit_program_is_kept(self):
        from app.agents.adviser_agent import AdviserAgent
        text = AdviserAgent._format_agent_input(object.__new__(AdviserAgent), "Core courses?", program_id="msba")
        assert "Program: MSBA" in text
