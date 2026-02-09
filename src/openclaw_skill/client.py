from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class PunkRecordsError(RuntimeError):
    pass


@dataclass(frozen=True)
class PunkRecordsClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("base_url is required")
        if not self.token:
            raise ValueError("token is required")

    def __enter__(self) -> "PunkRecordsClient":
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=httpx.Timeout(self.timeout_seconds),
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._client.close()

    def _handle(self, resp: httpx.Response) -> Any:
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        if resp.status_code >= 400:
            raise PunkRecordsError(
                f"punk-records request failed: {resp.status_code} {data!r}"
            )
        return data

    def health(self) -> dict[str, Any]:
        # /health is unauthenticated in backend; keep auth header anyway.
        resp = self._client.get("/health")
        return self._handle(resp)

    def post_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post("/events", json=event_data)
        return self._handle(resp)

    def get_events(
        self,
        *,
        workspace_id: str,
        type: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "limit": limit,
            "offset": offset,
        }
        if type is not None:
            params["type"] = type
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before

        resp = self._client.get("/events", params=params)
        return self._handle(resp)

    def get_context(
        self, *, workspace_id: str, limit: int = 10, since: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if since is not None:
            params["since"] = since
        resp = self._client.get(f"/context/{workspace_id}", params=params)
        return self._handle(resp)

    def get_memory(
        self,
        *,
        workspace_id: str,
        bucket: str | None = None,
        status: str | None = None,
        include_expired: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"include_expired": include_expired}
        if bucket is not None:
            params["bucket"] = bucket
        if status is not None:
            params["status"] = status
        resp = self._client.get(f"/memory/{workspace_id}", params=params)
        return self._handle(resp)

    def replay(self, *, workspace_id: str) -> dict[str, Any]:
        resp = self._client.post(f"/replay/{workspace_id}")
        return self._handle(resp)
