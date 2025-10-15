from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    api_port: int = Field(default=8080)
    api_token: str = Field(default="change-me-token", description="Bearer token for API auth")
    cors_origin: str = Field(default="*", description="Allowed CORS origin, e.g. https://<user>.github.io")

    # Docker/Minecraft
    docker_base_url: str = Field(default="unix://var/run/docker.sock")
    mc_container_name: str = Field(default="mc-server")
    mc_image: str = Field(default="itzg/minecraft-server:latest")
    mc_data_dir: str = Field(default="/opt/minecraft/data")
    server_port: int = Field(default=25565)

    # RCON
    enable_rcon: bool = Field(default=True)
    rcon_host: str = Field(default="mc")  # compose service name
    rcon_port: int = Field(default=25575)
    rcon_password: str = Field(default="changeme")

    # Server tuneables
    eula: bool = Field(default=True)
    memory: str = Field(default="2G")
    server_type: str = Field(default="PAPER")
    version: str = Field(default="LATEST")

    # Git sync
    git_repo: str = Field(default="")
    git_branch: str = Field(default="main")
    git_auto_push: bool = Field(default=True)
    git_push_interval_seconds: int = Field(default=300)
    git_ignore_server_properties: bool = Field(default=True)

settings = Settings()
