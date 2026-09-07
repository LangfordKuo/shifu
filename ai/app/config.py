"""全局配置（支持 .env 与环境变量覆盖）"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000

    # 推理设备: auto / cuda / cpu
    device: str = "auto"

    # 姿态模型路径（M2 起使用）
    model_path: str = "models/yolo11n-pose.pt"

    # CORS，逗号分隔
    allowed_origins: str = "*"

    # 与 server/.env 的 JWT_SECRET 保持一致（WS 鉴权用）
    jwt_secret: str = "change-me-to-a-random-64-hex-string"


@lru_cache
def get_settings() -> Settings:
    return Settings()
