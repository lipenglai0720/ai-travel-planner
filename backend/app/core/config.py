"""应用配置：读取环境变量和 .env 文件，并校验配置值。"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 当前文件的位置是：
# backend/app/core/config.py
#
# parents[0] 是 core 目录。
# parents[1] 是 app 目录。
# parents[2] 是 backend 目录。
#
# 使用配置文件自身的位置确定 backend 目录，
# 让 .env 的查找位置不依赖终端当前所在的目录。
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """基础配置模型：创建对象时读取配置，并检查字段是否合法。"""

    # 应用名称长度必须在 1～100 个字符之间。
    # 如果环境变量和 .env 都没有提供该项，就使用 default。
    app_name: str = Field(
        default="AI 智能旅行规划系统",
        min_length=1,
        max_length=100,
        description="应用名称，展示在自动生成的接口文档中。",
    )

    # Literal 列出允许的值。
    # Pydantic 会根据这个类型声明执行校验。
    app_env: Literal["development", "test", "production"] = "development"

    # 下面定义配置的读取规则。
    model_config = SettingsConfigDict(
        # 从 backend/.env 读取本地配置。
        env_file=BACKEND_DIR / ".env",

        # 使用 UTF-8，确保中文应用名称能够正常读取。
        env_file_encoding="utf-8",

        # 环境变量名称不区分大小写。
        # APP_NAME 对应 app_name，APP_ENV 对应 app_env。
        case_sensitive=False,

        # .env 中出现未定义的配置项时，报错提醒。
        # 例如把 APP_NAME 拼成 APP_NMAE，可以尽早发现问题。
        extra="forbid",
    )