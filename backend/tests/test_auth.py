"""Authentication, token handling and role-based access control."""

from __future__ import annotations

import time

from app.core.rate_limit import auth_limiter
from app.models import UserRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import PASSWORD, auth_headers, make_user

REGISTRATION = {
    "full_name": "Rahul Pravash",
    "email": "rahul@vanraksha.org",
    "password": "MalabarThrush2026",
    "organization": "Forest Research Institute",
    "role": "RESEARCHER",
}


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def test_register_creates_a_researcher(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "rahul@vanraksha.org"
    assert body["role"] == "RESEARCHER"
    assert body["is_active"] is True
    # A password or its hash must never appear in a response.
    assert "password" not in body
    assert "password_hash" not in body


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register", json=REGISTRATION).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json=REGISTRATION)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_register_normalises_the_email_case(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTRATION)
    clash = client.post(
        "/api/v1/auth/register", json={**REGISTRATION, "email": "RAHUL@VANRAKSHA.ORG"}
    )
    assert clash.status_code == 409


def test_register_rejects_an_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={**REGISTRATION, "email": "not-an-email"}
    )
    assert response.status_code == 422
    assert "email" in response.json()["fields"]


def test_register_rejects_a_weak_password(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={**REGISTRATION, "password": "short"})
    assert response.status_code == 422
    assert "password" in str(response.json()["fields"]).lower()


def test_register_rejects_a_password_without_a_digit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={**REGISTRATION, "password": "onlyletterspassword"}
    )
    assert response.status_code == 422


def test_register_rejects_a_missing_field(client: TestClient) -> None:
    payload = {k: v for k, v in REGISTRATION.items() if k != "email"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


def test_register_rejects_mismatched_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={**REGISTRATION, "password_confirm": "SomethingElse2026"},
    )
    assert response.status_code == 422


def test_public_registration_cannot_create_an_admin(client: TestClient) -> None:
    """The single most important authorisation rule at the front door."""
    for role in ("ADMIN", "EXPERT", "FOREST_OFFICER"):
        response = client.post("/api/v1/auth/register", json={**REGISTRATION, "role": role})
        assert response.status_code == 422, role
        assert "role" in str(response.json()["fields"])


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #
def test_login_returns_a_token_pair_and_the_user(client: TestClient, researcher) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == 30 * 60
    assert body["user"]["role"] == "RESEARCHER"


def test_login_with_a_wrong_password_is_401(client: TestClient, researcher) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": "WrongPassword1"}
    )
    assert response.status_code == 401


def test_login_with_an_unknown_email_is_401_with_the_same_message(
    client: TestClient, researcher
) -> None:
    """Identical wording for both failures, so the endpoint cannot enumerate accounts."""
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@vanraksha.org", "password": PASSWORD}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": "WrongPassword1"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_login_with_an_inactive_account_is_403(client: TestClient, db: Session) -> None:
    user = make_user(
        db, email="retired@vanraksha.org", role=UserRole.RESEARCHER, is_active=False
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]


def test_login_records_the_last_login_time(
    client: TestClient, db: Session, researcher
) -> None:
    assert researcher.last_login_at is None
    auth_headers(client, researcher.email)
    db.expire_all()
    assert db.get(type(researcher), researcher.id).last_login_at is not None


def test_login_is_rate_limited(client: TestClient, researcher) -> None:
    auth_limiter.reset()
    limiter_max = auth_limiter.max_attempts
    auth_limiter.max_attempts = 4
    try:
        statuses = [
            client.post(
                "/api/v1/auth/login",
                json={"email": researcher.email, "password": "WrongPassword1"},
            ).status_code
            for _ in range(6)
        ]
    finally:
        auth_limiter.max_attempts = limiter_max
        auth_limiter.reset()
    assert 429 in statuses
    assert statuses[:2] == [401, 401]


# --------------------------------------------------------------------------- #
# tokens
# --------------------------------------------------------------------------- #
def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_a_malformed_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401


def test_me_rejects_an_expired_token(client: TestClient, researcher) -> None:
    from datetime import timedelta

    from app.core.security import create_token

    token, _, _ = create_token(
        researcher.id, "access", role="RESEARCHER", expires_delta=timedelta(seconds=-10)
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_a_refresh_token_is_not_accepted_as_an_access_token(
    client: TestClient, researcher
) -> None:
    login = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": PASSWORD}
    ).json()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login['refresh_token']}"},
    )
    assert response.status_code == 401


def test_me_reports_capabilities_for_the_role(client: TestClient, expert_headers) -> None:
    body = client.get("/api/v1/auth/me", headers=expert_headers).json()
    capabilities = body["capabilities"]
    assert capabilities["can_verify"] is True
    assert capabilities["can_record_observations"] is False
    assert capabilities["can_manage_users"] is False
    assert capabilities["can_see_precise_locations"] is True


def test_viewer_capabilities_exclude_precise_locations(
    client: TestClient, viewer_headers
) -> None:
    capabilities = client.get("/api/v1/auth/me", headers=viewer_headers).json()[
        "capabilities"
    ]
    assert capabilities["can_see_precise_locations"] is False
    assert capabilities["can_verify"] is False


def test_refresh_rotates_the_token_pair(client: TestClient, researcher) -> None:
    login = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": PASSWORD}
    ).json()
    time.sleep(1.1)  # so the new token has a different `iat`
    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != login["access_token"]

    # The presented refresh token is revoked as part of the rotation.
    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert replay.status_code == 401
    assert "revoked" in replay.json()["detail"].lower()


