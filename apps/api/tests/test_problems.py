from typing import Any

PROBLEM = "application/problem+json"


async def test_unknown_route_is_problem_json(client: Any) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["type"].endswith("/not-found")
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["instance"] == "/api/v1/does-not-exist"


async def test_missing_token_is_problem_json(client: Any) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["type"].endswith("/unauthorized")
