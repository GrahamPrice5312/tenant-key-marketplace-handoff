import httpx

from marketplace_handoff.infrai_client import InfraiClient


def test_create_key_retries_429_and_preserves_idempotency_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"id": "key-1", "key": "issued-once"}, "error": None, "metadata": {}},
        )

    client = InfraiClient("test-key", transport=httpx.MockTransport(handler), sleep=lambda _: None)
    result = client.create_key(
        project_id="seller-acme",
        name="seller",
        scopes=["marketplace:assets"],
        idempotency_key="tenant:seller-acme:key:v1",
    )

    assert result["id"] == "key-1"
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert requests[0].method == "POST"

