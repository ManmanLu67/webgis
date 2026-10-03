from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEBGIS_")

    database_url: str = "sqlite:///./catalog.db"
    plugins_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "plugins")
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "data")
    default_publisher: str = "titiler"
    worker_enabled: bool = False
