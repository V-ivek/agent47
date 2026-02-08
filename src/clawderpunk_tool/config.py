from pydantic_settings import BaseSettings


class ToolConfig(BaseSettings):
    url: str
    token: str
    workspace_id: str
    satellite_id: str = "agent-zero"
    timeout: int = 10

    model_config = {"env_prefix": "CLAWDERPUNK_"}
