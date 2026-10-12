"""创建 FastAPI 应用，并注册路由和异常处理函数。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.error_handlers import (
    amap_error_handler,
    llm_configuration_error_handler,
    trip_generation_error_handler,
)
from app.api.routes.health import router as health_router
from app.api.routes.pois import router as pois_router
from app.api.routes.trips import router as trips_router
from app.clients.amap import AmapError
from app.core.config import Settings
from app.core.errors import request_validation_error_handler
from app.llm.client import LLMConfigurationError
from app.services.trip_generation_service import TripGenerationError


settings = Settings()

app = FastAPI(
    title=settings.app_name,
    description="提供旅行规划相关的后端接口。",
    version="0.1.0",
)

# 请求输入校验失败时，返回统一的 422 响应。
app.add_exception_handler(
    RequestValidationError,
    request_validation_error_handler,
)

# 大模型配置缺失。
app.add_exception_handler(
    LLMConfigurationError,
    llm_configuration_error_handler,
)

# 已识别的旅行生成异常。
app.add_exception_handler(
    TripGenerationError,
    trip_generation_error_handler,
)

# 已识别的高德客户端异常。
app.add_exception_handler(
    AmapError,
    amap_error_handler,
)

app.include_router(health_router)

app.include_router(
    trips_router,
    prefix="/api/v1",
)

app.include_router(
    pois_router,
    prefix="/api/v1",
)