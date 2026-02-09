from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class SkillConfig(BaseSettings):
    """Configuration for the OpenClaw Clawderpunk skill.

    All settings are read from environment variables with prefix `CLAWDERPUNK_`.
    """

    model_config = SettingsConfigDict(env_prefix="CLAWDERPUNK_", extra="ignore")

    # Punk Records
    url: str = "http://localhost:4701"
    token: str

    # Workspace identity
    workspace_id: str
    satellite_id: str = "openclaw"

    # Optional local vault root used for sync-memory.
    vault_root: Path | None = None

    # HTTP
    timeout_seconds: float = 10.0
