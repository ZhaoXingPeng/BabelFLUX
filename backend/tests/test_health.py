import pytest
from asgi_test_client import asgi_http_client


@pytest.mark.asyncio
async def test_health_check() -> None:
    async with asgi_http_client() as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
