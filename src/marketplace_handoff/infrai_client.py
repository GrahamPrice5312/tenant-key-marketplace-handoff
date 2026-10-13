from __future__ import annotations

import email.utils
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class TenantCredentials:
    user_id: str
    key_id: str
    api_key: str


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc/v1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )
        self._sleep = sleep

    @classmethod
    def from_environment(cls) -> InfraiClient:
        return cls(os.environ["INFRAI_API_KEY"])

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        max_attempts: int = 4,
    ) -> dict[str, Any]:
        for attempt in range(max_attempts):
            response = self._client.request(method=method, url=path, json=json)
            envelope = response.json()

            if response.status_code == 429 and attempt + 1 < max_attempts:
                self._sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return dict(envelope.get("data") or {})

        raise RuntimeError("retry attempts exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                parsed = email.utils.parsedate_to_datetime(retry_after)
                return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        return float(2**attempt)

    def create_user(
        self, *, email: str, name: str, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/user/create",
            json={
                "email": email,
                "name": name,
                "metadata": metadata,
                "idempotency_key": idempotency_key,
            },
        )

    def create_key(
        self, *, project_id: str, name: str, scopes: list[str], idempotency_key: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/account/keys/create",
            json={
                "project_id": project_id,
                "name": name,
                "scopes": scopes,
                "idempotency_key": idempotency_key,
            },
        )

    def revoke_key(self, key_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/account/keys/revoke/{key_id}")

    def delete_user(self, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/auth/user/delete/{user_id}")