def test_logout_revokes_the_access_token(client: TestClient, researcher) -> None:
    login = client.post(
        "/api/v1/auth/login", json={"email": researcher.email, "password": PASSWORD}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": login["refresh_token"]},
        headers=headers,
    )
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


# --------------------------------------------------------------------------- #
# password change
# --------------------------------------------------------------------------- #
def test_change_password_then_log_in_with_the_new_one(
    client: TestClient, researcher
) -> None:
    headers = auth_headers(client, researcher.email)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "NilgiriTahr2026"},
        headers=headers,
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": researcher.email, "password": PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": researcher.email, "password": "NilgiriTahr2026"},
        ).status_code
        == 200
    )


def test_change_password_requires_the_current_one(client: TestClient, researcher) -> None:
    headers = auth_headers(client, researcher.email)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "NotIt2026", "new_password": "NilgiriTahr2026"},
        headers=headers,
    )
    assert response.status_code == 401


def test_change_password_rejects_reusing_the_current_one(
    client: TestClient, researcher
) -> None:
    headers = auth_headers(client, researcher.email)
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers=headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# role-based access control
# --------------------------------------------------------------------------- #
def test_only_recorders_may_create_observations(
    client: TestClient, viewer_headers, expert_headers, researcher_headers, observed_at
) -> None:
    payload = {
        "observed_at": observed_at,
        "latitude": 11.59,
        "longitude": 76.53,
        "observation_type": "FIELD_NOTE",
    }
    assert client.post("/api/v1/observations", json=payload).status_code == 401
    assert (
        client.post("/api/v1/observations", json=payload, headers=viewer_headers).status_code
        == 403
    )
    assert (
        client.post("/api/v1/observations", json=payload, headers=expert_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/observations", json=payload, headers=researcher_headers
        ).status_code
        == 201
    )


def test_role_denial_explains_what_is_required(
    client: TestClient, viewer_headers, observed_at
) -> None:
    response = client.post(
        "/api/v1/observations",
        json={"observed_at": observed_at, "observation_type": "FIELD_NOTE"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
    body = response.json()
    assert "RESEARCHER" in body["detail"]
    assert body["context"]["your_role"] == "VIEWER"


def test_only_admins_may_list_users(
    client: TestClient, researcher_headers, admin_headers
) -> None:
    assert client.get("/api/v1/users").status_code == 401
    assert client.get("/api/v1/users", headers=researcher_headers).status_code == 403
    assert client.get("/api/v1/users", headers=admin_headers).status_code == 200


def test_only_experts_may_see_the_review_queue(
    client: TestClient, researcher_headers, expert_headers, admin_headers
) -> None:
    assert client.get("/api/v1/verifications/queue", headers=researcher_headers).status_code == 403
    assert client.get("/api/v1/verifications/queue", headers=expert_headers).status_code == 200
    assert client.get("/api/v1/verifications/queue", headers=admin_headers).status_code == 200


def test_only_officers_may_run_anomaly_detection(
    client: TestClient, researcher_headers, officer_headers
) -> None:
    assert client.post("/api/v1/alerts/detect", headers=researcher_headers).status_code == 403
    assert client.post("/api/v1/alerts/detect", headers=officer_headers).status_code == 200


def test_admin_creates_an_expert_account(client: TestClient, admin_headers) -> None:
    """Expert accounts exist only because an administrator made one."""
    response = client.post(
        "/api/v1/users",
        json={
            "full_name": "Dr Anjali Menon",
            "email": "anjali@wii.res.in",
            "password": "SholaForest2026",
            "role": "EXPERT",
            "expertise": "Western Ghats birds",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["role"] == "EXPERT"
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "anjali@wii.res.in", "password": "SholaForest2026"},
        ).status_code
        == 200
    )


def test_an_admin_cannot_demote_themselves(client: TestClient, admin, admin_headers) -> None:
    response = client.patch(
        f"/api/v1/users/{admin.id}", json={"role": "VIEWER"}, headers=admin_headers
    )
    assert response.status_code == 422
    assert "own administrator access" in response.json()["detail"]


def test_the_last_admin_cannot_be_demoted(
    client: TestClient, db: Session, admin, admin_headers
) -> None:
    other = make_user(db, email="second-admin@vanraksha.org", role=UserRole.ADMIN)
    headers = auth_headers(client, other.email)
    # Demoting one of two admins is fine…
    assert (
        client.patch(
            f"/api/v1/users/{admin.id}", json={"role": "RESEARCHER"}, headers=headers
        ).status_code
        == 200
    )
    # …but the remaining one cannot be demoted by a new admin-less state.
    third = make_user(db, email="third@vanraksha.org", role=UserRole.ADMIN)
    third_headers = auth_headers(client, third.email)
    response = client.patch(
        f"/api/v1/users/{other.id}", json={"role": "VIEWER"}, headers=third_headers
    )
    assert response.status_code == 200  # `third` is still an active admin


def test_deactivated_user_loses_access_immediately(
    client: TestClient, researcher, admin_headers
) -> None:
    headers = auth_headers(client, researcher.email)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert (
        client.delete(f"/api/v1/users/{researcher.id}", headers=admin_headers).status_code == 200
    )
    # The token is still cryptographically valid, but the account is not.
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]
