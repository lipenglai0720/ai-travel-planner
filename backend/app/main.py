"""后端应用入口：读取配置、创建 FastAPI 应用，并接入各功能路由。"""

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import Settings


# 创建配置对象。
# 这一步会读取环境变量和 backend/.env，并执行配置校验。
# 如果配置不合法，会在创建 FastAPI 应用之前报错。
settings = Settings()


# 创建整个后端应用。
# 应用名称使用配置对象中的 app_name。
app = FastAPI(
    title=settings.app_name,
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)


# 将健康检查模块中的路由接入应用。
app.include_router(health_router)