"""读取并校验应用配置。"""

from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# config.py 位于 backend/app/core/ 中。
# parents[2] 对应 backend 目录，使 .env 的读取位置保持明确。
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，由环境变量、.env 文件和默认值提供。"""

    app_name: str = Field(
        default="AI 智能旅行规划系统",
        min_length=1,
        max_length=100,
        description="应用名称，展示在自动生成的接口文档中。",
    )

    app_env: Literal[
        "development",
        "test",
        "production",
    ] = "development"

    # 允许尚未配置模型 Key 时启动已有的预览接口。
    # 真正发送模型请求前，调用方会检查 Key 是否填写。
    llm_api_key: SecretStr | None = Field(
        default=None,
        description="大模型服务的 API Key。",
    )

    # HttpUrl 会校验 URL 格式，但不会验证服务是否能连接。
    llm_base_url: HttpUrl = Field(
        default="https://api.deepseek.com",
        description="兼容聊天接口的服务根地址。",
    )

    llm_model: str = Field(
        default="deepseek-flash",
        min_length=1,
        description="服务商提供的模型名称。",
    )

    llm_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=120,
        description="传给模型 HTTP 客户端的超时参数，单位为秒。",
    )

    # Key 使用 SecretStr 保存。
    # 普通打印配置对象时，Pydantic 会隐藏其中的真实值。
    # 真正发送高德请求时，再明确取出密钥。
    amap_web_api_key: SecretStr | None = Field(
        default=None,
        description="高德 Web 服务类型的 API Key。",
    )

    # 配置一个独立于模型调用的超时参数。
    # 10 秒默认值和 60 秒上限是本项目当前的配置策略。
    amap_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=60,
        description="高德 HTTP 请求的超时参数，单位为秒。",
    )

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        hide_input_in_errors=True,
    )