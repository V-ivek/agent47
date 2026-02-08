from __future__ import annotations

import httpx

from clawderpunk_tool.config import ToolConfig


class PunkRecordsClient:
    def __init__(self, config: ToolConfig):
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PunkRecordsClient:
        self._client = httpx.AsyncClient(
            base_url=self._config.url,
            headers={"Authorization": f"Bearer {self._config.token}"},
            timeout=self._config.timeout,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def post_event(self, event_data: dict) -> dict:
        """Post an event to Punk Records. Returns response dict with status."""
        try:
            resp = await self._client.post("/events", json=event_data)
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "data": resp.json(),
            }
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.ConnectError:
            return {"ok": False, "error": "connection_failed"}

    async def get_context(
        self,
        workspace_id: str,
        limit: int = 10,
        since: str | None = None,
    ) -> dict:
        """Get context pack for a workspace."""
        params: dict = {"limit": limit}
        if since:
            params["since"] = since
        try:
            resp = await self._client.get(
                f"/context/{workspace_id}", params=params
            )
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "data": resp.json(),
            }
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.ConnectError:
            return {"ok": False, "error": "connection_failed"}

    async def health(self) -> dict:
        """Check Punk Records health."""
        try:
            resp = await self._client.get("/health")
            return {
                "ok": resp.status_code < 400,
                "status": resp.status_code,
                "data": resp.json(),
            }
        except (httpx.TimeoutException, httpx.ConnectError):
            return {"ok": False, "error": "unreachable"}
