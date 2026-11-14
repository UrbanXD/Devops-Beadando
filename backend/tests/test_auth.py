from fastapi.testclient import TestClient

from app.settings import REFRESH_COOKIE_NAME

EMAIL = "user@example.com"
CORRECT_PASSWORD = "super-secret-password"
WRONG_PASSWORD = "wrong-password"
SHORT_PASSWORD = "short"


def register(client: TestClient, email: str = EMAIL) -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": CORRECT_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_register_login_profile_refresh_and_logout(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={"email": EMAIL, "password": CORRECT_PASSWORD},
    )
    assert registration.status_code == 201
    access_token = registration.json()["access_token"]
    assert client.cookies.get(REFRESH_COOKIE_NAME)
    assert "httponly" in registration.headers["set-cookie"].lower()
    assert "path=/api/auth" in registration.headers["set-cookie"].lower()

    profile = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert profile.status_code == 200
    assert profile.json()["email"] == EMAIL

    login = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": CORRECT_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    previous_refresh_token = client.cookies.get(REFRESH_COOKIE_NAME)
    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert client.cookies.get(REFRESH_COOKIE_NAME) != previous_refresh_token

    profile_after_refresh = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )
    assert profile_after_refresh.status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.post("/api/auth/refresh").status_code == 401


def test_login_rejects_wrong_password(client: TestClient) -> None:
    register(client)

    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": WRONG_PASSWORD},
    )

    assert response.status_code == 401


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": EMAIL, "password": SHORT_PASSWORD},
    )

    assert response.status_code == 422


def test_account_deletion_requires_password_and_removes_sessions(
    client: TestClient,
) -> None:
    access_token = register(client)
    authorization = {"Authorization": f"Bearer {access_token}"}

    rejected = client.request(
        "DELETE",
        "/api/auth/me",
        headers=authorization,
        json={"password": WRONG_PASSWORD},
    )
    assert rejected.status_code == 403
    assert client.get("/api/auth/me", headers=authorization).status_code == 200

    deleted = client.request(
        "DELETE",
        "/api/auth/me",
        headers=authorization,
        json={"password": CORRECT_PASSWORD},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "account_deleted"
    assert client.get("/api/auth/me", headers=authorization).status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401
