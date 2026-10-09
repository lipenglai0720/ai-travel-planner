"""后端应用入口：加载配置、创建 FastAPI 应用，并接入功能路由。"""

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.trips import router as trips_router
from app.core.config import Settings


# 读取并校验应用配置。
settings = Settings()

# 创建后端应用。
app = FastAPI(
    title=settings.app_name,
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)

# 接入健康检查路由。
app.include_router(health_router)

# 接入带版本前缀的旅行业务路由。
app.include_router(
    trips_router,
    prefix="/api/v1",
)